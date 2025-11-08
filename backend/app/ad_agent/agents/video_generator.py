"""Agent for generating videos using Unified API (Veo 3.1)."""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
from app.ad_agent.interfaces.ad_schemas import VideoClip

logger = logging.getLogger(__name__)


class VideoGeneratorAgent:
    """Generates videos using Veo 3.1 via Unified API."""

    def __init__(self):
        """Initialize with Unified API client."""
        self.client = unified_api_client

    async def generate_video_clip(
        self,
        prompt: str,
        character_image: str,
        clip_number: int,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
    ) -> VideoClip:
        """
        Generate a single video clip using Veo 3.1.

        Args:
            prompt: Veo prompt
            character_image: Base64 encoded character reference image
            clip_number: Clip number/index
            duration: Duration in seconds (4, 6, or 8 for Veo)
            aspect_ratio: Aspect ratio
            resolution: Video resolution

        Returns:
            VideoClip with job info
        """
        logger.info(f"Generating clip {clip_number} with Veo 3.1")

        # Adjust duration to valid Veo values
        if duration > 6:
            duration = 8
        elif duration > 4:
            duration = 6
        else:
            duration = 4

        try:
            # Create video job via Unified API
            video_params = {
                "model": "veo-3.1-generate-preview",
                "mode": "text-to-video",
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "params": {
                    "reference_images": [character_image],  # Character reference
                },
            }

            response = await self.client.create_video_job(**video_params)
            job_id = response.get("job_id") or response.get("id")

            if not job_id:
                raise ValueError("No job_id returned from Unified API")

            logger.info(f"Clip {clip_number} job created: {job_id}")

            return VideoClip(
                clip_number=clip_number,
                prompt=prompt,
                veo_job_id=job_id,
                duration=duration,
                status="queued",
            )

        except UnifiedAPIError as e:
            logger.error(f"Failed to create video job for clip {clip_number}: {e.message}")
            return VideoClip(
                clip_number=clip_number,
                prompt=prompt,
                duration=duration,
                status="failed",
                error=e.message,
            )
        except Exception as e:
            logger.error(f"Unexpected error generating clip {clip_number}: {e}")
            return VideoClip(
                clip_number=clip_number,
                prompt=prompt,
                duration=duration,
                status="failed",
                error=str(e),
            )

    async def wait_for_video_completion(
        self,
        job_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """
        Poll video job until completion.

        Args:
            job_id: Video job ID
            timeout: Max wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            Job result with video URL

        Raises:
            TimeoutError: If job doesn't complete in time
            UnifiedAPIError: If job fails
        """
        logger.info(f"Waiting for video job {job_id} to complete")

        elapsed = 0
        while elapsed < timeout:
            try:
                result = await self.client.get_video_job_status(job_id)
                status = result.get("status", "").lower()

                logger.debug(f"Job {job_id} status: {status}")

                if status == "succeeded" or status == "completed":
                    # Extract video URL from artifacts
                    artifacts = result.get("artifacts", [])
                    if artifacts:
                        video_url = artifacts[0].get("url")
                        logger.info(f"Video job {job_id} completed: {video_url}")
                        return {
                            "status": "succeeded",
                            "video_url": video_url,
                            "result": result,
                        }
                    else:
                        raise ValueError("No video URL in completed job")

                elif status == "failed" or status == "error":
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Video job {job_id} failed: {error_msg}")
                    raise UnifiedAPIError(f"Video generation failed: {error_msg}")

                # Still processing, wait and retry
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            except UnifiedAPIError:
                raise
            except Exception as e:
                logger.error(f"Error checking job status: {e}")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise TimeoutError(f"Video job {job_id} timed out after {timeout}s")

    async def generate_all_clips(
        self,
        prompts: List[str],
        character_image: str,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        max_concurrent: int = 3,
    ) -> List[VideoClip]:
        """
        Generate all video clips concurrently.

        Args:
            prompts: List of Veo prompts
            character_image: Character reference image
            duration: Duration per clip
            aspect_ratio: Aspect ratio
            resolution: Resolution
            max_concurrent: Max concurrent video generation jobs

        Returns:
            List of VideoClip objects with job IDs
        """
        logger.info(f"Generating {len(prompts)} video clips (max {max_concurrent} concurrent)")

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_limit(prompt: str, clip_num: int) -> VideoClip:
            async with semaphore:
                return await self.generate_video_clip(
                    prompt=prompt,
                    character_image=character_image,
                    clip_number=clip_num,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )

        # Generate all clips concurrently with limit
        tasks = [
            generate_with_limit(prompt, i)
            for i, prompt in enumerate(prompts)
        ]

        clips = await asyncio.gather(*tasks)

        successful = sum(1 for c in clips if c.status != "failed")
        logger.info(f"Created {successful}/{len(clips)} video jobs successfully")

        return clips

    async def wait_for_all_clips(
        self,
        clips: List[VideoClip],
        timeout: int = 600,
    ) -> List[VideoClip]:
        """
        Wait for all video clips to complete.

        Args:
            clips: List of VideoClip objects
            timeout: Max wait time per clip

        Returns:
            Updated list of VideoClip objects with URLs
        """
        logger.info(f"Waiting for {len(clips)} video clips to complete")

        async def wait_for_clip(clip: VideoClip) -> VideoClip:
            if clip.status == "failed" or not clip.veo_job_id:
                return clip

            try:
                result = await self.wait_for_video_completion(
                    job_id=clip.veo_job_id,
                    timeout=timeout,
                )

                clip.video_url = result["video_url"]
                clip.status = "completed"
                logger.info(f"Clip {clip.clip_number} completed")

            except Exception as e:
                logger.error(f"Clip {clip.clip_number} failed: {e}")
                clip.status = "failed"
                clip.error = str(e)

            return clip

        # Wait for all clips concurrently
        updated_clips = await asyncio.gather(*[wait_for_clip(c) for c in clips])

        successful = sum(1 for c in updated_clips if c.status == "completed")
        logger.info(f"Completed {successful}/{len(updated_clips)} video clips")

        return updated_clips
