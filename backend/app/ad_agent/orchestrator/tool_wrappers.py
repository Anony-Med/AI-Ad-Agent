"""Tool wrapper functions for the agentic orchestrator.

Each function wraps existing agent code and returns structured JSON.
Errors are caught and returned as JSON (never raised) so Claude can decide how to handle them.
Large data (images, videos) flows via GCS URLs — never through the LLM context.
"""
import base64
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.ad_agent.agents.prompt_generator import PromptGeneratorAgent
from app.ad_agent.agents.video_generator import VideoGeneratorAgent
from app.ad_agent.agents.clip_verifier import ClipVerifierAgent
from app.ad_agent.agents.audio_compositor import AudioCompositorAgent
from app.ad_agent.agents.video_compositor import VideoCompositorAgent
from app.database.gcs_storage import GCSStorage, upload_file_to_gcs
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Shared state for all tool wrappers within a single ad creation job."""
    job_id: str
    user_id: str
    character_image_gcs_url: str
    character_image_b64: str  # raw base64 (without data URI prefix) for Veo API
    aspect_ratio: str = field(default_factory=lambda: settings.VEO_DEFAULT_ASPECT_RATIO)
    resolution: str = field(default_factory=lambda: settings.VEO_DEFAULT_RESOLUTION)
    voice_id: Optional[str] = None
    campaign_id: str = ""
    script: str = ""

    # Agent instances (initialized by orchestrator)
    prompt_agent: Optional[PromptGeneratorAgent] = None
    video_agent: Optional[VideoGeneratorAgent] = None
    clip_verifier: Optional[ClipVerifierAgent] = None
    audio_agent: Optional[AudioCompositorAgent] = None
    video_compositor: Optional[VideoCompositorAgent] = None
    storage: Optional[GCSStorage] = None

    # Track generated clips for merge step
    generated_clip_urls: Dict[int, str] = field(default_factory=dict)


async def tool_generate_veo_prompts(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Veo 3.1 video prompts from a script.

    Wraps PromptGeneratorAgent.generate_prompts_with_segments().
    Caps output at 2 clips max for the 15-second ad limit.
    """
    try:
        script = params["script"]
        character_name = params.get("character_name", "character")

        logger.info(f"[{ctx.job_id}] Tool: generate_veo_prompts (script={len(script)} chars)")

        prompts, segments = await ctx.prompt_agent.generate_prompts_with_segments(
            script=script,
            character_name=character_name,
            max_clip_duration=settings.MAX_CLIP_DURATION,
        )

        # Cap at max clips (max ad duration)
        if len(prompts) > settings.MAX_CLIPS_PER_AD:
            logger.warning(f"[{ctx.job_id}] Capping from {len(prompts)} to {settings.MAX_CLIPS_PER_AD} clips ({settings.MAX_AD_DURATION_SECONDS}s limit)")
            prompts = prompts[:settings.MAX_CLIPS_PER_AD]
            segments = segments[:settings.MAX_CLIPS_PER_AD]

        result = {
            "prompts": [
                {
                    "clip_number": i,
                    "veo_prompt": prompt,
                    "script_segment": segment,
                }
                for i, (prompt, segment) in enumerate(zip(prompts, segments))
            ],
            "total_clips": len(prompts),
        }

        logger.info(f"[{ctx.job_id}] Generated {len(prompts)} prompts")
        return result

    except Exception as e:
        logger.error(f"[{ctx.job_id}] generate_veo_prompts failed: {e}", exc_info=True)
        return {"error": str(e), "error_type": "prompt_generation_failed"}


