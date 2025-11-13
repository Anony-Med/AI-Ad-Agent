"""Main pipeline for AI Ad Agent - Orchestrates the 8-step workflow."""
import logging
import os
import asyncio
from datetime import datetime
from typing import Optional, List
from app.ad_agent.interfaces.ad_schemas import AdRequest, AdJob, AdJobStatus, VideoClip
from app.ad_agent.agents.prompt_generator import PromptGeneratorAgent
from app.ad_agent.agents.video_generator import VideoGeneratorAgent
from app.ad_agent.agents.creative_advisor import CreativeAdvisorAgent
from app.ad_agent.agents.audio_compositor import AudioCompositorAgent
from app.ad_agent.agents.video_compositor import VideoCompositorAgent
from app.ad_agent.agents.clip_verifier import ClipVerifierAgent
from app.database import get_db
from app.database.gcs_storage import upload_file_to_gcs

logger = logging.getLogger(__name__)


class AdCreationPipeline:
    """
    Orchestrates the complete AI video ad creation workflow.

    NEW Audio-First Workflow (10 steps):
    1. Generate complete voiceover from script (ElevenLabs)
    2. Segment voiceover by script segments (audio analysis)
    3. Generate Veo prompts for each segment (Gemini)
    4. Generate video clips with audio-derived durations (Veo 3.1)
    5. Verify clips match script content (Gemini Vision)
    6. Merge video clips
    7. Get creative enhancement suggestions (Gemini)
    8. Apply creative enhancements (text overlays, effects)
    9. Add background music and sound effects (ElevenLabs + ffmpeg)
    10. Final export and upload

    Key Improvements:
    - Videos are generated to match voiceover duration (perfect lip-sync)
    - No more arbitrary 7-second limits
    - Creative suggestions are actually applied
    - Natural pacing based on speech timing
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        elevenlabs_api_key: Optional[str] = None,
        enable_verification: bool = True,
        verification_threshold: float = 0.6,
    ):
        """
        Initialize pipeline with agents.

        Args:
            gemini_api_key: Google AI API key
            elevenlabs_api_key: ElevenLabs API key
            enable_verification: Whether to verify clips match script
            verification_threshold: Minimum confidence score to pass (0.0-1.0)
        """
        self.prompt_agent = PromptGeneratorAgent(api_key=gemini_api_key)
        self.video_agent = VideoGeneratorAgent()
        self.creative_agent = CreativeAdvisorAgent(api_key=gemini_api_key)
        self.audio_agent = AudioCompositorAgent(api_key=elevenlabs_api_key)
        self.video_compositor = VideoCompositorAgent()
        self.clip_verifier = ClipVerifierAgent(
            api_key=gemini_api_key,
            confidence_threshold=verification_threshold
        )
        self.enable_verification = enable_verification

        # Initialize Firestore if available (optional for testing)
        try:
            self.db = get_db()
        except Exception as e:
            logger.warning(f"Firestore not available: {e}")
            self.db = None

        self.script_segments: List[str] = []  # Store script segments for verification

        # Initialize GCS storage for checkpoint/resume
        from app.database.gcs_storage import get_storage
        self.storage = get_storage()

        # Progress callback for streaming updates (optional)
        self.progress_callback = None

    async def _emit_progress(self, event: str, data: dict):
        """Emit progress event if callback is set."""
        if self.progress_callback:
            try:
                await self.progress_callback(event, data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    async def _get_checkpoint_path(self, job_id: str, user_id: str, filename: str) -> str:
        """Get GCS path for checkpoint file."""
        return f"{user_id}/{job_id}/{filename}"

    async def _checkpoint_exists(self, job_id: str, user_id: str, filename: str) -> bool:
        """Check if checkpoint file exists in GCS."""
        path = await self._get_checkpoint_path(job_id, user_id, filename)
        return await self.storage.blob_exists(path)

    async def _save_checkpoint(self, job_id: str, user_id: str, local_path: str, gcs_filename: str) -> str:
        """Save checkpoint file to GCS and return signed URL."""
        blob_path = await self._get_checkpoint_path(job_id, user_id, gcs_filename)
        await self.storage.upload_from_file(local_path, blob_path)
        signed_url = await self.storage.get_signed_url(blob_path, expiration_days=7)
        logger.info(f"Saved checkpoint: {gcs_filename}")
        return signed_url

    async def _load_checkpoint(self, job_id: str, user_id: str, gcs_filename: str, local_path: str) -> str:
        """Load checkpoint file from GCS to local path."""
        blob_path = await self._get_checkpoint_path(job_id, user_id, gcs_filename)
        await self.storage.download_to_file(blob_path, local_path)
        logger.info(f"Loaded checkpoint: {gcs_filename}")
        return local_path

    async def _save_job(self, job: AdJob) -> None:
        """Save job state to Firestore (create if not exists, update otherwise)."""
        if not self.db:
            logger.warning("Database not available, skipping job save")
            return

        try:
            # Convert AdJob to dict for Firestore
            # Exclude large base64 fields - they're already in GCS
            job_data = {
                "status": job.status.value if hasattr(job.status, 'value') else job.status,
                "progress": job.progress,
                "current_step": job.current_step,
                "error_message": job.error_message,
                "final_video_url": job.final_video_url,
                "merged_video_url": job.merged_video_url,
                "character_image_gcs_url": getattr(job, 'character_image_gcs_url', None),
            }

            # Add optional fields if they exist
            if hasattr(job, 'video_clips') and job.video_clips:
                # Save only metadata, exclude large fields like video_b64
                clips_metadata = []
                for clip in job.video_clips:
                    clip_dict = clip.dict() if hasattr(clip, 'dict') else clip
                    # Remove large base64 video data to avoid Firestore 1MB limit
                    clip_metadata = {k: v for k, v in clip_dict.items() if k != 'video_b64'}
                    clips_metadata.append(clip_metadata)
                job_data["video_clips"] = clips_metadata
            if hasattr(job, 'voiceover_audio_url') and job.voiceover_audio_url:
                job_data["voiceover_audio_url"] = job.voiceover_audio_url
            if hasattr(job, 'creative_suggestions') and job.creative_suggestions:
                job_data["creative_suggestions"] = job.creative_suggestions

            # Check if job exists, create if not
            existing_job = await self.db.get_job(job.job_id, job.user_id)
            if not existing_job:
                # Create new job document
                job_data.update({
                    "job_id": job.job_id,
                    "user_id": job.user_id,
                    "campaign_id": job.campaign_id,
                    "script": job.script,
                    "character_name": job.character_name,
                })
                await self.db.create_job(job.user_id, job_data)
                logger.debug(f"[{job.job_id}] Job created in Firestore")
            else:
                # Update existing job
                await self.db.update_job(job.job_id, **job_data)
                logger.debug(f"[{job.job_id}] Job updated in Firestore")
        except Exception as e:
            logger.error(f"[{job.job_id}] Failed to save job to Firestore: {e}")

    async def create_ad(
        self,
        request: AdRequest,
        user_id: str,
    ) -> AdJob:
        """
        Execute the complete ad creation workflow.

        Args:
            request: Ad creation request
            user_id: User ID

        Returns:
            AdJob with final video URL

        Raises:
            Exception: If any step fails
        """
        job_id = f"ad_{datetime.utcnow().timestamp()}"

        logger.info(f"Starting ad creation pipeline: {job_id}")

        # Reinitialize prompt_agent with storage client, job_id, and user_id for GCS logging
        self.prompt_agent = PromptGeneratorAgent(
            api_key=self.prompt_agent.gemini.api_key,
            storage_client=self.storage,
            job_id=job_id,
            user_id=user_id
        )

        # Upload character image to GCS to avoid Firestore 1MB limit
        character_image_gcs_url = None
        if request.character_image:
            try:
                import base64
                import tempfile

                # Decode base64 and save to temp file
                image_data = base64.b64decode(request.character_image.split(',')[1] if ',' in request.character_image else request.character_image)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                temp_file.write(image_data)
                temp_file.close()

                # Upload to GCS
                gcs_path = f"{user_id}/{job_id}/character_image.png"
                await self.storage.upload_from_file(temp_file.name, gcs_path)
                character_image_gcs_url = await self.storage.get_signed_url(gcs_path, expiration_days=7)

                # Cleanup
                if os.path.exists(temp_file.name):
                    os.remove(temp_file.name)

                logger.info(f"[{job_id}] Uploaded character image to GCS: {gcs_path}")
            except Exception as e:
                logger.error(f"[{job_id}] Failed to upload character image to GCS: {e}")
                # Continue with base64 in memory (not saved to Firestore)

        # Create initial job record (without storing full character_image in Firestore)
        job = AdJob(
            job_id=job_id,
            campaign_id=request.campaign_id,
            user_id=user_id,
            status=AdJobStatus.PENDING,
            script=request.script,
            character_image="",  # Empty to avoid Firestore 1MB limit
            character_image_gcs_url=character_image_gcs_url,
            character_name=request.character_name or "character",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        try:
            # NEW SIMPLIFIED WORKFLOW: Veo-First with Voice Enhancement (5 Steps)
            # Based on proven manual workflow

            # Step 1: Generate Veo Prompts (GPT-style with lip-sync emphasis)
            job = await self._step1_generate_prompts_simple(job, request)

            # Step 2: Generate Videos WITH Audio (Veo built-in lip-sync)
            job = await self._step2_generate_videos_with_audio(job, request)

            # Step 3: Merge Videos
            job = await self._step3_merge_videos_simple(job)

            # Step 4: Enhance Voice with ElevenLabs Voice Changer
            job = await self._step4_enhance_voice(job, request)

            # Step 5: Final Upload and Cleanup
            job = await self._step5_finalize_simple(job, user_id)

            job.status = AdJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.progress = 100

            logger.info(f"Ad creation completed: {job_id}")

        except Exception as e:
            logger.error(f"Ad creation failed: {e}", exc_info=True)
            job.status = AdJobStatus.FAILED
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()

        # Save final job state
        await self._save_job(job)

        return job

    # ========================================================================
    # SIMPLIFIED 5-STEP WORKFLOW (Active)
    # Old 10-step audio-first workflow archived in docs/OLD_CODE_ARCHIVE.md
    # ========================================================================

    async def _step1_generate_prompts_simple(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 1: Generate Veo prompts (GPT-style with lip-sync emphasis)."""
        logger.info(f"[{job.job_id}] Step 1: Generating Veo prompts")

        job.status = AdJobStatus.GENERATING_PROMPTS
        job.current_step = "Generating video prompts..."
        job.progress = 10
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Emit progress event
        await self._emit_progress("step1", {
            "step": 1,
            "message": "Generating video prompts...",
            "progress": 10
        })

        # Generate prompts with script segments
        prompts, segments = await self.prompt_agent.generate_prompts_with_segments(
            script=request.script,
            character_name=request.character_name or "character",
            max_clip_duration=7,
        )

        # Store segments for later use
        self.script_segments = segments

        # Create VideoClip objects
        job.video_clips = [
            VideoClip(
                clip_number=i,
                prompt=prompt,
                script_segment=segment,
                duration=7,  # Veo will handle actual duration
                status="pending",
            )
            for i, (prompt, segment) in enumerate(zip(prompts, segments))
        ]

        logger.info(f"[{job.job_id}] Generated {len(prompts)} Veo prompts")
        job.progress = 20
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Emit completion event
        await self._emit_progress("step1_complete", {
            "step": 1,
            "message": f"Generated {len(prompts)} video prompts",
            "total_clips": len(prompts),
            "progress": 20
        })

        return job

    async def _step2_generate_videos_with_audio(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 2: Generate videos WITH audio (Veo built-in lip-sync) using frame-to-frame continuity."""
        logger.info(f"[{job.job_id}] Step 2: Generating videos with Veo (frame-to-frame continuity)")

        job.status = AdJobStatus.GENERATING_VIDEOS
        job.current_step = "Generating video clips..."
        job.progress = 30
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        import tempfile
        import base64
        from app.ad_agent.utils.video_utils import VideoProcessor

        all_clips = job.video_clips
        total_clips = len(all_clips)
        current_image = request.character_image  # Start with avatar

        # Generate clips sequentially, using last frame of each clip for the next
        for i, clip in enumerate(all_clips):
            logger.info(f"[{job.job_id}] ========== STARTING CLIP {i+1}/{total_clips} ==========")
            logger.info(f"[{job.job_id}] Generating clip {i+1}/{total_clips}")
            logger.info(f"[{job.job_id}]   Prompt: {clip.prompt[:100]}...")
            logger.info(f"[{job.job_id}]   Script: {clip.script_segment}")

            # Emit progress event for this clip
            await self._emit_progress("step2_clip", {
                "step": 2,
                "message": f"Generating clip {i+1}/{total_clips}",
                "current_clip": i + 1,
                "total_clips": total_clips,
                "progress": 30 + int((i / total_clips) * 20)
            })

            # Save prompt to GCS
            prompt_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt")
            prompt_file.write(f"Script: {clip.script_segment}\n\nPrompt: {clip.prompt}")
            prompt_file.close()

            prompt_url = await self._save_checkpoint(
                job.job_id,
                job.user_id,
                prompt_file.name,
                f"prompts/clip_{i}_prompt.txt"
            )
            os.remove(prompt_file.name)
            logger.info(f"[{job.job_id}] Saved prompt to GCS")

            # Generate single clip
            completed_clips = await self.video_agent.wait_for_all_clips(
                clips=await self.video_agent.generate_all_clips(
                    prompts=[clip.prompt],
                    character_image=current_image,
                    duration=7,
                    aspect_ratio=request.aspect_ratio or "16:9",
                    resolution=request.resolution or "720p",
                    max_concurrent=1,
                    clip_number_offset=i,
                ),
                timeout=600,
            )

            completed_clip = completed_clips[0]

            # RETRY LOGIC: If clip failed due to content policy, retry with original avatar
            if completed_clip.status == "failed" and completed_clip.error and "violates Vertex AI's usage guidelines" in completed_clip.error:
                logger.warning(f"[{job.job_id}] Clip {i} failed content policy check, retrying with original avatar...")

                # Retry with original avatar instead of extracted frame
                retry_clips = await self.video_agent.wait_for_all_clips(
                    clips=await self.video_agent.generate_all_clips(
                        prompts=[clip.prompt],
                        character_image=request.character_image,  # Use original avatar
                        duration=7,
                        aspect_ratio=request.aspect_ratio or "16:9",
                        resolution=request.resolution or "720p",
                        max_concurrent=1,
                        clip_number_offset=i,
                    ),
                    timeout=600,
                )

                completed_clip = retry_clips[0]
                if completed_clip.status == "completed":
                    logger.info(f"[{job.job_id}] Clip {i} retry succeeded with original avatar")
                    logger.info(f"[{job.job_id}] Retry clip status: {completed_clip.status}, has_video_b64: {bool(completed_clip.video_b64)}")

                    # CRITICAL CHECK: Ensure retry actually returned video data
                    if not completed_clip.video_b64:
                        logger.error(f"[{job.job_id}] CRITICAL: Retry succeeded but no video_b64 data! Marking as failed.")
                        completed_clip.status = "failed"
                        completed_clip.error = "Retry succeeded but returned no video data"
                else:
                    logger.error(f"[{job.job_id}] Clip {i} retry also failed: {completed_clip.error}")

            all_clips[i] = completed_clip
            logger.info(f"[{job.job_id}] Updated all_clips[{i}] with status: {completed_clip.status}")

            if completed_clip.status == "completed" and completed_clip.video_b64:
                logger.info(f"[{job.job_id}] Starting GCS save for clip {i}")
                try:
                    # Save video to temp file
                    logger.info(f"[{job.job_id}] Decoding base64 video for clip {i}")
                    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
                    video_bytes = base64.b64decode(completed_clip.video_b64)
                    with open(temp_video, 'wb') as f:
                        f.write(video_bytes)
                    logger.info(f"[{job.job_id}] Saved video to temp file: {temp_video}")

                    # Save video to GCS
                    logger.info(f"[{job.job_id}] Uploading clip {i} to GCS...")
                    gcs_url = await self._save_checkpoint(
                        job.job_id,
                        job.user_id,
                        temp_video,
                        f"clips/clip_{i}.mp4"
                    )
                    completed_clip.gcs_url = gcs_url
                    logger.info(f"[{job.job_id}] Saved clip {i} to GCS: {gcs_url}")

                    # Extract last frame for next clip (if not last clip)
                    if i < total_clips - 1:
                        logger.info(f"[{job.job_id}] Extracting last frame from clip {i} for clip {i+1}")
                        try:
                            last_frame_b64 = VideoProcessor.extract_frame_to_base64(temp_video)
                            current_image = f"data:image/jpeg;base64,{last_frame_b64}"
                            logger.info(f"[{job.job_id}] Extracted last frame ({len(last_frame_b64)} chars base64)")
                        except Exception as frame_error:
                            logger.error(f"[{job.job_id}] Frame extraction failed for clip {i}, using original avatar for next clip: {frame_error}")
                            # CRITICAL FIX: Use original avatar instead of hanging the pipeline
                            current_image = request.character_image
                            logger.info(f"[{job.job_id}] Falling back to original avatar for clip {i+1}")
                    else:
                        logger.info(f"[{job.job_id}] Clip {i} is the last clip, skipping frame extraction")

                    # Cleanup
                    logger.info(f"[{job.job_id}] Cleaning up temp file for clip {i}")
                    if os.path.exists(temp_video):
                        os.remove(temp_video)
                    logger.info(f"[{job.job_id}] Clip {i} processing completed successfully")

                except Exception as e:
                    logger.error(f"[{job.job_id}] Failed to save clip {i}: {e}", exc_info=True)
                    completed_clip.status = "failed"
                    completed_clip.error = str(e)
            else:
                logger.warning(f"[{job.job_id}] Skipping GCS save for clip {i} - status: {completed_clip.status}, has_video_b64: {bool(completed_clip.video_b64)}")

            # Update progress
            progress = 30 + int(((i + 1) / total_clips) * 20)
            job.progress = progress
            job.updated_at = datetime.utcnow()
            logger.info(f"[{job.job_id}] Saving job progress: {progress}%")
            await self._save_job(job)
            logger.info(f"[{job.job_id}] Completed iteration {i+1}/{total_clips}, moving to next clip")

        logger.info(f"[{job.job_id}] Finished processing all {total_clips} clips")
        job.video_clips = all_clips
        successful = sum(1 for c in job.video_clips if c.status == "completed")
        logger.info(f"[{job.job_id}] Generated {successful}/{total_clips} videos with frame-to-frame continuity")

        job.progress = 50
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        return job

    async def _step3_merge_videos_simple(self, job: AdJob) -> AdJob:
        """Step 3: Merge all video clips."""
        logger.info(f"[{job.job_id}] Step 3: Merging video clips")

        job.status = AdJobStatus.MERGING_VIDEOS
        job.current_step = "Merging video clips..."
        job.progress = 60
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Emit progress event
        await self._emit_progress("step3", {
            "step": 3,
            "message": "Merging video clips...",
            "progress": 60
        })

        # Get GCS URLs of completed clips
        video_urls = [
            clip.gcs_url
            for clip in job.video_clips
            if clip.status == "completed" and clip.gcs_url
        ]

        if not video_urls:
            raise RuntimeError("No video clips available for merging")

        # Merge videos
        merged_path = await self.video_compositor.merge_video_clips(
            video_urls=video_urls,
        )

        # Upload to GCS
        blob_name = f"{job.user_id}/{job.job_id}/merged_video.mp4"
        merged_url = await upload_file_to_gcs(merged_path, blob_name)

        job.merged_video_url = merged_url

        # Cleanup
        if os.path.exists(merged_path):
            os.remove(merged_path)

        logger.info(f"[{job.job_id}] Videos merged: {merged_url}")
        job.progress = 70
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        return job

    async def _step4_enhance_voice(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 4: Enhance voice with ElevenLabs Voice Changer."""
        import tempfile
        import httpx

        logger.info(f"[{job.job_id}] Step 4: Enhancing voice with Voice Changer")

        job.status = AdJobStatus.ENHANCING_VOICE
        job.current_step = "Enhancing voice with ElevenLabs..."
        job.progress = 80
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Emit progress event
        await self._emit_progress("step4", {
            "step": 4,
            "message": "Enhancing voice with ElevenLabs...",
            "progress": 80
        })

        # Get voice ID
        voice_id = None
        if request.voice_id:
            voice_id = request.voice_id
        else:
            # Try to find "Heather Bryant" voice
            voice_id = await self.audio_agent.elevenlabs.find_voice_by_name("Heather Bryant")
            if not voice_id:
                logger.warning("Heather Bryant voice not found, skipping voice enhancement")
                job.final_video_url = job.merged_video_url
                return job

        # STEP 4a: Extract audio from video (much smaller file ~3MB vs ~30MB video)
        # Pass URL directly to extract_audio_from_video - it will download internally
        logger.info(f"[{job.job_id}] Extracting audio from video URL...")
        extracted_audio = await self.audio_agent.extract_audio_from_video(job.merged_video_url)

        # Get file size for logging
        audio_size = os.path.getsize(extracted_audio)
        logger.info(f"[{job.job_id}] Extracted audio: {audio_size} bytes (~{audio_size/1024/1024:.1f} MB)")

        # STEP 4b: Apply voice changer to audio only (not video)
        logger.info(f"[{job.job_id}] Enhancing audio with Voice Changer...")
        enhanced_audio_bytes = await self.audio_agent.elevenlabs.voice_changer(
            audio_file_path=extracted_audio,  # Send audio file (AAC in .m4a)
            voice_id=voice_id,
        )

        # Save enhanced audio (ElevenLabs returns MP3)
        temp_enhanced_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        with open(temp_enhanced_audio, 'wb') as f:
            f.write(enhanced_audio_bytes)

        logger.info(f"[{job.job_id}] Voice enhancement complete")

        # STEP 4c: Download merged video and replace audio track
        logger.info(f"[{job.job_id}] Downloading merged video for audio replacement...")

        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        async with httpx.AsyncClient() as client:
            response = await client.get(job.merged_video_url)
            response.raise_for_status()
            with open(temp_video, 'wb') as f:
                f.write(response.content)

        logger.info(f"[{job.job_id}] Replacing audio track in video...")
        enhanced_video = await self.audio_agent.replace_audio_track(
            video_path=temp_video,
            audio_path=temp_enhanced_audio,
        )

        # Upload enhanced video
        blob_name = f"{job.user_id}/{job.job_id}/enhanced_video.mp4"
        enhanced_url = await upload_file_to_gcs(enhanced_video, blob_name)

        job.final_video_url = enhanced_url

        # Cleanup
        for path in [temp_video, extracted_audio, temp_enhanced_audio, enhanced_video]:
            if os.path.exists(path):
                os.remove(path)

        logger.info(f"[{job.job_id}] Voice enhanced: {enhanced_url}")
        job.progress = 90
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        return job

    async def _step5_finalize_simple(self, job: AdJob, user_id: str) -> AdJob:
        """Step 5: Final upload and cleanup."""
        logger.info(f"[{job.job_id}] Step 5: Finalizing")

        job.status = AdJobStatus.FINALIZING
        job.current_step = "Finalizing..."
        job.progress = 95
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Emit progress event
        await self._emit_progress("step5", {
            "step": 5,
            "message": "Finalizing...",
            "progress": 95
        })

        # Create asset record
        if self.db:
            asset_data = {
                "campaign_id": job.campaign_id,
                "job_id": job.job_id,
                "ad_type": "video",
                "model": "veo-3.1-generate-preview",
                "prompt": job.script,
                "url": job.final_video_url,
                "aspect_ratio": "16:9",
                "duration": len(job.video_clips) * 7,
                "tags": ["ai-generated", "veo-first-workflow"],
                "created_at": job.created_at,
            }

            asset = await self.db.create_asset(user_id, asset_data)
            logger.info(f"[{job.job_id}] Asset created: {asset.get('id')}")

        job.progress = 100
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        logger.info(f"[{job.job_id}] Ad creation complete!")
        return job
