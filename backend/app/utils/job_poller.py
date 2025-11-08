"""Background job polling service."""
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from app.config import settings
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
from app.database import get_db, get_storage
from app.models.enums import JobStatus, AdType
from app.utils.helpers import generate_gcs_path

logger = logging.getLogger(__name__)


class JobPoller:
    """Poll Unified API for job status and update Firestore."""

    def __init__(self):
        self.db = get_db()
        self.storage = get_storage()
        self.poll_interval = settings.JOB_POLL_INTERVAL

    async def poll_job_until_complete(
        self,
        job_id: str,
        ad_type: AdType,
        user_id: str,
        campaign_id: str,
        max_attempts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Poll job status until completion or failure.
        Returns final job data.
        """
        attempts = 0
        max_attempts = max_attempts or (settings.JOB_TIMEOUT // self.poll_interval)

        while attempts < max_attempts:
            try:
                # Get job status from Unified API
                if ad_type == AdType.VIDEO:
                    job_data = await unified_api_client.get_video_job_status(job_id)
                else:
                    job_data = await unified_api_client.get_image_job_status(job_id)

                # Map Unified API status to our status
                unified_status = job_data.get("status", "").lower()
                status = self._map_status(unified_status)
                progress = job_data.get("progress", 0)

                # Update job in Firestore
                update_data = {
                    "status": status.value,
                    "progress": progress,
                }

                # If completed, download and store assets
                if status == JobStatus.COMPLETED:
                    output_urls = job_data.get("output_urls") or job_data.get("outputs") or []
                    if isinstance(output_urls, str):
                        output_urls = [output_urls]

                    update_data["output_urls"] = output_urls
                    update_data["completed_at"] = datetime.utcnow()

                    # Extract cost if available
                    cost = job_data.get("cost") or job_data.get("price", 0)
                    update_data["cost"] = cost

                    # Download assets to GCS if enabled
                    if settings.ASSET_DOWNLOAD_ENABLED and output_urls:
                        try:
                            await self._download_and_store_assets(
                                job_id=job_id,
                                user_id=user_id,
                                campaign_id=campaign_id,
                                output_urls=output_urls,
                                ad_type=ad_type,
                                job_data=job_data,
                            )
                        except Exception as e:
                            logger.error(f"Failed to download assets for job {job_id}: {e}")

                    # Update campaign cost
                    if cost > 0:
                        await self.db.increment_campaign_cost(
                            campaign_id=campaign_id,
                            cost=cost,
                            increment_assets=len(output_urls) > 0,
                        )

                # If failed, capture error
                if status == JobStatus.FAILED:
                    update_data["error_message"] = job_data.get("error") or job_data.get(
                        "error_message", "Unknown error"
                    )

                # Update job in DB
                await self.db.update_job(job_id, **update_data)

                # Return if terminal state
                if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    return await self.db.get_job(job_id, user_id)

            except UnifiedAPIError as e:
                logger.error(f"Error polling job {job_id}: {e.message}")
                if e.status_code == 404:
                    # Job not found, mark as failed
                    await self.db.update_job(
                        job_id,
                        status=JobStatus.FAILED.value,
                        error_message="Job not found in Unified API",
                    )
                    return await self.db.get_job(job_id, user_id)

            except Exception as e:
                logger.error(f"Unexpected error polling job {job_id}: {e}")

            # Wait before next poll
            await asyncio.sleep(self.poll_interval)
            attempts += 1

        # Timeout reached
        logger.warning(f"Job {job_id} polling timed out after {attempts} attempts")
        await self.db.update_job(
            job_id,
            status=JobStatus.FAILED.value,
            error_message="Polling timeout reached",
        )
        return await self.db.get_job(job_id, user_id)

    async def _download_and_store_assets(
        self,
        job_id: str,
        user_id: str,
        campaign_id: str,
        output_urls: list,
        ad_type: AdType,
        job_data: Dict[str, Any],
    ):
        """Download assets from URLs and store in GCS."""
        for idx, url in enumerate(output_urls):
            try:
                # Generate GCS path
                filename = f"{job_id}_{idx}{'.mp4' if ad_type == AdType.VIDEO else '.png'}"
                gcs_path = generate_gcs_path(user_id, campaign_id, job_id, ad_type, filename)

                # Upload to GCS
                full_gcs_path = await self.storage.upload_from_url(url, gcs_path)

                # Create asset record in Firestore
                asset_data = {
                    "job_id": job_id,
                    "campaign_id": campaign_id,
                    "ad_type": ad_type.value,
                    "model": job_data.get("model", "unknown"),
                    "prompt": job_data.get("prompt", ""),
                    "url": url,
                    "gcs_path": full_gcs_path,
                    "aspect_ratio": job_data.get("aspect_ratio", "unknown"),
                    "duration": job_data.get("duration"),
                    "cost": job_data.get("cost", 0) / len(output_urls),  # Divide cost by outputs
                    "tags": [],
                    "metadata": job_data.get("metadata", {}),
                }

                await self.db.create_asset(user_id, asset_data)
                logger.info(f"Stored asset {filename} in GCS and Firestore")

            except Exception as e:
                logger.error(f"Failed to store asset {url}: {e}")

    def _map_status(self, unified_status: str) -> JobStatus:
        """Map Unified API status to internal JobStatus."""
        status_map = {
            "pending": JobStatus.PENDING,
            "queued": JobStatus.PENDING,
            "processing": JobStatus.PROCESSING,
            "running": JobStatus.PROCESSING,
            "completed": JobStatus.COMPLETED,
            "success": JobStatus.COMPLETED,
            "failed": JobStatus.FAILED,
            "error": JobStatus.FAILED,
            "cancelled": JobStatus.CANCELLED,
            "canceled": JobStatus.CANCELLED,
        }
        return status_map.get(unified_status, JobStatus.PENDING)
