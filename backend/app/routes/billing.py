"""Billing and usage analytics endpoints."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Query
from app.models.schemas import (
    UsageStats,
    BillingRecord,
)
from app.middleware.auth import get_current_user_id
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
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


@router.get("/history", response_model=List[BillingRecord])
async def get_billing_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get billing history from Unified API.

    Returns detailed billing records for all generations.
    """
    try:
        records = await unified_api_client.get_billing_history(
            limit=limit,
            offset=offset,
        )

        # Convert to BillingRecord format
        billing_records = []
        for record in records:
            billing_records.append(
                BillingRecord(
                    id=record.get("id", ""),
                    user_id=record.get("user_id", ""),
                    job_id=record.get("job_id", ""),
                    amount=record.get("amount", 0),
                    model=record.get("model", ""),
                    ad_type=record.get("type", ""),
                    description=record.get("description", ""),
                    created_at=record.get("created_at") or datetime.utcnow(),
                )
            )

        return billing_records

    except UnifiedAPIError as e:
        logger.error(f"Failed to get billing history: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
        )
    except Exception as e:
        logger.error(f"Failed to get billing history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get billing history: {str(e)}",
        )


@router.get("/models")
async def get_available_models():
    """
    Get list of available AI models with pricing information.

    Returns models from the Unified API with their capabilities and costs.
    """
    try:
        models = await unified_api_client.get_models()
        return {"models": models}

    except UnifiedAPIError as e:
        logger.error(f"Failed to get models: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
        )
    except Exception as e:
        logger.error(f"Failed to get models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get models: {str(e)}",
        )
