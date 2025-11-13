"""Agent for generating videos using Direct Veo 3.1 API."""
import logging
import asyncio
import base64
from typing import List, Dict, Any, Optional
from app.services.veo_client import direct_veo_client, VeoAPIError
from app.ad_agent.interfaces.ad_schemas import VideoClip
from app.utils.image_utils import resize_image_for_veo, get_image_info

logger = logging.getLogger(__name__)


class VideoGeneratorAgent:
    """Generates videos using Veo 3.1 via Direct Google API."""

    def __init__(self):
        """
        Initialize with Direct Veo API client.

        Uses Google default credentials (works with gcloud, service accounts, Cloud Run).
        """
        self.client = direct_veo_client
        logger.info("VideoGeneratorAgent initialized with Direct Veo API")

    async def generate_video_clip(
        self,
        prompt: str,
        character_image: str,
        clip_number: int,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        sample_count: int = 1,  # Number of videos to generate (1-4). Set to 1 for cost efficiency.
    ) -> VideoClip:
        """
        Generate a single video clip using Veo 3.1 image-to-video mode.

        Args:
            prompt: Veo prompt describing the action/motion
            character_image: Base64 encoded character reference image
            clip_number: Clip number/index
            duration: Duration in seconds (4, 6, or 8 for Veo)
            aspect_ratio: Aspect ratio
            resolution: Video resolution (720p or 1080p)
            sample_count: Number of video variations to generate (1-4, default 1). Increase for multiple options.

        Returns:
            VideoClip with job info
        """
        logger.info(f"Generating clip {clip_number} with Direct Veo API (sample_count={sample_count})")
        logger.info(f"DEBUG VIDEO_GEN: generate_video_clip called with clip_number={clip_number}")

        # Adjust duration to valid Veo values
        if duration > 6:
            duration = 8
        elif duration > 4:
            duration = 6
        else:
            duration = 4

        try:
            # Optimize character image for Veo API
            # Veo API has payload limits, so resize to 768px max
            logger.info(f"Optimizing character image for clip {clip_number}...")
            img_info = get_image_info(character_image)
            logger.debug(f"Original image: {img_info.get('width')}x{img_info.get('height')}, {img_info.get('size_kb', 0):.1f} KB")

            optimized_image = resize_image_for_veo(
                character_image,
                max_size=768,  # Good balance of quality and size
                quality=85,
            )

            # Create video job via Direct Veo API
            # Generate multiple samples - Veo will return fastest one
            operation_id = await self.client.create_video_job(
                prompt=prompt,
                character_image_b64=optimized_image,
                duration_seconds=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                sample_count=sample_count,  # Generate multiple videos
                generate_audio=True,
            )

            logger.info(f"Clip {clip_number} job created with {sample_count} video(s): {operation_id}")

            created_clip = VideoClip(
                clip_number=clip_number,
                prompt=prompt,
                veo_job_id=operation_id,
                duration=duration,
                status="queued",
            )
            logger.info(f"DEBUG VIDEO_GEN: Created VideoClip object with clip_number={created_clip.clip_number}")
            return created_clip

        except VeoAPIError as e:
            error_detail = f"{e.message}"
            if e.detail:
                error_detail += f" | Detail: {e.detail}"
            logger.error(f"Failed to create video job for clip {clip_number}: {error_detail}")
            return VideoClip(
                clip_number=clip_number,
                prompt=prompt,
                duration=duration,
                status="failed",
                error=error_detail,
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

    async def generate_clip(
        self,
        prompt: str,
        character_image: str,
        clip_number: int,
        script_segment: str,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
    ) -> VideoClip:
        """
        Alias for generate_video_clip with script_segment parameter.

        Args:
            prompt: Veo prompt (visual description)
            character_image: Base64 encoded character reference image
            clip_number: Clip number/index
            script_segment: Corresponding script text (what the avatar should say)
            duration: Duration in seconds
            aspect_ratio: Aspect ratio
            resolution: Video resolution

        Returns:
            VideoClip with job info
        """
        # Combine visual prompt with script for Veo
        # This ensures the avatar speaks the EXACT script text via lip-sync
        combined_prompt = f'{prompt} The character speaks: "{script_segment}"'

        clip = await self.generate_video_clip(
            prompt=combined_prompt,
            character_image=character_image,
            clip_number=clip_number,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        clip.script_segment = script_segment
        return clip

    async def wait_for_video_completion(
        self,
        job_id: str,
        timeout: int = 600,
        poll_interval: int = 10,
        return_all_videos: bool = False,
    ) -> Dict[str, Any]:
        """
        Poll video job until completion.

        Args:
            job_id: Video operation ID
            timeout: Max wait time in seconds
            poll_interval: Seconds between polls
            return_all_videos: If True, return all generated videos. If False, return only first.

        Returns:
            Job result with video data

        Raises:
            TimeoutError: If job doesn't complete in time
            VeoAPIError: If job fails
        """
        logger.info(f"Waiting for video job {job_id} to complete")

        try:
            result = await self.client.wait_for_completion(
                operation_id=job_id,
                timeout=timeout,
                poll_interval=poll_interval,
            )

            # Extract video data
            videos = self.client.extract_video_urls(result)
            if videos:
                if return_all_videos:
                    # Return all videos
                    logger.info(f"Video job {job_id} completed with {len(videos)} video(s)")
                    return {
                        "status": "succeeded",
                        "videos": videos,  # List of base64 strings
                        "result": result,
                    }
                else:
                    # Return first video (legacy behavior)
                    logger.info(f"Video job {job_id} completed successfully")
                    return {
                        "status": "succeeded",
                        "video_b64": videos[0],
                        "result": result,
                    }
            else:
                raise VeoAPIError("Job completed but no video generated")

        except TimeoutError as e:
            logger.error(f"Video job {job_id} timed out: {e}")
            raise
        except VeoAPIError as e:
            logger.error(f"Video job {job_id} failed: {e}")
            raise

    async def generate_all_clips(
        self,
        prompts: List[str],
        character_image: str,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        max_concurrent: int = 3,
        clip_number_offset: int = 0,
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
            clip_number_offset: Starting clip number (for batch processing)

        Returns:
            List of VideoClip objects with job IDs
        """
        logger.info(f"Generating {len(prompts)} video clips (max {max_concurrent} concurrent)")
        logger.info(f"DEBUG: clip_number_offset={clip_number_offset}")

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
        tasks = []
        for i, prompt in enumerate(prompts):
            clip_num = clip_number_offset + i
            logger.info(f"DEBUG: Creating task for clip {clip_num} (offset={clip_number_offset}, i={i})")
            tasks.append(generate_with_limit(prompt, clip_num))

        clips = await asyncio.gather(*tasks)

        successful = sum(1 for c in clips if c.status != "failed")
        logger.info(f"Created {successful}/{len(clips)} video jobs successfully")

        return clips

    async def wait_for_all_clips(
        self,
        clips: List[VideoClip],
        timeout: int = 600,
        max_retries: int = 3,
        character_image: str = None,
        prompts: List[str] = None,
        duration: int = 7,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
    ) -> List[VideoClip]:
        """
        Wait for all video clips to complete with automatic retry on timeout.

        Args:
            clips: List of VideoClip objects
            timeout: Max wait time per clip attempt
            max_retries: Max retry attempts per clip (default: 3)
            character_image: Character image for retry (optional)
            prompts: List of prompts for retry (optional, must match clips length)
            duration: Duration for retry
            aspect_ratio: Aspect ratio for retry
            resolution: Resolution for retry

        Returns:
            Updated list of VideoClip objects with video data
        """
        logger.info(f"Waiting for {len(clips)} video clips to complete (max {max_retries} retries per clip)")

        async def wait_for_clip_with_retry(clip: VideoClip, clip_prompt: str = None) -> VideoClip:
            """Wait for clip with automatic retry on timeout."""
            if clip.status == "failed" or not clip.veo_job_id:
                return clip

            for attempt in range(max_retries):
                try:
                    logger.info(f"Clip {clip.clip_number}: Attempt {attempt + 1}/{max_retries}")

                    result = await self.wait_for_video_completion(
                        job_id=clip.veo_job_id,
                        timeout=timeout,
                        return_all_videos=True,  # Get all videos (default: 1, configurable via sample_count)
                    )

                    # Extract video(s) from response (default: 1 video, or more if sample_count > 1)
                    videos = result.get("videos", [])
                    if videos and len(videos) > 0:
                        # Use the first video (when sample_count=1, there's only one; when >1, use first)
                        clip.video_b64 = videos[0]
                        clip.status = "completed"
                        logger.info(f"✅ Clip {clip.clip_number} completed on attempt {attempt + 1} ({len(videos)} video(s) received)")
                        return clip

                    # Legacy fallback for single video response
                    if "video_b64" in result:
                        clip.video_b64 = result["video_b64"]
                        clip.status = "completed"
                        logger.info(f"✅ Clip {clip.clip_number} completed on attempt {attempt + 1}")
                        return clip

                    # No videos generated
                    raise VeoAPIError("No videos in response")

                except TimeoutError as e:
                    logger.warning(f"⏱️ Clip {clip.clip_number} timed out on attempt {attempt + 1}/{max_retries}")

                    # If not last attempt, create a NEW Veo job with same prompt
                    if attempt < max_retries - 1 and character_image and clip_prompt:
                        logger.info(f"🔄 Retrying clip {clip.clip_number} with a NEW Veo request...")

                        try:
                            # Create new video job
                            new_clip = await self.generate_video_clip(
                                prompt=clip_prompt,
                                character_image=character_image,
                                clip_number=clip.clip_number,
                                duration=duration,
                                aspect_ratio=aspect_ratio,
                                resolution=resolution,
                            )

                            if new_clip.status != "failed":
                                # Update clip with new job ID
                                clip.veo_job_id = new_clip.veo_job_id
                                logger.info(f"Created new Veo job for clip {clip.clip_number}: {clip.veo_job_id}")
                            else:
                                logger.error(f"Failed to create retry job for clip {clip.clip_number}: {new_clip.error}")
                                clip.status = "failed"
                                clip.error = f"Retry job creation failed: {new_clip.error}"
                                return clip

                        except Exception as retry_error:
                            logger.error(f"Failed to create retry job for clip {clip.clip_number}: {retry_error}")
                            clip.status = "failed"
                            clip.error = f"Retry failed: {str(retry_error)}"
                            return clip
                    else:
                        # Last attempt or missing retry params
                        if not character_image or not clip_prompt:
                            logger.warning(f"Cannot retry clip {clip.clip_number}: missing retry parameters")
                        logger.error(f"❌ Clip {clip.clip_number} failed after {max_retries} attempts")
                        clip.status = "failed"
                        clip.error = f"Timeout after {max_retries} attempts"
                        return clip

                except Exception as e:
                    logger.error(f"Clip {clip.clip_number} failed on attempt {attempt + 1}: {e}")

                    # TASK 4: Retry ALL errors (not just timeout)
                    # Check if this is a content policy error
                    error_str = str(e).lower()
                    is_content_policy = any(phrase in error_str for phrase in [
                        "safety filter", "blocked by", "violates", "content policy",
                        "usage guidelines", "inappropriate content"
                    ])

                    # If not last attempt, retry with new Veo job
                    if attempt < max_retries - 1 and character_image and clip_prompt:
                        if is_content_policy:
                            logger.warning(f"🔄 Clip {clip.clip_number}: Content policy error - retrying with same prompt (attempt {attempt + 2}/{max_retries})")
                        else:
                            logger.warning(f"🔄 Clip {clip.clip_number}: Error occurred - retrying anyway (need clip on any basis) (attempt {attempt + 2}/{max_retries})")

                        try:
                            # Create new video job with same parameters
                            new_clip = await self.generate_video_clip(
                                prompt=clip_prompt,
                                character_image=character_image,
                                clip_number=clip.clip_number,
                                duration=duration,
                                aspect_ratio=aspect_ratio,
                                resolution=resolution,
                            )

                            if new_clip.status != "failed":
                                # Update clip with new job ID and continue retry loop
                                clip.veo_job_id = new_clip.veo_job_id
                                logger.info(f"Created new Veo job for clip {clip.clip_number}: {clip.veo_job_id}")
                            else:
                                logger.error(f"Failed to create retry job for clip {clip.clip_number}: {new_clip.error}")
                                # Don't return yet - let the retry loop continue
                                if attempt >= max_retries - 1:
                                    clip.status = "failed"
                                    clip.error = f"Retry job creation failed: {new_clip.error}"
                                    return clip

                        except Exception as retry_error:
                            logger.error(f"Failed to create retry job for clip {clip.clip_number}: {retry_error}")
                            # Don't return yet - let the retry loop continue
                            if attempt >= max_retries - 1:
                                clip.status = "failed"
                                clip.error = f"Retry failed: {str(retry_error)}"
                                return clip
                    else:
                        # Last attempt or missing retry params
                        if not character_image or not clip_prompt:
                            logger.warning(f"Cannot retry clip {clip.clip_number}: missing retry parameters")
                        logger.error(f"❌ Clip {clip.clip_number} failed after {max_retries} attempts: {str(e)}")
                        clip.status = "failed"
                        clip.error = f"Failed after {max_retries} attempts: {str(e)}"
                        return clip

            return clip

        # Wait for all clips with retry support
        tasks = []
        for i, clip in enumerate(clips):
            clip_prompt = prompts[i] if prompts and i < len(prompts) else None
            tasks.append(wait_for_clip_with_retry(clip, clip_prompt))

        updated_clips = await asyncio.gather(*tasks)

        successful = sum(1 for c in updated_clips if c.status == "completed")
        logger.info(f"Completed {successful}/{len(updated_clips)} video clips")

        return updated_clips
