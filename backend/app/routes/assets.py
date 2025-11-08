"""Asset library endpoints."""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from app.models.schemas import (
    Asset,
    AssetFilter,
    MessageResponse,
)
from app.models.enums import AdType, ModelType
from app.middleware.auth import get_current_user_id
from app.database import get_db, get_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assets", tags=["Assets"])


@router.get("", response_model=List[Asset])
async def list_assets(
    user_id: str = Depends(get_current_user_id),
    campaign_id: Optional[str] = Query(None),
    ad_type: Optional[AdType] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all assets in the library.

    Supports filtering by campaign, ad type, tags, and pagination.
    Returns asset metadata including URLs, costs, and thumbnails.
    """
    try:
        db = get_db()
        assets = await db.list_assets(
            user_id=user_id,
            campaign_id=campaign_id,
            ad_type=ad_type.value if ad_type else None,
            tags=tags,
            limit=limit,
            offset=offset,
        )

        return [Asset(**a) for a in assets]

    except Exception as e:
        logger.error(f"Failed to list assets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list assets: {str(e)}",
        )


@router.get("/{asset_id}", response_model=Asset)
async def get_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific asset by ID."""
    try:
        db = get_db()
        asset = await db.get_asset(asset_id, user_id)

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )

        return Asset(**asset)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get asset {asset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get asset: {str(e)}",
        )


@router.patch("/{asset_id}", response_model=Asset)
async def update_asset(
    asset_id: str,
    tags: Optional[List[str]] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Update asset metadata.

    Currently supports updating tags for organization.
    """
    try:
        db = get_db()

        updates = {}
        if tags is not None:
            updates["tags"] = tags

        asset = await db.update_asset(asset_id, user_id, **updates)

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )

        logger.info(f"Asset updated: {asset_id}")
        return Asset(**asset)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update asset {asset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update asset: {str(e)}",
        )


@router.delete("/{asset_id}", response_model=MessageResponse)
async def delete_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete an asset.

    Removes the asset record from Firestore and optionally from GCS.
    """
    try:
        db = get_db()
        storage = get_storage()

        # Get asset to check GCS path
        asset = await db.get_asset(asset_id, user_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )

        # Delete from GCS if it exists
        if asset.get("gcs_path"):
            try:
                gcs_path = asset["gcs_path"].replace(f"gs://{storage.bucket.name}/", "")
                await storage.delete_blob(gcs_path)
                logger.info(f"Deleted asset from GCS: {gcs_path}")
            except Exception as e:
                logger.warning(f"Failed to delete from GCS: {e}")

        # Delete from Firestore
        success = await db.delete_asset(asset_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )

        logger.info(f"Asset deleted: {asset_id}")
        return MessageResponse(message="Asset deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete asset {asset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete asset: {str(e)}",
        )


@router.get("/{asset_id}/download-url")
async def get_download_url(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
    expiration_minutes: int = Query(60, ge=5, le=1440),
):
    """
    Get a temporary signed URL for downloading an asset from GCS.

    Returns a URL that expires after the specified number of minutes.
    """
    try:
        db = get_db()
        storage = get_storage()

        asset = await db.get_asset(asset_id, user_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )

        # If asset is in GCS, generate signed URL
        if asset.get("gcs_path"):
            gcs_path = asset["gcs_path"].replace(f"gs://{storage.bucket.name}/", "")
            signed_url = await storage.get_signed_url(gcs_path, expiration_minutes)
            return {"download_url": signed_url, "expires_in_minutes": expiration_minutes}

        # Otherwise return the original URL
        return {"download_url": asset["url"], "expires_in_minutes": None}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get download URL for asset {asset_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get download URL: {str(e)}",
        )
