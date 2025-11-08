"""Helper utility functions."""
from datetime import datetime
from typing import Optional
from app.models.enums import AdType


def generate_gcs_path(
    user_id: str,
    campaign_id: str,
    job_id: str,
    ad_type: AdType,
    filename: Optional[str] = None,
) -> str:
    """Generate GCS storage path for an asset."""
    timestamp = datetime.utcnow().strftime("%Y/%m/%d")
    extension = ".mp4" if ad_type == AdType.VIDEO else ".png"

    if not filename:
        filename = f"{job_id}{extension}"

    return f"users/{user_id}/campaigns/{campaign_id}/{timestamp}/{filename}"


def format_cost(cost: float) -> float:
    """Format cost to 2 decimal places."""
    return round(cost, 2)


def get_file_extension(url: str) -> str:
    """Extract file extension from URL."""
    return url.split(".")[-1].split("?")[0]
