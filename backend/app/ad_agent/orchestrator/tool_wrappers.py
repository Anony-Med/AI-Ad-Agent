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

    # Agent instances (initialized by orchestrator)
    prompt_agent: Optional[PromptGeneratorAgent] = None
    video_agent: Optional[VideoGeneratorAgent] = None
    clip_verifier: Optional[ClipVerifierAgent] = None
    audio_agent: Optional[AudioCompositorAgent] = None
    video_compositor: Optional[VideoCompositorAgent] = None
    storage: Optional[GCSStorage] = None
    gemini_client: Optional[GeminiClient] = None

    # Track generated artifacts
    generated_clip_urls: Dict[int, str] = field(default_factory=dict)
    generated_scene_image_urls: Dict[int, str] = field(default_factory=dict)


async def tool_generate_veo_prompts(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini text generation: break script into segments with Veo prompts."""
    try:
        script = params["script"]
        system_prompt = params["system_prompt"]
        num_segments = params["num_segments"]
        character_name = params.get("character_name", "character")

        logger.info(f"[{ctx.job_id}] Tool: generate_veo_prompts (script={len(script)} chars, num_segments={num_segments})")

        prompts, segments = await ctx.prompt_agent.generate_prompts_with_segments(
            script=script,
            system_prompt=system_prompt,
            num_segments=num_segments,
            character_name=character_name,
        )

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


async def tool_generate_scene_image(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini image generation: create a scene image from prompt + character reference."""
    try:
        prompt = params["prompt"]
        clip_number = params["clip_number"]

        logger.info(f"[{ctx.job_id}] Tool: generate_scene_image (clip={clip_number})")

        if not ctx.gemini_client:
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": "Gemini client not configured for image generation",
                "error_type": "configuration_error",
            }

        image_bytes = await ctx.gemini_client.generate_scene_image(
            prompt=prompt,
            character_image_b64=ctx.character_image_b64,
            aspect_ratio=ctx.aspect_ratio,
        )

        # Save to GCS
        temp_image = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        try:
            with open(temp_image, "wb") as f:
                f.write(image_bytes)

            gcs_path = f"{ctx.user_id}/{ctx.job_id}/scene_images/clip_{clip_number}.png"
            await ctx.storage.upload_from_file(temp_image, gcs_path)
            scene_image_gcs_url = await ctx.storage.get_signed_url(gcs_path, expiration_days=7)

            ctx.generated_scene_image_urls[clip_number] = scene_image_gcs_url

            logger.info(f"[{ctx.job_id}] Scene image for clip {clip_number} saved to GCS")

            return {
                "status": "completed",
                "clip_number": clip_number,
                "scene_image_gcs_url": scene_image_gcs_url,
            }
        finally:
            if os.path.exists(temp_image):
                os.remove(temp_image)

    except Exception as e:
        logger.error(f"[{ctx.job_id}] generate_scene_image failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "clip_number": params.get("clip_number", -1),
            "error": str(e),
            "error_type": "image_generation_failed",
        }


