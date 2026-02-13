"""Vendor-level tool wrappers for the agentic orchestrator.

Each function is a thin wrapper around a single vendor API call.
Errors are caught and returned as JSON (never raised) so Claude can decide how to handle them.
Large artifacts (images, videos) are saved to GCS internally — Claude only sees URLs.
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
from app.ad_agent.clients.gemini_client import GeminiClient
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

    # Agent/client instances (initialized by orchestrator)
    prompt_agent: Optional[PromptGeneratorAgent] = None
    video_agent: Optional[VideoGeneratorAgent] = None
    clip_verifier: Optional[ClipVerifierAgent] = None
    audio_agent: Optional[AudioCompositorAgent] = None
    video_compositor: Optional[VideoCompositorAgent] = None
    storage: Optional[GCSStorage] = None
    gemini_client: Optional[GeminiClient] = None


# ──────────────────────────────────────────────
# 1. gemini_text — Gemini text generation
# ──────────────────────────────────────────────

async def tool_gemini_text(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini text generation for any purpose."""
    try:
        prompt = params["prompt"]
        system_instruction = params.get("system_instruction")

        logger.info(f"[{ctx.job_id}] Tool: gemini_text ({len(prompt)} chars)")

        text = await ctx.gemini_client.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
        )

        return {"text": text}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] gemini_text failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 2. gemini_image — Gemini image generation + GCS upload
# ──────────────────────────────────────────────

