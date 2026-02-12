"""Billing and usage analytics endpoints."""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Query
from app.models.schemas import UsageStats
from app.middleware.auth import get_current_user_id
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing & Usage"])


@router.get("/usage", response_model=UsageStats)
async def get_usage_statistics(
    user_id: str = Depends(get_current_user_id),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
):
    """
    Get usage statistics for the current user.

    Returns aggregated data on jobs, costs, and breakdowns by model and ad type.
    """
    try:
        db = get_db()

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get stats from Firestore
        stats = await db.get_usage_stats(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        return UsageStats(**stats)

    except Exception as e:
        logger.error(f"Failed to get usage stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage statistics: {str(e)}",
        )
