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

    9-Step Workflow (with verification):
    1. Analyze script and generate Veo prompts + script segments (Gemini)
    2. Generate video clips with Veo 3.1
    2.5. Verify clips match script content (Gemini Vision)
    3. Merge video clips
    4. Get creative enhancement suggestions (Gemini)
    5. Generate voiceover (ElevenLabs)
    6. Replace audio with voiceover (ffmpeg)
    7. Add sound effects and background music (ElevenLabs + ffmpeg)
    8. Final export and upload
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
        self.db = get_db()
        self.script_segments: List[str] = []  # Store script segments for verification

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

        # Create initial job record
        job = AdJob(
            job_id=job_id,
            campaign_id=request.campaign_id,
            user_id=user_id,
            status=AdJobStatus.PENDING,
            script=request.script,
            character_image=request.character_image,
            character_name=request.character_name or "character",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        try:
            # Step 1: Generate Veo Prompts + Script Segments
            job = await self._step1_generate_prompts(job, request)

            # Step 2: Generate Video Clips
            job = await self._step2_generate_videos(job, request)

            # Step 2.5: Verify Clips Match Script (Optional)
            if self.enable_verification:
                job = await self._step2_5_verify_clips(job)

            # Step 3: Merge Videos
            job = await self._step3_merge_videos(job)

            # Step 4: Get Creative Suggestions
            job = await self._step4_get_suggestions(job, request)

            # Step 5-7: Audio Enhancement (Voice + Music + SFX)
            job = await self._step567_add_audio(job, request)

            # Step 8: Final Upload
            job = await self._step8_finalize(job, user_id)

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

    async def _step1_generate_prompts(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 1: Generate Veo 3.1 prompts + script segments from script."""
        logger.info(f"[{job.job_id}] Step 1: Generating Veo prompts and script segments")

        job.status = AdJobStatus.GENERATING_PROMPTS
        job.current_step = "Analyzing script and generating video prompts..."
        job.progress = 10
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Generate prompts WITH script segments for verification
        prompts, segments = await self.prompt_agent.generate_prompts_with_segments(
            script=request.script,
            character_name=request.character_name,
            max_clip_duration=7,
        )

        job.veo_prompts = prompts
        self.script_segments = segments  # Store for later verification
        job.progress = 20
        job.updated_at = datetime.utcnow()

        logger.info(f"[{job.job_id}] Generated {len(prompts)} Veo prompts with script segments")
        return job

    async def _step2_generate_videos(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 2: Generate videos with Veo 3.1."""
        logger.info(f"[{job.job_id}] Step 2: Generating {len(job.veo_prompts)} video clips")

        job.status = AdJobStatus.GENERATING_VIDEOS
        job.current_step = f"Generating {len(job.veo_prompts)} video clips with Veo 3.1..."
        job.progress = 30
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Generate all clips
        clips = await self.video_agent.generate_all_clips(
            prompts=job.veo_prompts,
            character_image=request.character_image,
            duration=7,
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            max_concurrent=3,
        )

        job.video_clips = clips
        job.progress = 40
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Wait for all clips to complete
        job.current_step = "Waiting for videos to render..."
        await self._save_job(job)

        completed_clips = await self.video_agent.wait_for_all_clips(
            clips=clips,
            timeout=600,
        )

        job.video_clips = completed_clips
        job.progress = 50
        job.updated_at = datetime.utcnow()

        # Check if any clips failed
        failed = [c for c in completed_clips if c.status != "completed"]
        if failed:
            logger.warning(f"[{job.job_id}] {len(failed)} clips failed")
            # Could retry failed clips here

        successful = [c for c in completed_clips if c.status == "completed"]
        logger.info(f"[{job.job_id}] {len(successful)} clips completed successfully")

        if not successful:
            raise RuntimeError("No video clips were generated successfully")

        return job

    async def _step2_5_verify_clips(self, job: AdJob) -> AdJob:
        """Step 2.5: Verify clips match script content using Gemini Vision."""
        logger.info(f"[{job.job_id}] Step 2.5: Verifying clips match script segments")

        job.status = AdJobStatus.VERIFYING_CLIPS
        job.current_step = "Verifying video clips match script content..."
        job.progress = 52
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Only verify completed clips
        completed_clips = [c for c in job.video_clips if c.status == "completed" and c.video_url]

        if not completed_clips:
            logger.warning(f"[{job.job_id}] No completed clips to verify")
            return job

        # Verify all clips
        verified_clips = await self.clip_verifier.verify_all_clips(
            clips=completed_clips,
            script_segments=self.script_segments,
        )

        # Update job with verified clips (preserves verification results)
        for i, verified_clip in enumerate(verified_clips):
            for j, job_clip in enumerate(job.video_clips):
                if job_clip.clip_number == verified_clip.clip_number:
                    job.video_clips[j] = verified_clip
                    break

        # Get verification summary
        summary = self.clip_verifier.get_verification_summary(verified_clips)

        logger.info(
            f"[{job.job_id}] Verification complete: "
            f"{summary['verified']}/{summary['total_clips']} verified "
            f"(avg confidence: {summary['avg_confidence']:.2f})"
        )

        # Log warnings for failed clips
        failed_clips = self.clip_verifier.get_failed_clips(verified_clips)
        if failed_clips:
            logger.warning(f"[{job.job_id}] {len(failed_clips)} clips failed verification:")
            for clip in failed_clips:
                if clip.verification:
                    logger.warning(
                        f"  - Clip {clip.clip_number}: "
                        f"confidence={clip.verification.confidence_score:.2f}, "
                        f"feedback: {clip.verification.alignment_feedback[:100]}"
                    )

        job.progress = 55
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        return job

    async def _step3_merge_videos(self, job: AdJob) -> AdJob:
        """Step 3: Merge all video clips."""
        logger.info(f"[{job.job_id}] Step 3: Merging video clips")

        job.status = AdJobStatus.MERGING_VIDEOS
        job.current_step = "Merging video clips..."
        job.progress = 60
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Get URLs of completed clips
        video_urls = [
            clip.video_url
            for clip in job.video_clips
            if clip.status == "completed" and clip.video_url
        ]

        if not video_urls:
            raise RuntimeError("No video URLs available for merging")

        # Merge videos
        merged_path = await self.video_compositor.merge_video_clips(
            video_urls=video_urls,
        )

        # Upload to GCS temporarily
        blob_name = f"{job.user_id}/{job.job_id}/merged_video.mp4"
        merged_url = await upload_file_to_gcs(merged_path, blob_name)

        job.merged_video_url = merged_url
        job.progress = 70
        job.updated_at = datetime.utcnow()

        logger.info(f"[{job.job_id}] Videos merged: {merged_url}")

        # Cleanup local file
        if os.path.exists(merged_path):
            os.remove(merged_path)

        return job

    async def _step4_get_suggestions(self, job: AdJob, request: AdRequest) -> AdJob:
        """Step 4: Get creative enhancement suggestions."""
        logger.info(f"[{job.job_id}] Step 4: Getting creative suggestions")

        job.status = AdJobStatus.GETTING_SUGGESTIONS
        job.current_step = "Analyzing video for creative enhancements..."
        job.progress = 75
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        suggestions = await self.creative_agent.get_suggestions(
            script=request.script,
            video_description=f"Video ad with {len(job.video_clips)} clips",
        )

        job.creative_suggestions = suggestions
        job.updated_at = datetime.utcnow()

        logger.info(f"[{job.job_id}] Creative suggestions generated")
        return job

    async def _step567_add_audio(self, job: AdJob, request: AdRequest) -> AdJob:
        """Steps 5-7: Generate voiceover + Music + SFX."""
        logger.info(f"[{job.job_id}] Steps 5-7: Generating complete audio layers")

        job.status = AdJobStatus.ENHANCING_VOICE
        job.current_step = "Generating voiceover with ElevenLabs..."
        job.progress = 75
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        voiceover_path = None
        music_path = None
        sfx_path = None

        try:
            # STEP 5: Generate complete script voiceover with ElevenLabs
            logger.info(f"[{job.job_id}] Step 5: Generating voiceover for entire script")
            voiceover_path = await self.audio_agent.generate_voiceover(
                script=request.script,
                voice_id=request.voice_id,
                voice_name=request.character_name,
            )

            job.progress = 80
            job.current_step = "Generating background music..."
            job.updated_at = datetime.utcnow()
            await self._save_job(job)

            # STEP 7a: Generate background music if requested
            if request.background_music_prompt:
                logger.info(f"[{job.job_id}] Step 7: Generating background music")
                music_path = await self.audio_agent.generate_background_music(
                    prompt=request.background_music_prompt,
                )

            job.progress = 82
            job.current_step = "Generating sound effects..."
            job.updated_at = datetime.utcnow()
            await self._save_job(job)

            # STEP 7b: Generate sound effects if requested
            if request.add_sound_effects and job.creative_suggestions:
                sfx_prompts = job.creative_suggestions.effects[:1] if job.creative_suggestions.effects else []
                if sfx_prompts:
                    logger.info(f"[{job.job_id}] Step 7: Generating sound effects")
                    sfx_files = await self.audio_agent.generate_sound_effects(
                        prompts=sfx_prompts,
                        duration=3.0,
                    )
                    sfx_path = sfx_files[0] if sfx_files else None

            job.progress = 85
            job.current_step = "Replacing video audio with voiceover..."
            job.updated_at = datetime.utcnow()
            await self._save_job(job)

        except Exception as e:
            logger.error(f"[{job.job_id}] Audio generation failed: {e}")
            raise RuntimeError(f"Audio generation failed: {e}")

        # Download merged video (currently has Veo's audio or no audio)
        import tempfile
        merged_video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name

        async with __import__('httpx').AsyncClient() as client:
            response = await client.get(job.merged_video_url)
            with open(merged_video_path, 'wb') as f:
                f.write(response.content)

        # STEP 6: Replace video audio with ElevenLabs voiceover
        logger.info(f"[{job.job_id}] Step 6: Replacing audio with ElevenLabs voice")
        video_with_voice_path = tempfile.NamedTemporaryFile(delete=False, suffix="_with_voice.mp4").name

        self.video_compositor.video_processor.add_audio_to_video(
            video_path=merged_video_path,
            audio_path=voiceover_path,
            output_path=video_with_voice_path,
            audio_volume=1.0,
        )

        job.progress = 87
        job.current_step = "Mixing background music and effects..."
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # STEP 7c: Mix voice + music + SFX
        logger.info(f"[{job.job_id}] Step 7: Mixing all audio layers")
        if music_path or sfx_path:
            final_path = self.video_compositor.add_audio_layers(
                video_path=video_with_voice_path,
                music_path=music_path,
                sfx_path=sfx_path,
                music_volume=0.2,  # Quiet background music (voice is primary)
                sfx_volume=0.5,
            )
        else:
            # No music/SFX, just use video with voice
            final_path = video_with_voice_path

        # Upload final video
        blob_name = f"{job.user_id}/{job.job_id}/final_video_temp.mp4"
        final_url = await upload_file_to_gcs(final_path, blob_name)

        job.final_video_url = final_url
        job.progress = 90
        job.updated_at = datetime.utcnow()

        # Cleanup temp files
        self.audio_agent.cleanup_temp_files(voiceover_path, music_path, sfx_path)
        if os.path.exists(merged_video_path):
            os.remove(merged_video_path)
        if os.path.exists(video_with_voice_path):
            os.remove(video_with_voice_path)
        if os.path.exists(final_path) and final_path != video_with_voice_path:
            os.remove(final_path)

        logger.info(f"[{job.job_id}] Complete audio layers added (voice + music + SFX)")
        return job

    async def _step8_finalize(self, job: AdJob, user_id: str) -> AdJob:
        """Step 8: Final upload and asset creation."""
        logger.info(f"[{job.job_id}] Step 8: Finalizing ad")

        job.status = AdJobStatus.FINALIZING
        job.current_step = "Finalizing and uploading ad..."
        job.progress = 95
        job.updated_at = datetime.utcnow()
        await self._save_job(job)

        # Move final video to permanent location
        final_blob_name = f"{user_id}/{job.campaign_id}/ads/{job.job_id}.mp4"

        # Copy from temp location to final location
        # (In production, use GCS copy operation)
        # For now, the temp URL is the final URL

        # Create asset record in database
        asset_data = {
            "campaign_id": job.campaign_id,
            "job_id": job.job_id,
            "ad_type": "video",
            "model": "veo-3.1-generate-preview",
            "prompt": job.script,
            "url": job.final_video_url,
            "gcs_path": final_blob_name,
            "aspect_ratio": "16:9",  # From request
            "duration": len(job.video_clips) * 7,  # Approximate
            "tags": ["ai-generated", "ad-agent"],
            "cost": job.total_cost,
        }

        asset = await self.db.create_asset(user_id, asset_data)

        logger.info(f"[{job.job_id}] Asset created: {asset['id']}")

        job.progress = 100
        job.updated_at = datetime.utcnow()

        return job

    async def _save_job(self, job: AdJob):
        """Save job state to database."""
        try:
            job_dict = job.dict()
            await self.db.save_ad_job(job.user_id, job_dict)
        except Exception as e:
            logger.error(f"Failed to save job state: {e}")

    async def get_job_status(self, job_id: str, user_id: str) -> Optional[AdJob]:
        """
        Get job status.

        Args:
            job_id: Job ID
            user_id: User ID

        Returns:
            AdJob if found, None otherwise
        """
        try:
            job_dict = await self.db.get_ad_job(user_id, job_id)
            if job_dict:
                return AdJob(**job_dict)
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")

        return None