async def tool_gemini_image(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini image generation from prompt + optional character reference. Saves to GCS."""
    try:
        prompt = params["prompt"]
        destination_path = params["destination_path"]
        character_image_gcs_url = params.get("character_image_gcs_url")

        logger.info(f"[{ctx.job_id}] Tool: gemini_image")

        # Download and encode character reference if provided
        character_image_b64 = None
        if character_image_gcs_url:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                resp = await http_client.get(character_image_gcs_url)
                resp.raise_for_status()
                character_image_b64 = base64.b64encode(resp.content).decode("utf-8")

        image_bytes = await ctx.gemini_client.generate_scene_image(
            prompt=prompt,
            character_image_b64=character_image_b64,
            aspect_ratio=ctx.aspect_ratio,
        )

        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        try:
            with open(temp_path, "wb") as f:
                f.write(image_bytes)
            gcs_path = f"{ctx.user_id}/{ctx.job_id}/{destination_path}"
            await ctx.storage.upload_from_file(temp_path, gcs_path)
            signed_url = await ctx.storage.get_signed_url(gcs_path, expiration_days=7)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return {"image_gcs_url": signed_url}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] gemini_image failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 3. gemini_vision — Gemini video/image analysis
# ──────────────────────────────────────────────

async def tool_gemini_vision(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini Vision: analyze a video clip against script and prompt."""
    try:
        video_url = params["video_url"]
        system_instruction = params["system_instruction"]
        script_segment = params["script_segment"]
        veo_prompt = params["veo_prompt"]
        clip_label = params.get("clip_label", "clip")

        logger.info(f"[{ctx.job_id}] Tool: gemini_vision ({clip_label})")

        result = await ctx.gemini_client.analyze_video_content(
            video_url=video_url,
            system_instruction=system_instruction,
            script_segment=script_segment,
            prompt=veo_prompt,
            clip_label=clip_label,
        )

        return {
            "confidence_score": result.get("confidence_score", 0.0),
            "description": result.get("description", ""),
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] gemini_vision failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 4. veo_generate — Veo image-to-video + GCS upload
# ──────────────────────────────────────────────

async def tool_veo_generate(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Veo 3.1 image-to-video. Downloads scene image, generates video(s), uploads to GCS."""
    try:
        prompt = params["prompt"]
        scene_image_gcs_url = params["scene_image_gcs_url"]
        destination_prefix = params["destination_prefix"]
        duration = params.get("duration", settings.DEFAULT_CLIP_DURATION)
        aspect_ratio = params.get("aspect_ratio", ctx.aspect_ratio)
        resolution = params.get("resolution", ctx.resolution)
        sample_count = params.get("sample_count", settings.VEO_SAMPLE_COUNT)

        logger.info(f"[{ctx.job_id}] Tool: veo_generate (samples={sample_count})")

        # Download scene image and encode as b64 for Veo
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.get(scene_image_gcs_url)
            resp.raise_for_status()
            scene_image_b64 = base64.b64encode(resp.content).decode("utf-8")

        # Create Veo job
        clip = await ctx.video_agent.generate_video_clip(
            prompt=prompt,
            character_image=scene_image_b64,
            clip_number=0,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            sample_count=sample_count,
        )

        if clip.status == "failed":
            return {"error": clip.error or "Video generation failed"}

        # Wait for completion
        result = await ctx.video_agent.wait_for_video_completion(
            job_id=clip.veo_job_id,
            timeout=settings.VIDEO_GENERATION_TIMEOUT,
            return_all_videos=True,
        )

        videos = result.get("videos", [])
        if not videos:
            return {"error": "Veo returned no videos"}

        # Upload each variant to GCS
        clip_gcs_urls = []
        for i, video_b64 in enumerate(videos):
            temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
            try:
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(video_b64))
                gcs_path = f"{ctx.user_id}/{ctx.job_id}/{destination_prefix}_v{i}.mp4"
                await ctx.storage.upload_from_file(temp_path, gcs_path)
                signed_url = await ctx.storage.get_signed_url(gcs_path, expiration_days=7)
                clip_gcs_urls.append(signed_url)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        logger.info(f"[{ctx.job_id}] Veo generated {len(clip_gcs_urls)} variant(s)")

        return {"clip_gcs_urls": clip_gcs_urls, "count": len(clip_gcs_urls)}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] veo_generate failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 5. ffmpeg_merge — Concatenate video clips + GCS upload
# ──────────────────────────────────────────────

async def tool_ffmpeg_merge(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """ffmpeg: merge multiple video clips into one. Uploads result to GCS."""
    try:
        video_urls = params["video_urls"]

        logger.info(f"[{ctx.job_id}] Tool: ffmpeg_merge ({len(video_urls)} clips)")

        if len(video_urls) == 1:
            return {"merged_video_url": video_urls[0], "duration": 8.0}

        merged_path = await ctx.video_compositor.merge_video_clips(video_urls=video_urls)

        try:
            blob_name = f"{ctx.user_id}/{ctx.job_id}/merged_video.mp4"
            merged_url = await upload_file_to_gcs(merged_path, blob_name)
            video_info = ctx.video_compositor.get_video_info(merged_path)
            duration = video_info.get("duration", len(video_urls) * 8.0)
        finally:
            if os.path.exists(merged_path):
                os.remove(merged_path)

        return {"merged_video_url": merged_url, "duration": duration}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] ffmpeg_merge failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 6. ffmpeg_audio_extract — Extract audio from video
# ──────────────────────────────────────────────

async def tool_ffmpeg_audio_extract(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """ffmpeg: extract audio track from a video URL."""
    try:
        video_url = params["video_url"]

        logger.info(f"[{ctx.job_id}] Tool: ffmpeg_audio_extract")

        audio_path = await ctx.audio_agent.extract_audio_from_video(video_url)

        return {"audio_file_path": audio_path}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] ffmpeg_audio_extract failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 7. ffmpeg_audio_replace — Replace audio in video + GCS upload
# ──────────────────────────────────────────────

async def tool_ffmpeg_audio_replace(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """ffmpeg: replace audio track in video. Uploads result to GCS."""
    try:
        video_url = params["video_url"]
        audio_file_path = params["audio_file_path"]

        logger.info(f"[{ctx.job_id}] Tool: ffmpeg_audio_replace")

        output_path = await ctx.audio_agent.replace_audio_track(
            video_path=video_url,
            audio_path=audio_file_path,
        )

        try:
            blob_name = f"{ctx.user_id}/{ctx.job_id}/enhanced_video.mp4"
            video_url = await upload_file_to_gcs(output_path, blob_name)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

        return {"video_gcs_url": video_url}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] ffmpeg_audio_replace failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 8. elevenlabs_voice_change — Speech-to-speech
# ──────────────────────────────────────────────

async def tool_elevenlabs_voice_change(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """ElevenLabs: apply voice conversion to an audio file."""
    try:
        audio_file_path = params["audio_file_path"]
        voice_id = params.get("voice_id") or ctx.voice_id

        logger.info(f"[{ctx.job_id}] Tool: elevenlabs_voice_change")

        if not voice_id:
            voice_id = await ctx.audio_agent.elevenlabs.find_voice_by_name(settings.DEFAULT_VOICE_NAME)
            if not voice_id:
                return {"error": f"Voice '{settings.DEFAULT_VOICE_NAME}' not found"}

        enhanced_bytes = await ctx.audio_agent.elevenlabs.voice_changer(
            audio_file_path=audio_file_path,
            voice_id=voice_id,
        )

        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        with open(temp_path, "wb") as f:
            f.write(enhanced_bytes)

        return {"audio_file_path": temp_path, "voice_id": voice_id}

    except Exception as e:
        logger.error(f"[{ctx.job_id}] elevenlabs_voice_change failed: {e}", exc_info=True)
        return {"error": str(e)}


# ──────────────────────────────────────────────
# 9. firestore_create_asset — Create asset record
# ──────────────────────────────────────────────

async def tool_firestore_create_asset(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Firestore: create an asset record for the final video."""
    try:
        final_video_url = params["final_video_url"]

        logger.info(f"[{ctx.job_id}] Tool: firestore_create_asset")

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
            "tags": ["ai-generated", "agentic-workflow"],
        }

        asset = await db.create_asset(ctx.user_id, asset_data)

        return {
            "asset_id": asset.get("id", ctx.job_id),
            "final_video_url": final_video_url,
            "status": "finalized",
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] firestore_create_asset failed: {e}", exc_info=True)
        return {"error": str(e)}
