"""
Direct Google Vertex AI Veo 3.1 API Client using google-genai SDK.

Uses the google-genai SDK with Vertex AI backend for video generation.
Supports image-to-video and video extension modes.
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


class VeoAPIError(Exception):
    """Custom exception for Veo API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class DirectVeoClient:
    """Direct Google Vertex AI Veo 3.1 API client using google-genai SDK."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ):
        """
        Initialize the Direct Veo client.

        Args:
            project_id: GCP project ID (defaults to settings.GCP_PROJECT_ID)
            location: GCP region for Veo API (defaults to settings.VEO_REGION)
        """
        self.project_id = project_id or settings.GCP_PROJECT_ID
        self.location = location or settings.VEO_REGION
        self.model_id = settings.VEO_MODEL_ID

        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

        # Cache operations by name for polling
        self._operations: Dict[str, Any] = {}

        logger.info(
            f"Initialized DirectVeoClient (google-genai SDK) "
            f"for project {self.project_id} in {self.location}"
        )

    async def create_video_job(
        self,
        prompt: str,
        character_image_b64: str,
        duration_seconds: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
        sample_count: Optional[int] = None,
        generate_audio: bool = True,
    ) -> str:
        """
        Create a video generation job using Veo's image-to-video mode.

        Args:
            prompt: Video generation prompt describing the action/motion
            character_image_b64: Base64 encoded character image (JPEG)
            duration_seconds: Duration (4, 6, or 8 seconds)
            aspect_ratio: Aspect ratio (9:16, 16:9)
            resolution: Resolution (720p or 1080p)
            sample_count: Number of video variations (1-4)
            generate_audio: Whether to generate audio

        Returns:
            Operation name (string) for polling

        Raises:
            VeoAPIError: If the API request fails
        """
        duration_seconds = duration_seconds if duration_seconds is not None else settings.MAX_CLIP_DURATION
        aspect_ratio = aspect_ratio or settings.VEO_DEFAULT_ASPECT_RATIO
        resolution = resolution or settings.VEO_DEFAULT_RESOLUTION
        sample_count = sample_count if sample_count is not None else settings.VEO_SAMPLE_COUNT

        # Validate duration
        if duration_seconds not in [4, 6, 8]:
            logger.warning(f"Invalid duration {duration_seconds}, using {settings.MAX_CLIP_DURATION}s")
            duration_seconds = settings.MAX_CLIP_DURATION

        # Decode base64 image to raw bytes for the SDK
        image_bytes = base64.b64decode(character_image_b64)

        source = types.GenerateVideosSource(
            prompt=prompt,
            image=types.Image(image_bytes=image_bytes, mime_type="image/jpeg"),
        )
        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            person_generation=settings.VEO_PERSON_GENERATION,
            number_of_videos=sample_count,
            generate_audio=generate_audio,
        )

        logger.info(f"Creating Veo video job (prompt length: {len(prompt)} chars)")
        logger.info(f"  Prompt preview: {prompt[:120]}...")
        logger.info(f"  Full prompt: {prompt}")
        logger.debug(f"  Duration: {duration_seconds}s | Resolution: {resolution} | Aspect: {aspect_ratio}")

        try:
            operation = await self.client.aio.models.generate_videos(
                model=self.model_id,
                source=source,
                config=config,
            )

            operation_name = operation.name
            if not operation_name:
                raise VeoAPIError("No operation name returned from Veo API")

            # Cache for later polling
            self._operations[operation_name] = operation

            logger.info(f"Veo job created: {operation_name}")
            return operation_name

        except VeoAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to create Veo video job: {e}")
            raise VeoAPIError(f"Failed to create video job: {str(e)}", detail=str(e))

    async def extend_video_job(
        self,
        prompt: str,
        source_video_gcs_uri: str,
        duration_seconds: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
        sample_count: Optional[int] = None,
        generate_audio: bool = True,
    ) -> str:
        """
        Create a video extension job using Veo's video-to-video mode.

        Extends an existing video by continuing the motion/action.

        Args:
            prompt: Video generation prompt describing the continuation
            source_video_gcs_uri: GCS URI of source video (e.g., gs://bucket/video.mp4)
            duration_seconds: Duration (4, 6, or 8 seconds)
            aspect_ratio: Aspect ratio (9:16, 16:9)
            resolution: Resolution (720p or 1080p)
            sample_count: Number of video variations (1-4)
            generate_audio: Whether to generate audio

        Returns:
            Operation name (string) for polling

        Raises:
            VeoAPIError: If the API request fails
        """
        duration_seconds = duration_seconds if duration_seconds is not None else settings.MAX_CLIP_DURATION
        aspect_ratio = aspect_ratio or settings.VEO_DEFAULT_ASPECT_RATIO
        resolution = resolution or settings.VEO_DEFAULT_RESOLUTION
        sample_count = sample_count if sample_count is not None else settings.VEO_SAMPLE_COUNT

        # Validate duration
        if duration_seconds not in [4, 6, 8]:
            logger.warning(f"Invalid duration {duration_seconds}, using {settings.MAX_CLIP_DURATION}s")
            duration_seconds = settings.MAX_CLIP_DURATION

        source = types.GenerateVideosSource(
            prompt=prompt,
            video=types.Video(uri=source_video_gcs_uri),
        )
        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            person_generation=settings.VEO_PERSON_GENERATION,
            number_of_videos=sample_count,
            generate_audio=generate_audio,
        )

        logger.info(f"Extending video with prompt: {prompt[:100]}...")
        logger.debug(f"  Duration: {duration_seconds}s | Resolution: {resolution} | Aspect: {aspect_ratio}")

        try:
            operation = await self.client.aio.models.generate_videos(
                model=self.model_id,
                source=source,
                config=config,
            )

            operation_name = operation.name
            if not operation_name:
                raise VeoAPIError("No operation name returned from Veo API")

            # Cache for later polling
            self._operations[operation_name] = operation

            logger.info(f"Video extension job created: {operation_name}")
            return operation_name

        except VeoAPIError:
            raise
        except Exception as e:
            logger.error(f"Failed to create video extension job: {e}")
            raise VeoAPIError(f"Failed to extend video: {str(e)}", detail=str(e))

    async def wait_for_completion(
        self,
        operation_id: str,
        timeout: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> Any:
        """
        Poll the operation until completion.

        Args:
            operation_id: Operation name from create_video_job
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            Completed Operation object (use extract_video_urls to get videos)

        Raises:
            TimeoutError: If operation doesn't complete in time
            VeoAPIError: If operation fails
        """
        timeout = timeout if timeout is not None else settings.VIDEO_GENERATION_TIMEOUT
        poll_interval = poll_interval if poll_interval is not None else settings.VEO_POLL_INTERVAL

        logger.info(f"Waiting for Veo job completion: {operation_id}")

        operation = self._operations.get(operation_id)
        if not operation:
            raise VeoAPIError(
                f"Unknown operation: {operation_id}. "
                f"Operation must be created via create_video_job first."
            )

        elapsed = 0
        while elapsed < timeout:
            if operation.done:
                # Check for errors
                if hasattr(operation, "error") and operation.error:
                    error_msg = str(operation.error)
                    logger.error(f"Veo job failed: {error_msg}")
                    raise VeoAPIError(
                        f"Video generation failed: {error_msg}",
                        detail=operation.error,
                    )

                # Check for successful result
                if operation.result:
                    generated = getattr(operation.result, "generated_videos", None) or []
                    logger.info(f"Veo job completed with {len(generated)} video(s)")
                    return operation

                logger.warning(f"Operation done but no result")
                return operation

            logger.debug(f"[{elapsed}s] Polling Veo operation... (not done yet)")
            await asyncio.sleep(poll_interval)

            try:
                operation = await self.client.aio.operations.get(operation=operation)
                self._operations[operation_id] = operation
            except Exception as e:
                logger.error(f"Error polling Veo operation: {e}")
                raise VeoAPIError(f"Failed to poll operation: {str(e)}")

            elapsed += poll_interval

        raise TimeoutError(f"Veo job {operation_id} timed out after {timeout}s")

    def extract_video_urls(self, operation_result: Any) -> List[str]:
        """
        Extract base64-encoded video data from a completed operation.

        Args:
            operation_result: Operation object from wait_for_completion

        Returns:
            List of base64 encoded video strings
        """
        try:
            response = operation_result.result
            if not response:
                logger.warning("No result in operation")
                return []

            generated_videos = getattr(response, "generated_videos", None) or []

            video_b64_list = []
            for gv in generated_videos:
                video = gv.video
                if video and hasattr(video, "video_bytes") and video.video_bytes:
                    video_b64 = base64.b64encode(video.video_bytes).decode("utf-8")
                    video_b64_list.append(video_b64)

            logger.info(f"Extracted {len(video_b64_list)} video(s) from result")
            return video_b64_list

        except Exception as e:
            logger.error(f"Error extracting videos from result: {e}")
            return []

    async def generate_video_complete(
        self,
        prompt: str,
        character_image_b64: str,
        duration_seconds: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
        timeout: Optional[int] = None,
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
