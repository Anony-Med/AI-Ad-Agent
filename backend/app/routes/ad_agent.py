"""API routes for AI Ad Agent."""
import logging
import json
import asyncio
from typing import Optional, AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
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


# Simple schema for streaming endpoint
class StreamAdRequest(BaseModel):
    """Simplified request for streaming ad creation."""
    script: str = Field(..., description="The dialogue script for the ad")
    character_image: str = Field(..., description="Base64-encoded character image (data:image/png;base64,...)")
    character_name: Optional[str] = Field("character", description="Name of the character")
    voice_id: Optional[str] = Field(None, description="ElevenLabs voice ID (optional, uses default if not provided)")
    aspect_ratio: Optional[str] = Field(default_factory=lambda: settings.VEO_DEFAULT_ASPECT_RATIO, description="Video aspect ratio")
    resolution: Optional[str] = Field(default_factory=lambda: settings.VEO_DEFAULT_RESOLUTION, description="Video resolution")


# Initialize pipeline (will be created per request to support different settings and user keys)
async def get_pipeline(
    user_id: str,
    enable_verification: bool = True,
    verification_threshold: Optional[float] = None,
) -> AdCreationPipeline:
    """
    Get pipeline instance with API keys from Secret Manager.

    Tries user-specific secrets first, then falls back to global.

    Args:
        user_id: User identifier for fetching user-specific API keys
        enable_verification: Whether to verify clips match script
        verification_threshold: Minimum confidence score (0.0-1.0)

    Returns:
        AdCreationPipeline instance configured with user's or global API keys
    """
    from app.secrets import get_user_secret

    # Use asyncio.to_thread to avoid blocking the event loop with synchronous gRPC calls
    gemini_key = await asyncio.to_thread(get_user_secret, user_id, "gemini")
    if not gemini_key:
        gemini_key = await asyncio.to_thread(get_user_secret, user_id, "google")

    elevenlabs_key = await asyncio.to_thread(get_user_secret, user_id, "elevenlabs")

    # Anthropic API key (for agentic orchestrator)
    anthropic_key = await asyncio.to_thread(get_user_secret, user_id, "anthropic")
    if not anthropic_key:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            logger.info(f"Using environment variable for Anthropic API key (user {user_id})")

    # Fall back to environment variables if Secret Manager not available
    if not gemini_key:
        gemini_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        logger.warning(f"Using environment variable for Gemini API key (user {user_id})")

    if not elevenlabs_key:
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        logger.warning(f"Using environment variable for ElevenLabs API key (user {user_id})")

    logger.info(f"Pipeline initialized for user {user_id} with verification={enable_verification}, anthropic={'yes' if anthropic_key else 'no'}")

    return AdCreationPipeline(
        gemini_api_key=gemini_key,
        elevenlabs_api_key=elevenlabs_key,
        anthropic_api_key=anthropic_key,
        enable_verification=enable_verification,
        verification_threshold=verification_threshold if verification_threshold is not None else settings.VERIFICATION_THRESHOLD,
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

        # Validate campaign exists (skip if Firestore not available)
        try:
            from app.database import get_db
            db = get_db()
            campaign = await db.get_campaign(request.campaign_id, user_id)

            if not campaign:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Campaign not found",
                )
        except Exception as e:
            logger.warning(f"Skipping campaign validation (Firestore not available): {e}")

        # Create pipeline with user-specific API keys and verification settings
        pipeline = await get_pipeline(
            user_id=user_id,
            enable_verification=request.enable_verification,
            verification_threshold=request.verification_threshold,
        )

        # Start job in background — use agentic pipeline if Anthropic key is available
        job_id = f"ad_{int(__import__('time').time() * 1000)}"

        if pipeline.anthropic_api_key:
            logger.info(f"Using AGENTIC pipeline for ad creation (user {user_id})")
            background_tasks.add_task(
                pipeline.create_ad_agentic,
                request=request,
                user_id=user_id,
            )
        else:
            logger.info(f"Using LEGACY pipeline for ad creation (user {user_id})")
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
        pipeline = await get_pipeline(user_id=user_id)
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

        pipeline = await get_pipeline(user_id=user_id)
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
        from app.ad_agent.clients.gemini_client import DEFAULT_VEO_PROMPT_SYSTEM_INSTRUCTION
        from app.config import settings

        gemini_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        agent = PromptGeneratorAgent(api_key=gemini_key)

        prompts, segments = await agent.generate_prompts_with_segments(
            script=script,
            system_prompt=DEFAULT_VEO_PROMPT_SYSTEM_INSTRUCTION,
            num_segments=settings.CLIPS_PER_AD,
            character_name=character_name,
        )

        return {
            "script": script,
            "character_name": character_name,
            "prompts": prompts,
            "script_segments": segments,
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
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # Also check Secret Manager for Anthropic key
    # Use asyncio.to_thread to avoid blocking the event loop with synchronous gRPC
    if not anthropic_key:
        try:
            import asyncio
            from app.secrets import get_secret
            anthropic_key = await asyncio.to_thread(get_secret, "ai_ad_agent_anthropic_api_key")
        except Exception:
            pass

    return {
        "status": "healthy",
        "gemini_configured": bool(gemini_key),
        "elevenlabs_configured": bool(elevenlabs_key),
        "anthropic_configured": bool(anthropic_key),
        "pipeline_mode": "agentic" if anthropic_key else "legacy",
    }


@router.post("/create-stream")
async def create_ad_stream(
    request: StreamAdRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create an AI-generated video ad with real-time progress updates.

    This endpoint streams progress updates as Server-Sent Events (SSE) and returns
    the final video URL when complete.

    **Input:**
    - script: Your ad script (what the character will say)
    - character_image: Base64-encoded avatar image
    - character_name: Name of the character (optional)
    - voice_id: ElevenLabs voice ID (optional, uses default if not provided)

    **Progress Events:**
    - step1: Generating prompts
    - step2: Generating clip X/Y
    - step3: Merging videos
    - step4: Enhancing voice
    - step5: Finalizing
    - complete: Final video URL

    **Example:**
    ```
    curl -N -X POST http://localhost:8001/api/ad-agent/create-stream \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "script": "Your ad script here...",
        "character_image": "data:image/png;base64,..."
      }'
    ```
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events with progress updates."""
        import time

        try:
            # Convert to full AdRequest
            ad_request = AdRequest(
                campaign_id="stream-ad",  # Auto-generated campaign
                script=request.script,
                character_image=request.character_image,
                character_name=request.character_name,
                voice_id=request.voice_id,
                aspect_ratio=request.aspect_ratio,
                resolution=request.resolution,
            )

            # Progress callback queue
            progress_queue = asyncio.Queue()

            async def progress_callback(event: str, data: dict):
                """Callback to emit progress events."""
                await progress_queue.put({"event": event, "data": data})

            # Create pipeline with progress callback
            pipeline = await get_pipeline(user_id=user_id)
            pipeline.progress_callback = progress_callback

            # Start ad creation in background — use agentic if available
            async def create_ad_task():
                try:
                    if pipeline.anthropic_api_key:
                        logger.info("Using AGENTIC pipeline for streaming ad creation")
                        job = await pipeline.create_ad_agentic(ad_request, user_id)
                    else:
                        logger.info("Using LEGACY pipeline for streaming ad creation")
                        job = await pipeline.create_ad(ad_request, user_id)
                    await progress_queue.put({"event": "complete", "data": {
                        "status": job.status.value if hasattr(job.status, 'value') else job.status,
                        "final_video_url": job.final_video_url,
                        "job_id": job.job_id,
                    }})
                except Exception as e:
                    logger.error(f"Ad creation failed: {e}", exc_info=True)
                    await progress_queue.put({"event": "error", "data": {
                        "message": str(e)
                    }})
                finally:
                    await progress_queue.put(None)  # Signal completion

            # Start background task
            task = asyncio.create_task(create_ad_task())

            # Track last event time for keepalive
            last_event_time = time.time()

            # Stream events with keepalive to prevent timeout
            # SSE connections can timeout after 2-5 minutes of inactivity
            # Send keepalive comments every 15 seconds to keep connection alive
            while True:
                try:
                    # Wait for event with timeout for keepalive
                    event = await asyncio.wait_for(progress_queue.get(), timeout=settings.SSE_KEEPALIVE_SECONDS)

                    if event is None:  # End signal
                        break

                    # Update last event time
                    last_event_time = time.time()

                    # Format as SSE
                    event_name = event["event"]
                    event_data = json.dumps(event["data"])

                    yield f"event: {event_name}\n"
                    yield f"data: {event_data}\n\n"

                except asyncio.TimeoutError:
                    # No event in 15 seconds - send keepalive comment
                    # SSE comments (lines starting with :) keep connection alive without triggering events
                    yield f": keepalive {int(time.time())}\n\n"
                    logger.debug(f"Sent keepalive at {int(time.time())}")

            # Wait for task to complete
            await task

        except Exception as e:
            logger.error(f"Streaming ad creation failed: {e}", exc_info=True)
            error_data = json.dumps({"message": str(e)})
            yield f"event: error\n"
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/create-stream-upload")
async def create_ad_stream_with_upload(
    script: str = Form(..., description="The dialogue script for the ad"),
    avatar: UploadFile = File(..., description="Avatar image file (PNG, JPG)"),
    character_name: Optional[str] = Form("character", description="Name of the character"),
    voice_id: Optional[str] = Form(None, description="ElevenLabs voice ID"),
    aspect_ratio: Optional[str] = Form(None, description="Video aspect ratio"),
    resolution: Optional[str] = Form(None, description="Video resolution"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Create an AI-generated video ad with real-time progress updates (FILE UPLOAD VERSION).

    **This endpoint accepts multipart/form-data with file upload - much easier than base64!**

    **Input:**
    - script: Your ad script (form field)
    - avatar: Avatar image file (PNG, JPG - file upload)
    - character_name: Name of the character (optional, form field)
    - voice_id: ElevenLabs voice ID (optional, form field)
    - aspect_ratio: Video aspect ratio (optional, form field)
    - resolution: Video resolution (optional, form field)

    **Progress Events:**
    Same as /create-stream endpoint - streams SSE events.

    **Example (Python with httpx):**
    ```python
    files = {"avatar": open("Avatar.png", "rb")}
    data = {
        "script": "Your ad script...",
        "character_name": "Heather"
    }
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8001/api/ad-agent/create-stream-upload",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {token}"}
        ) as response:
            # Process SSE events...
    ```

    **Example (cURL):**
    ```bash
    curl -N -X POST http://localhost:8001/api/ad-agent/create-stream-upload \
      -H "Authorization: Bearer TOKEN" \
      -F "script=Your ad script here..." \
      -F "avatar=@Avatar.png" \
      -F "character_name=Heather"
    ```
    """
    import base64

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events with progress updates."""
        import time

        try:
            # Read uploaded file and convert to base64
            avatar_bytes = await avatar.read()
            avatar_b64 = base64.b64encode(avatar_bytes).decode('utf-8')

            # Determine image format from filename or content type
            content_type = avatar.content_type or "image/png"
            if "jpeg" in content_type or "jpg" in content_type:
                mime = "image/jpeg"
            else:
                mime = "image/png"

            avatar_data_uri = f"data:{mime};base64,{avatar_b64}"

            # Convert to full AdRequest
            ad_request = AdRequest(
                campaign_id="stream-ad-upload",
                script=script,
                character_image=avatar_data_uri,
                character_name=character_name,
                voice_id=voice_id,
                aspect_ratio=aspect_ratio or settings.VEO_DEFAULT_ASPECT_RATIO,
                resolution=resolution or settings.VEO_DEFAULT_RESOLUTION,
            )

            # Progress callback queue
            progress_queue = asyncio.Queue()

            async def progress_callback(event: str, data: dict):
                """Callback to emit progress events."""
                await progress_queue.put({"event": event, "data": data})

            # Create pipeline with progress callback
            pipeline = await get_pipeline(user_id=user_id)
            pipeline.progress_callback = progress_callback

            # Start ad creation in background — use agentic if available
            async def create_ad_task():
                try:
                    if pipeline.anthropic_api_key:
                        logger.info("Using AGENTIC pipeline for streaming upload ad creation")
                        job = await pipeline.create_ad_agentic(ad_request, user_id)
                    else:
                        logger.info("Using LEGACY pipeline for streaming upload ad creation")
                        job = await pipeline.create_ad(ad_request, user_id)
                    await progress_queue.put({"event": "complete", "data": {
                        "status": job.status.value if hasattr(job.status, 'value') else job.status,
                        "final_video_url": job.final_video_url,
                        "job_id": job.job_id,
                    }})
                except Exception as e:
                    logger.error(f"Ad creation failed: {e}", exc_info=True)
                    await progress_queue.put({"event": "error", "data": {
                        "message": str(e)
                    }})
                finally:
                    await progress_queue.put(None)  # Signal completion

            # Start background task
            task = asyncio.create_task(create_ad_task())

            # Track last event time for keepalive
            last_event_time = time.time()

            # Stream events with keepalive to prevent timeout
            # SSE connections can timeout after 2-5 minutes of inactivity
            # Send keepalive comments every 15 seconds to keep connection alive
            while True:
                try:
                    # Wait for event with timeout for keepalive
                    event = await asyncio.wait_for(progress_queue.get(), timeout=settings.SSE_KEEPALIVE_SECONDS)

                    if event is None:  # End signal
                        break

                    # Update last event time
                    last_event_time = time.time()

                    # Format as SSE
                    event_name = event["event"]
                    event_data = json.dumps(event["data"])

                    yield f"event: {event_name}\n"
                    yield f"data: {event_data}\n\n"

                except asyncio.TimeoutError:
                    # No event in 15 seconds - send keepalive comment
                    # SSE comments (lines starting with :) keep connection alive without triggering events
                    yield f": keepalive {int(time.time())}\n\n"
                    logger.debug(f"Sent keepalive at {int(time.time())}")

            # Wait for task to complete
            await task

        except Exception as e:
            logger.error(f"Streaming ad creation failed: {e}", exc_info=True)
            error_data = json.dumps({"message": str(e)})
            yield f"event: error\n"
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