async def tool_generate_video_clip(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a single video clip using Veo 3.1.

    Blocks until the video is fully generated (2-5 minutes).
    Always uses the original character image from ctx (not from Claude's message).
    Saves the clip to GCS and returns only the URL.
    """
    try:
        clip_number = params["clip_number"]
        veo_prompt = params["veo_prompt"]
        script_segment = params["script_segment"]
        duration_seconds = params.get("duration_seconds", 8)

        logger.info(f"[{ctx.job_id}] Tool: generate_video_clip (clip={clip_number}, duration={duration_seconds}s)")

        # Combine script and visual prompt for Veo (lip-sync requires dialogue)
        full_veo_prompt = f"Script/Dialogue: {script_segment}\n\nVisual Description: {veo_prompt}"

        # Generate clip using existing agent (uses character_image_b64 from context)
        clips = await ctx.video_agent.generate_all_clips(
            prompts=[full_veo_prompt],
            character_image=ctx.character_image_b64,
            duration=duration_seconds,
            aspect_ratio=ctx.aspect_ratio,
            resolution=ctx.resolution,
            max_concurrent=1,
            clip_number_offset=clip_number,
        )

        if not clips or clips[0].status == "failed":
            error_msg = clips[0].error if clips else "No clip generated"
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": error_msg,
                "error_type": "content_policy" if _is_content_policy_error(error_msg) else "generation_failed",
            }

        # Wait for clip completion (blocking, with retries)
        completed_clips = await ctx.video_agent.wait_for_all_clips(
            clips=clips,
            timeout=settings.VIDEO_GENERATION_TIMEOUT,
            max_retries=settings.MAX_CLIP_RETRIES,
            character_image=ctx.character_image_b64,
            prompts=[full_veo_prompt],
            duration=duration_seconds,
            aspect_ratio=ctx.aspect_ratio,
            resolution=ctx.resolution,
        )

        completed_clip = completed_clips[0]

        if completed_clip.status != "completed" or not completed_clip.video_b64:
            error_msg = completed_clip.error or "Video generation failed or returned no data"
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": error_msg,
                "error_type": "content_policy" if _is_content_policy_error(error_msg) else "generation_failed",
            }

        # Save clip to GCS
        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        try:
            video_bytes = base64.b64decode(completed_clip.video_b64)
            with open(temp_video, "wb") as f:
                f.write(video_bytes)

            gcs_path = f"{ctx.user_id}/{ctx.job_id}/clips/clip_{clip_number}.mp4"
            await ctx.storage.upload_from_file(temp_video, gcs_path)
            clip_gcs_url = await ctx.storage.get_signed_url(gcs_path, expiration_days=7)

            # Track clip URL for merge step
            ctx.generated_clip_urls[clip_number] = clip_gcs_url

            logger.info(f"[{ctx.job_id}] Clip {clip_number} saved to GCS")

            return {
                "status": "completed",
                "clip_number": clip_number,
                "clip_gcs_url": clip_gcs_url,
                "duration_seconds": duration_seconds,
            }
        finally:
            if os.path.exists(temp_video):
                os.remove(temp_video)

    except Exception as e:
        logger.error(f"[{ctx.job_id}] generate_video_clip failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "clip_number": params.get("clip_number", -1),
            "error": str(e),
            "error_type": "content_policy" if _is_content_policy_error(str(e)) else "unexpected_error",
        }


async def tool_verify_video_clip(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify a generated clip matches its script using Gemini Vision.

    Downloads the clip from GCS URL internally. Returns only text analysis.
    """
    try:
        clip_number = params["clip_number"]
        clip_gcs_url = params["clip_gcs_url"]
        script_segment = params["script_segment"]
        veo_prompt = params["veo_prompt"]

        logger.info(f"[{ctx.job_id}] Tool: verify_video_clip (clip={clip_number})")

        verification = await ctx.clip_verifier.verify_clip_from_url(
            clip_gcs_url=clip_gcs_url,
            script_segment=script_segment,
            veo_prompt=veo_prompt,
            clip_number=clip_number,
        )

        result = {
            "clip_number": clip_number,
            "verified": verification.verified,
            "confidence_score": verification.confidence_score,
            "visual_description": verification.visual_description or "",
            "alignment_feedback": verification.alignment_feedback or "",
        }

        logger.info(
            f"[{ctx.job_id}] Clip {clip_number} verification: "
            f"verified={verification.verified}, score={verification.confidence_score:.2f}"
        )
        return result

    except Exception as e:
        logger.error(f"[{ctx.job_id}] verify_video_clip failed: {e}", exc_info=True)
        return {
            "clip_number": params.get("clip_number", -1),
            "verified": False,
            "confidence_score": 0.0,
            "visual_description": "",
            "alignment_feedback": f"Verification failed with error: {str(e)}",
            "error": str(e),
        }


async def tool_merge_video_clips(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge verified video clips into a single video using ffmpeg.

    Streams from GCS URLs (no local download of source clips).
    Uploads merged result to GCS.
    """
    try:
        clip_gcs_urls = params["clip_gcs_urls"]

        logger.info(f"[{ctx.job_id}] Tool: merge_video_clips ({len(clip_gcs_urls)} clips)")

        if len(clip_gcs_urls) == 1:
            # Single clip — no merge needed, just return the URL
            logger.info(f"[{ctx.job_id}] Single clip, skipping merge")
            return {
                "merged_video_url": clip_gcs_urls[0],
                "total_duration_seconds": 8.0,  # approximate
            }

        # Merge using ffmpeg streaming
        merged_path = await ctx.video_compositor.merge_video_clips(
            video_urls=clip_gcs_urls,
        )

        # Upload merged video to GCS
        blob_name = f"{ctx.user_id}/{ctx.job_id}/merged_video.mp4"
        merged_url = await upload_file_to_gcs(merged_path, blob_name)

        # Get duration info
        video_info = ctx.video_compositor.get_video_info(merged_path)
        total_duration = video_info.get("duration", len(clip_gcs_urls) * 8.0)

        # Cleanup
        if os.path.exists(merged_path):
            os.remove(merged_path)

        logger.info(f"[{ctx.job_id}] Merged video uploaded: {merged_url}")

        return {
            "merged_video_url": merged_url,
            "total_duration_seconds": total_duration,
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] merge_video_clips failed: {e}", exc_info=True)
        return {"error": str(e), "error_type": "merge_failed"}


async def tool_enhance_voice(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance the voice in a video using ElevenLabs Voice Changer.

    Extracts audio, applies voice changer, replaces audio track.
    All processing uses streaming from GCS URLs (no full video download).
    """
    try:
        merged_video_url = params["merged_video_url"]
        voice_id = params.get("voice_id") or ctx.voice_id

        logger.info(f"[{ctx.job_id}] Tool: enhance_voice")

        # Find voice by name if no ID provided
        if not voice_id:
            voice_id = await ctx.audio_agent.elevenlabs.find_voice_by_name(settings.DEFAULT_VOICE_NAME)
            if not voice_id:
                logger.warning(f"[{ctx.job_id}] {settings.DEFAULT_VOICE_NAME} voice not found, skipping voice enhancement")
                return {
                    "enhanced_video_url": merged_video_url,
                    "voice_used": f"none ({settings.DEFAULT_VOICE_NAME} not found)",
                    "skipped": True,
                }

        # Step 1: Extract audio from video URL (ffmpeg streaming)
        extracted_audio = await ctx.audio_agent.extract_audio_from_video(merged_video_url)

        # Step 2: Apply voice changer
        enhanced_audio_bytes = await ctx.audio_agent.elevenlabs.voice_changer(
            audio_file_path=extracted_audio,
            voice_id=voice_id,
        )

        # Save enhanced audio
        temp_enhanced_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        with open(temp_enhanced_audio, "wb") as f:
            f.write(enhanced_audio_bytes)

        # Step 3: Replace audio track (ffmpeg streaming from video URL)
        enhanced_video_path = await ctx.audio_agent.replace_audio_track(
            video_path=merged_video_url,
            audio_path=temp_enhanced_audio,
        )

        # Upload enhanced video to GCS
        blob_name = f"{ctx.user_id}/{ctx.job_id}/enhanced_video.mp4"
        enhanced_url = await upload_file_to_gcs(enhanced_video_path, blob_name)

        # Cleanup temp files
        for path in [extracted_audio, temp_enhanced_audio, enhanced_video_path]:
            if os.path.exists(path):
                os.remove(path)

        logger.info(f"[{ctx.job_id}] Voice enhanced: {enhanced_url}")

        return {
            "enhanced_video_url": enhanced_url,
            "voice_used": voice_id,
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] enhance_voice failed: {e}", exc_info=True)
        # On failure, return merged video URL as fallback
        return {
            "enhanced_video_url": params.get("merged_video_url", ""),
            "voice_used": "none (enhancement failed)",
            "error": str(e),
            "skipped": True,
        }


async def tool_upload_and_finalize(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an asset record in Firestore and finalize the ad.
    """
    try:
        final_video_url = params["final_video_url"]

        logger.info(f"[{ctx.job_id}] Tool: upload_and_finalize")

        # Create asset record in Firestore
        asset_id = None
        try:
            from app.database import get_db
            db = get_db()

            asset_data = {
                "campaign_id": ctx.campaign_id,
                "job_id": ctx.job_id,
                "ad_type": "video",
                "model": settings.VEO_MODEL_ID,
                "prompt": ctx.script,
                "url": final_video_url,
                "aspect_ratio": ctx.aspect_ratio,
                "duration": len(ctx.generated_clip_urls) * 8,
                "tags": ["ai-generated", "agentic-workflow"],
            }

            asset = await db.create_asset(ctx.user_id, asset_data)
            asset_id = asset.get("id")
            logger.info(f"[{ctx.job_id}] Asset created: {asset_id}")
        except Exception as db_error:
            logger.warning(f"[{ctx.job_id}] Failed to create asset record: {db_error}")

        return {
            "final_video_url": final_video_url,
            "asset_id": asset_id or ctx.job_id,
            "status": "finalized",
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] upload_and_finalize failed: {e}", exc_info=True)
        return {"error": str(e), "error_type": "finalization_failed"}


def _is_content_policy_error(error_msg: str) -> bool:
    """Check if an error message indicates a content policy violation."""
    if not error_msg:
        return False
    error_lower = error_msg.lower()
    return any(phrase in error_lower for phrase in [
        "safety filter", "blocked by", "violates", "content policy",
        "usage guidelines", "inappropriate content",
    ])
