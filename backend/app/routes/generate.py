"""AI generation endpoints for videos and images."""
import logging
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query, BackgroundTasks
from app.models.schemas import (
    VideoGenerationRequest,
    ImageGenerationRequest,
    JobResponse,
    MessageResponse,
)
from app.models.enums import AdType, JobStatus
from app.middleware.auth import get_current_user_id
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
from app.database import get_db
from app.utils.job_poller import JobPoller

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generate", tags=["Generation"])


@router.post("/video", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a video ad creative.

    Creates a video generation job in the Unified API and starts polling
    for completion in the background.
    """
    try:
        db = get_db()

        # Verify campaign exists and user owns it
        campaign = await db.get_campaign(request.campaign_id, user_id)
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        # Prepare video generation parameters
        video_params = {
            "prompt": request.prompt,
            "model": request.model.value,
            "aspect_ratio": request.aspect_ratio.value,
            "duration": request.duration,
        }

        # Add optional parameters
        if request.style:
            video_params["style"] = request.style
        if request.negative_prompt:
            video_params["negative_prompt"] = request.negative_prompt
        if request.seed:
            video_params["seed"] = request.seed
        if request.first_frame_image_url:
            video_params["first_frame_image_url"] = request.first_frame_image_url
        if request.last_frame_image_url:
            video_params["last_frame_image_url"] = request.last_frame_image_url
        if request.extra_params:
            video_params.update(request.extra_params)

        # Create video job in Unified API
        api_response = await unified_api_client.create_video_job(**video_params)

        # Extract job_id
        job_id = api_response.get("job_id") or api_response.get("id")
        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No job_id returned from Unified API",
            )

        # Create job record in Firestore
        job_data = {
            "job_id": job_id,
            "campaign_id": request.campaign_id,
            "ad_type": AdType.VIDEO.value,
            "model": request.model.value,
            "prompt": request.prompt,
            "status": JobStatus.PENDING.value,
            "progress": 0,
        }

        job = await db.create_job(user_id, job_data)

        # Start background polling
        poller = JobPoller()
        background_tasks.add_task(
            poller.poll_job_until_complete,
            job_id=job_id,
            ad_type=AdType.VIDEO,
            user_id=user_id,
            campaign_id=request.campaign_id,
        )

        logger.info(f"Video job created: {job_id} for campaign {request.campaign_id}")
        return JobResponse(**job)

    except UnifiedAPIError as e:
        logger.error(f"Unified API error: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create video job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create video job: {str(e)}",
        )


@router.post("/image", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def generate_image(
    request: ImageGenerationRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate an image ad creative.

    Creates an image generation job in the Unified API and starts polling
    for completion in the background.
    """
    try:
        db = get_db()

        # Verify campaign exists
        campaign = await db.get_campaign(request.campaign_id, user_id)
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        # Prepare image generation parameters
        image_params = {
            "prompt": request.prompt,
            "model": request.model.value,
            "aspect_ratio": request.aspect_ratio.value,
            "num_images": request.num_images,
        }

        # Add optional parameters
        if request.style:
            image_params["style"] = request.style
        if request.negative_prompt:
            image_params["negative_prompt"] = request.negative_prompt
        if request.seed:
            image_params["seed"] = request.seed
        if request.extra_params:
            image_params.update(request.extra_params)

        # Create image job in Unified API
        api_response = await unified_api_client.create_image_job(**image_params)

        # Extract job_id
        job_id = api_response.get("job_id") or api_response.get("id")
        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No job_id returned from Unified API",
            )

        # Create job record in Firestore
        job_data = {
            "job_id": job_id,
            "campaign_id": request.campaign_id,
            "ad_type": AdType.IMAGE.value,
            "model": request.model.value,
            "prompt": request.prompt,
            "status": JobStatus.PENDING.value,
            "progress": 0,
        }

        job = await db.create_job(user_id, job_data)

        # Start background polling
        poller = JobPoller()
        background_tasks.add_task(
            poller.poll_job_until_complete,
            job_id=job_id,
            ad_type=AdType.IMAGE,
            user_id=user_id,
            campaign_id=request.campaign_id,
        )

        logger.info(f"Image job created: {job_id} for campaign {request.campaign_id}")
        return JobResponse(**job)

    except UnifiedAPIError as e:
        logger.error(f"Unified API error: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create image job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create image job: {str(e)}",
        )


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    user_id: str = Depends(get_current_user_id),
    campaign_id: Optional[str] = Query(None),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all generation jobs for the current user.

    Supports filtering by campaign, status, and pagination.
    """
    try:
        db = get_db()
        jobs = await db.list_jobs(
            user_id=user_id,
            campaign_id=campaign_id,
            status=status_filter.value if status_filter else None,
            limit=limit,
            offset=offset,
        )

        return [JobResponse(**j) for j in jobs]

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}",
        )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get the status of a specific generation job.

    Returns the current status, progress, and output URLs if completed.
    """
    try:
        db = get_db()
        job = await db.get_job(job_id, user_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        return JobResponse(**job)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job: {str(e)}",
        )


@router.delete("/jobs/{job_id}", response_model=MessageResponse)
async def cancel_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Cancel a pending or processing job.

    Attempts to cancel the job in the Unified API and updates local status.
    """
    try:
        db = get_db()

        # Get job to verify ownership and get ad_type
        job = await db.get_job(job_id, user_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )

        # Check if job can be cancelled
        if job["status"] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel completed or failed job",
            )

        # Cancel in Unified API
        try:
            if job["ad_type"] == AdType.VIDEO.value:
                await unified_api_client.cancel_video_job(job_id)
            else:
                await unified_api_client.cancel_image_job(job_id)
        except UnifiedAPIError as e:
            logger.warning(f"Failed to cancel in Unified API: {e.message}")

        # Update status in Firestore
        await db.update_job(job_id, status=JobStatus.CANCELLED.value)

        logger.info(f"Job cancelled: {job_id}")
        return MessageResponse(message="Job cancelled successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job: {str(e)}",
        )