async def tool_generate_video_clip(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Veo 3.1 image-to-video: generate video clip variants from a scene image with lip-sync.

    Retries automatically when Veo returns fewer variants than requested,
    asking only for the remaining count each time until the desired total is collected.
    """
    try:
        clip_number = params["clip_number"]
        veo_prompt = params["veo_prompt"]
        script_segment = params["script_segment"]
        scene_image_gcs_url = params.get("scene_image_gcs_url")

        if not scene_image_gcs_url:
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": "scene_image_gcs_url is required.",
            }

        desired_count = settings.VEO_SAMPLE_COUNT
        max_collection_retries = 3  # max extra attempts to collect remaining variants

        logger.info(f"[{ctx.job_id}] Tool: generate_video_clip (clip={clip_number}, desired_variants={desired_count})")

        # Download scene image from GCS and encode as base64 for Veo
        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                resp = await http_client.get(scene_image_gcs_url)
                resp.raise_for_status()
                scene_image_bytes = resp.content
            starting_image_b64 = base64.b64encode(scene_image_bytes).decode("utf-8")
        except Exception as img_err:
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": f"Failed to download scene image: {img_err}",
            }

        # Combine script and visual prompt for Veo (lip-sync requires dialogue)
        full_veo_prompt = f"Script/Dialogue: {script_segment}\n\nVisual Description: {veo_prompt}"

        # Collect video variants across retries
        all_videos = []  # list of base64 video strings

        for attempt in range(1 + max_collection_retries):
            remaining = desired_count - len(all_videos)
            if remaining <= 0:
                break

            if attempt > 0:
                logger.info(
                    f"[{ctx.job_id}] Clip {clip_number}: collected {len(all_videos)}/{desired_count} variants, "
                    f"retrying for {remaining} more (attempt {attempt + 1})"
                )

            # Create Veo job requesting only the remaining count
            clip = await ctx.video_agent.generate_video_clip(
                prompt=full_veo_prompt,
                character_image=starting_image_b64,
                clip_number=clip_number,
                duration=8,
                aspect_ratio=ctx.aspect_ratio,
                resolution=ctx.resolution,
                sample_count=remaining,
            )

            if clip.status == "failed":
                if all_videos:
                    logger.warning(
                        f"[{ctx.job_id}] Clip {clip_number}: job creation failed on retry, "
                        f"proceeding with {len(all_videos)} variant(s) collected so far"
                    )
                    break
                return {
                    "status": "failed",
                    "clip_number": clip_number,
                    "error": clip.error or "Video generation job creation failed",
                    "error_type": "content_policy" if _is_content_policy_error(clip.error) else "generation_failed",
                }

            # Wait for video variants to complete
            try:
                result = await ctx.video_agent.wait_for_video_completion(
                    job_id=clip.veo_job_id,
                    timeout=settings.VIDEO_GENERATION_TIMEOUT,
                    return_all_videos=True,
                )
                videos = result.get("videos", [])
                if videos:
                    all_videos.extend(videos)
                    logger.info(
                        f"[{ctx.job_id}] Clip {clip_number}: received {len(videos)} variant(s), "
                        f"total now {len(all_videos)}/{desired_count}"
                    )
            except Exception as wait_err:
                if all_videos:
                    logger.warning(
                        f"[{ctx.job_id}] Clip {clip_number}: wait failed on retry ({wait_err}), "
                        f"proceeding with {len(all_videos)} variant(s) collected so far"
                    )
                    break
                raise  # re-raise if we have nothing

        if not all_videos:
            return {
                "status": "failed",
                "clip_number": clip_number,
                "error": "Veo returned no videos after all attempts",
                "error_type": "generation_failed",
            }

        # Save all collected variants to GCS
        variant_urls = []
        for i, video_b64 in enumerate(all_videos):
            temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
            try:
                video_bytes = base64.b64decode(video_b64)
                with open(temp_video, "wb") as f:
                    f.write(video_bytes)

                gcs_path = f"{ctx.user_id}/{ctx.job_id}/clips/clip_{clip_number}_v{i}.mp4"
                await ctx.storage.upload_from_file(temp_video, gcs_path)
                variant_url = await ctx.storage.get_signed_url(gcs_path, expiration_days=7)
                variant_urls.append(variant_url)
            finally:
                if os.path.exists(temp_video):
                    os.remove(temp_video)

        logger.info(f"[{ctx.job_id}] Clip {clip_number}: {len(variant_urls)} variants saved to GCS")

        return {
            "status": "completed",
            "clip_number": clip_number,
            "clip_variant_urls": variant_urls,
            "variants_generated": len(variant_urls),
        }

    except Exception as e:
        logger.error(f"[{ctx.job_id}] generate_video_clip failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "clip_number": params.get("clip_number", -1),
            "error": str(e),
            "error_type": "content_policy" if _is_content_policy_error(str(e)) else "unexpected_error",
        }


async def tool_verify_video_clip(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gemini Vision: analyze a video clip to verify it matches the script."""
    try:
        clip_number = params["clip_number"]
        clip_gcs_url = params["clip_gcs_url"]
        system_prompt = params["system_prompt"]
        script_segment = params["script_segment"]
        veo_prompt = params["veo_prompt"]

        # Extract variant index from URL pattern clip_{N}_v{M}.mp4
        import re
        variant_match = re.search(r'clip_\d+_v(\d+)\.mp4', clip_gcs_url)
        variant_index = int(variant_match.group(1)) if variant_match else 0

        logger.info(f"[{ctx.job_id}] Tool: verify_video_clip (clip={clip_number}, variant={variant_index})")

        verification = await ctx.clip_verifier.verify_clip_from_url(
            clip_gcs_url=clip_gcs_url,
            system_prompt=system_prompt,
            script_segment=script_segment,
            veo_prompt=veo_prompt,
            clip_number=clip_number,
            variant_index=variant_index,
        )

        result = {
            "clip_number": clip_number,
            "verified": verification.verified,
            "confidence_score": verification.confidence_score,
            "description": verification.description or "",
        }

        # Save verification log to GCS
        try:
            import json as _json
            log_data = {
                "clip_number": clip_number,
                "variant_index": variant_index,
                "clip_gcs_url": clip_gcs_url,
                "verified": verification.verified,
                "confidence_score": verification.confidence_score,
                "description": verification.description or "",
                "script_segment": script_segment,
                "veo_prompt": veo_prompt,
            }
            gcs_path = f"{ctx.user_id}/{ctx.job_id}/verification_logs/clip_{clip_number}_v{variant_index}.json"
            blob = ctx.storage.bucket.blob(gcs_path)
            blob.upload_from_string(_json.dumps(log_data, indent=2), content_type="application/json")
            logger.info(f"[{ctx.job_id}] Saved verification log to gs://{gcs_path}")
        except Exception as log_err:
            logger.warning(f"[{ctx.job_id}] Failed to save verification log: {log_err}")

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
            "description": f"Verification failed with error: {str(e)}",
            "error": str(e),
        }


async def tool_merge_video_clips(ctx: ToolContext, params: Dict[str, Any]) -> Dict[str, Any]:
    """ffmpeg: concatenate multiple video clips into one."""
    try:
        clip_gcs_urls = params["clip_gcs_urls"]

        # Track selected clip URLs (for duration calculation in finalize)
        for i, url in enumerate(clip_gcs_urls):
            ctx.generated_clip_urls[i] = url

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
    """ElevenLabs Speech-to-Speech: enhance voice quality in a video."""
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
    """Firestore: create an asset record for the final video."""
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
