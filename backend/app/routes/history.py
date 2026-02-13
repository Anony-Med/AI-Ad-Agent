"""History endpoint for listing past generation jobs."""
import logging
from fastapi import APIRouter, Depends, Query
from app.middleware.auth import get_current_user_id
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["History"])


@router.get("")
async def get_history(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get generation history for the current user.

    Returns ad_jobs ordered by creation date descending.
    """
    db = get_db()
    jobs = await db.list_jobs(user_id=user_id, limit=limit, offset=offset)

    transformed = []
    for job in jobs:
        transformed.append({
            "job_id": job.get("job_id", ""),
            "type": "video",
            "model": "ai-ad-agent",
            "prompt": job.get("script", ""),
            "status": _map_status(job.get("status", "")),
            "created_at": _serialize_dt(job.get("created_at")),
            "completed_at": _serialize_dt(job.get("updated_at")),
            "output_urls": [job["final_video_url"]] if job.get("final_video_url") else [],
            "thumbnail_url": None,
            "output_type": "video",
        })

    return {
        "user_id": user_id,
        "total": len(transformed),
        "limit": limit,
        "offset": offset,
        "jobs": transformed,
    }


def _map_status(status: str) -> str:
    """Map AI-Ad-Agent job status to frontend-expected status."""
    mapping = {
        "pending": "queued",
        "processing": "running",
        "generating_prompts": "running",
        "generating_clips": "running",
        "merging": "running",
        "enhancing_audio": "running",
        "finalizing": "running",
        "completed": "succeeded",
        "failed": "failed",
    }
    return mapping.get(status, status)


def _serialize_dt(dt) -> str | None:
    """Serialize datetime to ISO string."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()
