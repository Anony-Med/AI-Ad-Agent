"""Google Cloud Storage operations."""
import logging
from typing import Optional
from pathlib import Path
import httpx
from google.cloud import storage
from app.config import settings

logger = logging.getLogger(__name__)


class GCSStorage:
    """Google Cloud Storage service for asset management."""

    def __init__(self):
        """Initialize GCS client."""
        try:
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
    ) -> str:
        """Upload local file to GCS."""
        try:
            blob = self.bucket.blob(destination_path)
            blob.upload_from_filename(file_path, content_type=content_type)
            return f"gs://{settings.GCS_BUCKET_NAME}/{destination_path}"
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            raise

    async def get_signed_url(
        self,
        blob_path: str,
        expiration_minutes: int = 60,
    ) -> str:
        """Generate a signed URL for temporary access."""
        try:
            blob = self.bucket.blob(blob_path)
            url = blob.generate_signed_url(
                expiration=expiration_minutes * 60,
                method="GET",
            )
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
