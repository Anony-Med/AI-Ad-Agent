"""Campaign management endpoints."""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from app.models.schemas import (
    Campaign,
    CampaignCreate,
    CampaignUpdate,
    MessageResponse,
)
from app.models.enums import CampaignStatus
from app.middleware.auth import get_current_user_id
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_data: CampaignCreate,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a new ad campaign.

    Creates a campaign with specified platform, ad type, and targeting parameters.
    """
    try:
        db = get_db()
        campaign = await db.create_campaign(
            user_id=user_id,
            campaign_data=campaign_data.model_dump(),
        )

        logger.info(f"Campaign created: {campaign['id']} by user {user_id}")
        return Campaign(**campaign)

    except Exception as e:
        logger.error(f"Failed to create campaign: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create campaign: {str(e)}",
        )


@router.get("", response_model=List[Campaign])
async def list_campaigns(
    user_id: str = Depends(get_current_user_id),
    status_filter: Optional[CampaignStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all campaigns for the current user.

    Supports filtering by status and pagination.
    """
    try:
        db = get_db()
        campaigns = await db.list_campaigns(
            user_id=user_id,
            status=status_filter.value if status_filter else None,
            limit=limit,
            offset=offset,
        )

        return [Campaign(**c) for c in campaigns]

    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list campaigns: {str(e)}",
        )


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific campaign by ID."""
    try:
        db = get_db()
        campaign = await db.get_campaign(campaign_id, user_id)

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        return Campaign(**campaign)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaign {campaign_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get campaign: {str(e)}",
        )


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: str,
    updates: CampaignUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """
    Update a campaign.

    Allows updating campaign details, status, budget, and other metadata.
    """
    try:
        db = get_db()

        # Only update fields that were provided
        update_data = updates.model_dump(exclude_unset=True)

        campaign = await db.update_campaign(
            campaign_id=campaign_id,
            user_id=user_id,
            **update_data,
        )

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        logger.info(f"Campaign updated: {campaign_id}")
        return Campaign(**campaign)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update campaign {campaign_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update campaign: {str(e)}",
        )


@router.delete("/{campaign_id}", response_model=MessageResponse)
async def delete_campaign(
    campaign_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete a campaign.

    Note: This does not delete associated assets from storage.
    Consider archiving instead of deleting.
    """
    try:
        db = get_db()
        success = await db.delete_campaign(campaign_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        logger.info(f"Campaign deleted: {campaign_id}")
        return MessageResponse(message="Campaign deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete campaign {campaign_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete campaign: {str(e)}",
        )
