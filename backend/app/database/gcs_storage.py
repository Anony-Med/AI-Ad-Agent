"""Google Cloud Storage operations."""
import json
import logging
from typing import Optional
from pathlib import Path
import httpx
from google.cloud import storage
from google.oauth2 import service_account
from app.config import settings

logger = logging.getLogger(__name__)


class GCSStorage:
    """Google Cloud Storage service for asset management."""

    def __init__(self):
        """Initialize GCS client with service account from Secret Manager."""
        try:
            # Try to load service account credentials from Secret Manager for signed URLs
            credentials = None
            try:
                from app.secrets import get_secret
                service_account_json = get_secret("gcs-service-account-key")

                if service_account_json:
                    # Parse the JSON and create credentials
                    service_account_info = json.loads(service_account_json)
                    credentials = service_account.Credentials.from_service_account_info(
                        service_account_info
                    )
                    logger.info("✓ Loaded GCS service account credentials from Secret Manager")
            except Exception as e:
                logger.warning(f"Could not load service account from Secret Manager: {e}")
                logger.info("Using default credentials (signed URLs may not work)")

            # Initialize storage client with credentials if available
            if credentials:
                self.client = storage.Client(project=settings.GCP_PROJECT_ID, credentials=credentials)
            else:
                self.client = storage.Client(project=settings.GCP_PROJECT_ID)

            self.bucket = self.client.bucket(settings.GCS_BUCKET_NAME)
            logger.info(f"GCS initialized with bucket: {settings.GCS_BUCKET_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize GCS: {e}")
            raise

    async def upload_from_url(
        self,
        source_url: str,
        destination_path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Download from URL and upload to GCS."""
        try:
            # Download the file
            async with httpx.AsyncClient() as client:
                response = await client.get(source_url, timeout=120.0)
                response.raise_for_status()
                file_data = response.content

            # Upload to GCS
            blob = self.bucket.blob(destination_path)

            # Detect content type if not provided
            if not content_type:
                if destination_path.endswith(".mp4"):
                    content_type = "video/mp4"
                elif destination_path.endswith(".png"):
                    content_type = "image/png"
                elif destination_path.endswith(".jpg") or destination_path.endswith(".jpeg"):
                    content_type = "image/jpeg"
                else:
                    content_type = "application/octet-stream"

            blob.upload_from_string(file_data, content_type=content_type)

            # Make publicly accessible (optional, remove if you want private)
            # blob.make_public()

            # Return GCS path
            return f"gs://{settings.GCS_BUCKET_NAME}/{destination_path}"

        except Exception as e:
            logger.error(f"Failed to upload from URL {source_url}: {e}")
            raise

    async def upload_from_file(
        self,
        file_path: str,
        destination_path: str,
        content_type: Optional[str] = None,
        timeout: int = 300,  # 5 minute timeout
    ) -> str:
        """Upload local file to GCS with timeout."""
        try:
            blob = self.bucket.blob(destination_path)
            logger.info(f"Uploading {file_path} to GCS with {timeout}s timeout...")
            blob.upload_from_filename(file_path, content_type=content_type, timeout=timeout)
            logger.info(f"Successfully uploaded {file_path} to gs://{settings.GCS_BUCKET_NAME}/{destination_path}")
            return f"gs://{settings.GCS_BUCKET_NAME}/{destination_path}"
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} after {timeout}s: {e}")
            raise

    async def get_signed_url(
        self,
        blob_path: str,
        expiration_days: int = 7,
    ) -> str:
        """
        Generate a signed URL for temporary access.

        Args:
            blob_path: Path to blob in bucket
            expiration_days: Number of days until URL expires (default: 7)

        Returns:
            Signed URL that expires after specified days
        """
        try:
            from datetime import timedelta

            blob = self.bucket.blob(blob_path)
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(days=expiration_days),
                method="GET",
            )
            logger.info(f"Generated signed URL for {blob_path} (expires in {expiration_days} days)")
            return url
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {blob_path}: {e}")
            raise

    async def delete_blob(self, blob_path: str) -> bool:
        """Delete a blob from GCS."""
        try:
            blob = self.bucket.blob(blob_path)
            blob.delete()
            return True
        except Exception as e:
            logger.error(f"Failed to delete blob {blob_path}: {e}")
            return False

    async def blob_exists(self, blob_path: str) -> bool:
        """Check if a blob exists."""
        blob = self.bucket.blob(blob_path)
        return blob.exists()

    async def download_to_file(self, blob_path: str, destination_path: str) -> str:
        """Download a blob to local file."""
        try:
            blob = self.bucket.blob(blob_path)
            blob.download_to_filename(destination_path)
            logger.info(f"Downloaded {blob_path} to {destination_path}")
            return destination_path
        except Exception as e:
            logger.error(f"Failed to download blob {blob_path}: {e}")
            raise

    async def download_as_bytes(self, blob_path: str) -> bytes:
        """Download a blob as bytes."""
        try:
            blob = self.bucket.blob(blob_path)
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"Failed to download blob {blob_path}: {e}")
            raise

    def get_public_url(self, blob_path: str) -> str:
        """Get public URL for a blob."""
        return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob_path}"


# Singleton instance
_storage_instance: Optional[GCSStorage] = None


def get_storage() -> GCSStorage:
    """Get GCS storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = GCSStorage()
    return _storage_instance


async def upload_file_to_gcs(file_path: str, blob_name: str) -> str:
    """
    Upload a file to GCS and return a signed URL.

    Args:
        file_path: Local path to the file to upload
        blob_name: Destination path in GCS bucket

    Returns:
        Signed URL for the uploaded file (7-day expiration)
    """
    storage = get_storage()

    # Upload file
    await storage.upload_from_file(file_path, blob_name)

    # Get signed URL
    signed_url = await storage.get_signed_url(blob_name, expiration_days=7)

    return signed_url
