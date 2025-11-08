"""API routes for AI Ad Agent."""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from app.models.schemas import MessageResponse
from app.ad_agent.interfaces.ad_schemas import (
    AdRequest,
    AdJobResponse,
    AdJobStatus,
)
from app.ad_agent.pipelines.ad_creation_pipeline import AdCreationPipeline
from app.middleware.auth import get_current_user_id
from app.config import settings
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ad-agent", tags=["AI Ad Agent"])


# Initialize pipeline (will be created per request to support different settings and user keys)
def get_pipeline(
    user_id: str,
    enable_verification: bool = True,
    verification_threshold: float = 0.6
) -> AdCreationPipeline:
    """
    Get pipeline instance with API keys from Secret Manager.

    Follows Unified API pattern: tries user-specific secrets first, then falls back to global.

    Args:
        user_id: User identifier for fetching user-specific API keys
        enable_verification: Whether to verify clips match script
        verification_threshold: Minimum confidence score (0.0-1.0)

    Returns:
        AdCreationPipeline instance configured with user's or global API keys
    """
    from app.secrets import get_user_secret

    # Get user-specific API keys (falls back to global if not found)
    gemini_key = get_user_secret(user_id, "gemini", "api_key")
    if not gemini_key:
        # Try "google" as provider name (compatible with unified API)
        gemini_key = get_user_secret(user_id, "google", "api_key")

    elevenlabs_key = get_user_secret(user_id, "elevenlabs", "api_key")

    # Fall back to environment variables if Secret Manager not available
    if not gemini_key:
        gemini_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        logger.warning(f"Using environment variable for Gemini API key (user {user_id})")

    if not elevenlabs_key:
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        logger.warning(f"Using environment variable for ElevenLabs API key (user {user_id})")

    logger.info(f"Pipeline initialized for user {user_id} with verification={enable_verification}")

    return AdCreationPipeline(
        gemini_api_key=gemini_key,
        elevenlabs_api_key=elevenlabs_key,
        enable_verification=enable_verification,
        verification_threshold=verification_threshold,
    )


@router.post("/create", response_model=AdJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_ad(
    request: AdRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create an AI-generated video ad from a script.

    This endpoint starts a background job that executes the 9-step workflow:
    1. Generate Veo prompts + script segments from script
    2. Generate video clips with Veo 3.1
    2.5. Verify clips match script content (optional, uses Gemini Vision)
    3. Merge video clips
    4. Get creative enhancement suggestions
    5. Generate voiceover with ElevenLabs
    6. Replace video audio with voiceover
    7. Add background music and sound effects
    8. Final export and upload

    Returns immediately with job ID. Use GET /ad-agent/jobs/{id} to check status.
    """
    try:
        logger.info(f"Creating ad for user {user_id}, campaign {request.campaign_id}")

        # Validate campaign exists
        from app.database import get_db
        db = get_db()
        campaign = await db.get_campaign(request.campaign_id, user_id)

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        # Create pipeline with user-specific API keys and verification settings
        pipeline = get_pipeline(
            user_id=user_id,
            enable_verification=request.enable_verification,
            verification_threshold=request.verification_threshold,
        )

        # Start job in background
        job_id = f"ad_{int(__import__('time').time() * 1000)}"

        background_tasks.add_task(
            pipeline.create_ad,
            request=request,
            user_id=user_id,
        )

        logger.info(f"Ad creation job started: {job_id}")

        # Return initial job response
        from datetime import datetime
        return AdJobResponse(
            job_id=job_id,
            status=AdJobStatus.PENDING,
            progress=0,
            current_step="Job queued...",
            final_video_url=None,
            error_message=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create ad: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create ad: {str(e)}",
        )


@router.get("/jobs/{job_id}", response_model=AdJobResponse)
async def get_ad_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the status of an ad creation job.

    Returns progress, current step, and final video URL when complete.
    """
    try:
        pipeline = get_pipeline()
        job = await pipeline.get_job_status(job_id, user_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        return AdJobResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            current_step=job.current_step,
            final_video_url=job.final_video_url,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


@router.get("/jobs/{job_id}/download")
async def download_ad_video(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the download URL for a completed ad video.

    Returns a redirect to the signed GCS URL.
    """
    try:
        from fastapi.responses import RedirectResponse

        pipeline = get_pipeline()
        job = await pipeline.get_job_status(job_id, user_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        if job.status != AdJobStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job not completed yet. Status: {job.status}",
            )

        if not job.final_video_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video URL not available",
            )

        # Redirect to the GCS signed URL
        return RedirectResponse(url=job.final_video_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get download URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get download URL: {str(e)}",
        )


@router.post("/test/prompts")
async def test_prompt_generation(
    script: str,
    character_name: str = "character",
    user_id: str = Depends(get_current_user_id),
):
    """
    Test endpoint: Generate Veo prompts from a script without creating videos.

    Useful for testing and previewing prompts before starting full workflow.
    """
    try:
        from app.ad_agent.agents.prompt_generator import PromptGeneratorAgent

        gemini_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        agent = PromptGeneratorAgent(api_key=gemini_key)

        prompts = await agent.generate_prompts(
            script=script,
            character_name=character_name,
        )

        return {
            "script": script,
            "character_name": character_name,
            "prompts": prompts,
            "total_clips": len(prompts),
            "estimated_duration": len(prompts) * 7,
        }

    except Exception as e:
        logger.error(f"Failed to generate test prompts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate prompts: {str(e)}",
        )


@router.get("/health")
async def ad_agent_health():
    """
    Health check for AI Ad Agent.

    Checks if required API keys are configured.
    """
    gemini_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")

    return {
        "status": "healthy",
        "gemini_configured": bool(gemini_key),
        "elevenlabs_configured": bool(elevenlabs_key),
        "unified_api_url": settings.UNIFIED_API_BASE_URL,
    }
