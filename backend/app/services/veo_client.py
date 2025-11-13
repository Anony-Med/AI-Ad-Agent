"""
Direct Google Vertex AI Veo 3.1 API Client.

This client directly calls Google's Veo API without going through Unified API,
using image-to-video mode to bypass celebrity likeness restrictions.
"""

import asyncio
import base64
import logging
from typing import Dict, Any, Optional, List
from google.auth import default
from google.auth.transport.requests import Request
import httpx

logger = logging.getLogger(__name__)


class VeoAPIError(Exception):
    """Custom exception for Veo API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class DirectVeoClient:
    """Direct Google Vertex AI Veo 3.1 API client."""

    def __init__(
        self,
        project_id: str = "sound-invention-432122-m5",
        location: str = "us-central1",
    ):
        """
        Initialize the Direct Veo client.

        Args:
            project_id: GCP project ID
            location: GCP region for Veo API
        """
        self.project_id = project_id
        self.location = location
        self.api_endpoint = f"{location}-aiplatform.googleapis.com"
        self.model_id = "veo-3.1-generate-preview"
        self._credentials = None
        self._access_token = None

        logger.info(f"Initialized DirectVeoClient for project {project_id} in {location}")

    def _get_credentials(self):
        """
        Get Google Cloud credentials using default credentials.

        This works with:
        - gcloud auth login (local development)
        - Service account JSON key (GOOGLE_APPLICATION_CREDENTIALS)
        - Workload Identity (Cloud Run)
        """
        if not self._credentials:
            self._credentials, project = default()
            logger.info(f"Loaded default credentials for project: {project}")
        return self._credentials

    def _get_access_token(self) -> str:
        """
        Get a fresh access token.

        Returns:
            Access token string
        """
        credentials = self._get_credentials()

        # Refresh token if needed
        if not credentials.valid:
            credentials.refresh(Request())

        self._access_token = credentials.token
        return self._access_token

    async def create_video_job(
        self,
        prompt: str,
        character_image_b64: str,
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        sample_count: int = 1,
        generate_audio: bool = True,
    ) -> str:
        """
        Create a video generation job using Veo's image-to-video mode.

        This uses the direct Veo API with image in the instances array,
        which treats it as image-to-video and bypasses celebrity detection.

        Args:
            prompt: Video generation prompt describing the action/motion
            character_image_b64: Base64 encoded character image (JPEG, 512-1024px recommended)
            duration_seconds: Duration (4, 6, or 8 seconds)
            aspect_ratio: Aspect ratio (9:16, 16:9)
            resolution: Resolution (720p or 1080p)
            sample_count: Number of video variations (1-4)
            generate_audio: Whether to generate audio

        Returns:
            Operation ID for polling

        Raises:
            VeoAPIError: If the API request fails
        """
        url = (
            f"https://{self.api_endpoint}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.model_id}:predictLongRunning"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

        # Validate duration
        if duration_seconds not in [4, 6, 8]:
            logger.warning(f"Invalid duration {duration_seconds}, using 8s")
            duration_seconds = 8

        payload = {
            "instances": [
                {
                    "prompt": prompt,
                    "image": {
                        "bytesBase64Encoded": character_image_b64,
                        "mimeType": "image/jpeg",
                    },
                }
            ],
            "parameters": {
                "aspectRatio": aspect_ratio,
                "sampleCount": sample_count,
                "durationSeconds": str(duration_seconds),
                "personGeneration": "allow_all",
                "addWatermark": True,
                "includeRaiReason": True,
                "generateAudio": generate_audio,
                "resolution": resolution,
            },
        }

        logger.info(f"Creating Veo video job (prompt length: {len(prompt)} chars)")
        logger.info(f"  Prompt preview: {prompt[:120]}...")
        logger.info(f"  Full prompt: {prompt}")
        logger.debug(f"  Duration: {duration_seconds}s | Resolution: {resolution} | Aspect: {aspect_ratio}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Veo API error {response.status_code}: {error_detail}")
                    raise VeoAPIError(
                        f"Failed to create video job: {response.status_code}",
                        status_code=response.status_code,
                        detail=error_detail,
                    )

                result = response.json()
                operation_id = result.get("name", "")

                if not operation_id:
                    raise VeoAPIError(f"No operation ID in response: {result}")

                logger.info(f"✅ Veo job created: {operation_id}")
                return operation_id

            except httpx.HTTPError as e:
                logger.error(f"HTTP error creating Veo job: {e}")
                raise VeoAPIError(f"Network error: {str(e)}")

    async def extend_video_job(
        self,
        prompt: str,
        source_video_gcs_uri: str,
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        sample_count: int = 1,
        generate_audio: bool = True,
    ) -> str:
        """
        Create a video extension job using Veo's video-to-video mode.

        This extends an existing video by continuing the motion/action.
        Can be used up to 20 times to create videos up to 148 seconds long.

        IMPORTANT: Video extension requires the source video to be in GCS, not base64.

        Args:
            prompt: Video generation prompt describing the continuation
            source_video_gcs_uri: GCS URI of source video (e.g., gs://bucket/video.mp4)
            duration_seconds: Duration (4, 6, or 8 seconds)
            aspect_ratio: Aspect ratio (9:16, 16:9)
            resolution: Resolution (720p or 1080p)
            sample_count: Number of video variations (1-4)
            generate_audio: Whether to generate audio

        Returns:
            Operation ID for polling

        Raises:
            VeoAPIError: If the API request fails
        """
        url = (
            f"https://{self.api_endpoint}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.model_id}:predictLongRunning"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

        # Validate duration
        if duration_seconds not in [4, 6, 8]:
            logger.warning(f"Invalid duration {duration_seconds}, using 8s")
            duration_seconds = 8

        # For video extension, use "video" with GCS URI (not base64!)
        payload = {
            "instances": [
                {
                    "prompt": prompt,
                    "video": {
                        "gcsUri": source_video_gcs_uri,
                        "mimeType": "video/mp4",
                    },
                }
            ],
            "parameters": {
                "aspectRatio": aspect_ratio,
                "sampleCount": sample_count,
                "durationSeconds": str(duration_seconds),
                "personGeneration": "allow_all",
                "addWatermark": True,
                "includeRaiReason": True,
                "generateAudio": generate_audio,
                "resolution": resolution,
            },
        }

        logger.info(f"Extending video with prompt: {prompt[:100]}...")
        logger.debug(f"  Duration: {duration_seconds}s | Resolution: {resolution} | Aspect: {aspect_ratio}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Veo API error {response.status_code}: {error_detail}")
                    raise VeoAPIError(
                        f"Failed to extend video: {response.status_code}",
                        status_code=response.status_code,
                        detail=error_detail,
                    )

                result = response.json()
                operation_id = result.get("name", "")

                if not operation_id:
                    raise VeoAPIError(f"No operation ID in response: {result}")

                logger.info(f"✅ Video extension job created: {operation_id}")
                return operation_id

            except httpx.HTTPError as e:
                logger.error(f"HTTP error extending video: {e}")
                raise VeoAPIError(f"Network error: {str(e)}")

    async def get_operation_status(self, operation_id: str) -> Dict[str, Any]:
        """
        Fetch the status/result of a video generation operation.

        Args:
            operation_id: The operation ID returned from create_video_job

        Returns:
            Operation result dictionary

        Raises:
            VeoAPIError: If the API request fails
        """
        url = (
            f"https://{self.api_endpoint}/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.model_id}:fetchPredictOperation"
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

        payload = {
            "operationName": operation_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    raise VeoAPIError(
                        f"Failed to fetch operation status: {response.status_code}",
                        status_code=response.status_code,
                        detail=response.text,
                    )

                return response.json()

            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching operation status: {e}")
                raise VeoAPIError(f"Network error: {str(e)}")

    async def wait_for_completion(
        self,
        operation_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """
        Poll the operation until completion.

        Args:
            operation_id: Operation ID to poll
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            Final operation result with videos

        Raises:
            TimeoutError: If operation doesn't complete in time
            VeoAPIError: If operation fails
        """
        logger.info(f"Waiting for Veo job completion: {operation_id}")

        elapsed = 0
        while elapsed < timeout:
            result = await self.get_operation_status(operation_id)

            done = result.get("done", False)
            metadata = result.get("metadata", {})
            generic_metadata = metadata.get("genericMetadata", {})
            state = generic_metadata.get("state", "UNKNOWN")

            logger.debug(f"[{elapsed}s] Operation state: {state} | Done: {done}")

            if done:
                # Check for errors
                if "error" in result:
                    error_info = result["error"]
                    error_msg = error_info.get("message", str(error_info))
                    logger.error(f"Veo job failed: {error_msg}")
                    raise VeoAPIError(f"Video generation failed: {error_msg}", detail=error_info)

                # Check for successful completion
                if "response" in result:
                    videos = result.get("response", {}).get("videos", [])
                    if videos:
                        logger.info(f"✅ Veo job completed with {len(videos)} video(s)")
                        return result
                    else:
                        logger.warning("Job completed but no videos in response")
                        return result

                # Done but no response or error
                logger.warning(f"Operation marked done but no clear result: {result}")
                return result

            # Still processing
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Veo job {operation_id} timed out after {timeout}s")

    def extract_video_urls(self, operation_result: Dict[str, Any]) -> List[str]:
        """
        Extract video data from operation result.

        The videos are returned as base64 encoded strings in the response.

        Args:
            operation_result: Result from wait_for_completion

        Returns:
            List of base64 encoded video strings
        """
        response = operation_result.get("response", {})
        videos = response.get("videos", [])

        video_b64_list = []
        for video in videos:
            video_b64 = video.get("bytesBase64Encoded", "")
            if video_b64:
                video_b64_list.append(video_b64)

        logger.info(f"Extracted {len(video_b64_list)} video(s) from result")
        return video_b64_list

    async def generate_video_complete(
        self,
        prompt: str,
        character_image_b64: str,
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        timeout: int = 600,
    ) -> str:
        """
        Convenience method: Create job, wait for completion, return first video.

        Args:
            prompt: Video generation prompt
            character_image_b64: Base64 encoded character image
            duration_seconds: Duration in seconds
            aspect_ratio: Aspect ratio
            resolution: Resolution
            timeout: Max wait time

        Returns:
            Base64 encoded video string

        Raises:
            VeoAPIError: If generation fails
            TimeoutError: If generation times out
        """
        # Create job
        operation_id = await self.create_video_job(
            prompt=prompt,
            character_image_b64=character_image_b64,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            sample_count=1,
        )

        # Wait for completion
        result = await self.wait_for_completion(operation_id, timeout=timeout)

        # Extract video
        videos = self.extract_video_urls(result)
        if not videos:
            raise VeoAPIError("No video generated")

        return videos[0]


# Singleton instance
direct_veo_client = DirectVeoClient()
