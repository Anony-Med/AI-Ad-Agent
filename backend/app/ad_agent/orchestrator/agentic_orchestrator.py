"""Agentic orchestrator for AI Ad Agent.

Claude acts as the decision-making orchestrator, receiving a natural language
instruction and a set of tools. It decides which tools to call, in what order,
and how to handle failures (e.g., retrying clips that fail verification with
adjusted prompts).
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.ad_agent.clients.anthropic_client import AnthropicClient
from app.ad_agent.orchestrator.tool_wrappers import (
    ToolContext,
    tool_gemini_text,
    tool_gemini_image,
    tool_gemini_vision,
    tool_veo_generate,
    tool_ffmpeg_merge,
    tool_ffmpeg_audio_extract,
    tool_ffmpeg_audio_replace,
    tool_elevenlabs_voice_change,
    tool_firestore_create_asset,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Map tool names to handler functions
TOOL_HANDLERS = {
    "gemini_text": tool_gemini_text,
    "gemini_image": tool_gemini_image,
    "gemini_vision": tool_gemini_vision,
    "veo_generate": tool_veo_generate,
    "ffmpeg_merge": tool_ffmpeg_merge,
    "ffmpeg_audio_extract": tool_ffmpeg_audio_extract,
    "ffmpeg_audio_replace": tool_ffmpeg_audio_replace,
    "elevenlabs_voice_change": tool_elevenlabs_voice_change,
    "firestore_create_asset": tool_firestore_create_asset,
}

# Progress mapping: tool name -> (job status string, base progress %)
PROGRESS_MAP = {
    "gemini_text": ("generating_prompts", 10),
    "gemini_image": ("generating_scene_images", 20),
    "veo_generate": ("generating_videos", 40),
    "gemini_vision": ("verifying_clips", 55),
    "ffmpeg_merge": ("merging_videos", 70),
    "ffmpeg_audio_extract": ("enhancing_voice", 80),
    "elevenlabs_voice_change": ("enhancing_voice", 85),
    "ffmpeg_audio_replace": ("enhancing_voice", 90),
    "firestore_create_asset": ("finalizing", 95),
}

SYSTEM_INSTRUCTION = f"""You are an AI video ad creation agent. Your goal is to produce a video ad from a script and the provided character reference image.
"""


def _build_tool_definitions() -> List[Dict[str, Any]]:
    """Build Anthropic tool definitions for all 9 vendor-level tools."""
    return [
        {
            "name": "gemini_text",
            "description": (
                f"Generates text using the {settings.GEMINI_MODEL} language model. "
                "Send any text prompt and receive a generated text response. "
                "Use this tool whenever you need to produce written content, transform text, "
                "or extract structured information from unstructured input. "
                "Do not use this tool for image generation or video/image analysis — "
                "separate tools exist for those capabilities. "
                "The response contains a single field 'text' with the generated output as a string."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "The text prompt to send to the Gemini model. "
                            "This is the primary input that determines what text is generated. "
                            "Be as specific and detailed as possible for best results."
                        ),
                    },
                    "system_instruction": {
                        "type": "string",
                        "description": (
                            "An optional system-level instruction that sets the persona, format, "
                            "or constraints for the generation. When provided, it is prepended as context "
                            "before the prompt. Use this to enforce output format (e.g. JSON), "
                            "tone, or domain-specific rules without cluttering the prompt itself."
                        ),
                    },
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "gemini_image",
            "description": (
                f"Generates an image using the {settings.GEMINI_IMAGE_MODEL} model, optionally composited with a character reference photo. "
                "When a character_image_gcs_url is provided, the reference photo is sent alongside the prompt "
                "so the generated image features that character. The generated image is saved directly to "
                "Google Cloud Storage. Use this tool whenever you need to create a new image. "
                "Do not use this tool for text generation or video analysis. "
                "The response contains 'image_gcs_url' with the GCS URL of the saved image."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "A detailed description of the image to generate. "
                            "Include the scene setting, character pose, camera angle, lighting, and mood. "
                            "The more specific the prompt, the more accurate the output."
                        ),
                    },
                    "character_image_gcs_url": {
                        "type": "string",
                        "description": (
                            "GCS URL of a character reference photo to include in the generation. "
                            "When provided, the model uses this image as a visual reference so the generated "
                            "image features the same character. If omitted, the image is generated "
                            "from the text prompt alone without any character reference."
                        ),
                    },
                    "destination_path": {
                        "type": "string",
                        "description": (
                            "The GCS path suffix where the generated image will be stored, "
                            "relative to the job's storage prefix. For example, 'scene_images/clip_0.png'. "
                            "The full GCS path is constructed automatically by prepending the job's base path."
                        ),
                    },
                },
                "required": ["prompt", "destination_path"],
            },
        },
        {
            "name": "gemini_vision",
            "description": (
                "Analyzes a video using the Gemini Vision model. Downloads the video from a GCS URL, "
                "sends it to Gemini along with reference text, and returns a structured assessment. "
                "Use this tool when you need to evaluate how well a video matches expected criteria — "
                "such as whether the visual content and spoken dialogue align with reference text. "
                "Do not use this tool for generating text or images. "
                "The response contains 'confidence_score' (a float from 0.0 to 1.0 indicating match quality) "
                "and 'description' (a textual summary of what was observed in the video)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": (
                            "The GCS URL of the video file to analyze. "
                            "The video will be downloaded and sent to the Gemini Vision model."
                        ),
                    },
                    "system_instruction": {
                        "type": "string",
                        "description": (
                            "A system-level instruction that defines how the analysis should be performed. "
                            "Use this to specify evaluation criteria, scoring rubric, "
                            "or the format of the expected response."
                        ),
                    },
                    "script_segment": {
                        "type": "string",
                        "description": (
                            "The expected dialogue or narration text that the video should contain. "
                            "The model uses this as a reference to assess whether the video's audio "
                            "and lip movements match the intended speech."
                        ),
                    },
                    "veo_prompt": {
                        "type": "string",
                        "description": (
                            "The visual prompt that was used to produce the video. "
                            "The model uses this as a reference to assess whether the video's visual "
                            "content (scene, actions, framing) matches the intended description."
                        ),
                    },
                    "clip_label": {
                        "type": "string",
                        "description": (
                            "An optional human-readable label for this analysis, used in log messages "
                            "to identify which clip is being evaluated. For example, 'clip_0_v1'. "
                            "Does not affect the analysis itself."
                        ),
                    },
                },
                "required": ["video_url", "system_instruction", "script_segment", "veo_prompt"],
            },
        },
        {
            "name": "veo_generate",
            "description": (
                "Generates one or more short video clips from a static image using the Google Veo 3.1 API. "
                "The model animates the input image according to the prompt, producing video with synchronized "
                "lip movements when dialogue is included in the prompt. "
                "Each generated clip is saved directly to Google Cloud Storage. "
                "Use this tool when you need to turn a still image into a video. "
                "This tool may fail due to content policy filters on the input image or prompt — "
                "if that happens, the error message will indicate a content policy violation. "
                "Generation takes approximately 1-3 minutes per clip. "
                "The response contains 'clip_gcs_urls' (a list of GCS URLs for the generated clips) "
                "and 'count' (the number of clips successfully generated)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "A detailed prompt describing what should happen in the video. "
                            "Include both visual direction (actions, camera movement, expressions) "
                            "and any dialogue the character should speak. "
                            "Dialogue included in the prompt will be lip-synced automatically by Veo."
                        ),
                    },
                    "scene_image_gcs_url": {
                        "type": "string",
                        "description": (
                            "The GCS URL of the source image to animate. "
                            "This image serves as the first frame of the generated video. "
                            "Must be a valid GCS URL pointing to a PNG or JPEG image."
                        ),
                    },
                    "destination_prefix": {
                        "type": "string",
                        "description": (
                            "The GCS path prefix where generated clips will be stored. "
                            "For example, 'clips/clip_0'. Each variant is saved with a suffix "
                            "appended automatically (e.g. '_v0.mp4', '_v1.mp4')."
                        ),
                    },
                    "duration": {
                        "type": "integer",
                        "description": (
                            "The length of the generated video in seconds. "
                            "Allowed values are 4, 6, or 8. If omitted, the system default is used. "
                            "Longer durations allow more action but increase generation time."
                        ),
                    },
                    "sample_count": {
                        "type": "integer",
                        "description": (
                            "The number of video variants to generate from the same prompt and image. "
                            "Allowed values are 1 through 4. If omitted, the system default is used. "
                            "Generating multiple variants lets you select the best result."
                        ),
                    },
                },
                "required": ["prompt", "scene_image_gcs_url", "destination_prefix"],
            },
        },
        {
            "name": "ffmpeg_merge",
            "description": (
                "Concatenates multiple video clips into a single continuous video using ffmpeg. "
                "The clips are joined in the exact order provided, with no transitions or crossfades — "
                "clips are placed back-to-back. The merged result is uploaded to Google Cloud Storage. "
                "Use this tool when you have multiple separate video files that need to be combined "
                "into one continuous video. All input clips should have the same resolution and codec "
                "for best results. "
                "The response contains 'merged_video_url' (the GCS URL of the merged video) "
                "and 'duration' (total duration in seconds)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "video_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "An ordered list of GCS URLs pointing to the video clips to concatenate. "
                            "The clips will be merged in the order they appear in this list. "
                            "Must contain at least two URLs."
                        ),
                    },
                },
                "required": ["video_urls"],
            },
        },
        {
            "name": "ffmpeg_audio_extract",
            "description": (
                "Extracts the audio track from a video file using ffmpeg. "
                "Downloads the video from the provided GCS URL, strips out the audio, "
                "and saves it as a local temporary file. The video file itself is not modified. "
                "Use this tool when you need the audio from a video as a standalone file — "
                "for example, before processing it with a voice conversion tool. "
                "The response contains 'audio_file_path' pointing to the local temporary file. "
                "This file is cleaned up automatically at the end of the job."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": (
                            "The GCS URL of the video file from which to extract the audio track. "
                            "The video must contain an audio stream; if it has no audio, the tool will return an error."
                        ),
                    },
                },
                "required": ["video_url"],
            },
        },
        {
            "name": "ffmpeg_audio_replace",
            "description": (
                "Replaces the entire audio track of a video with a different audio file using ffmpeg. "
                "Downloads the video from GCS, swaps its audio for the provided local audio file, "
                "and uploads the result to Google Cloud Storage. The original video is not modified. "
                "Use this tool when you have a video whose audio needs to be replaced with a new track — "
                "for example, after enhancing the voice quality of the original audio. "
                "The audio is trimmed or padded to match the video duration. "
                "The response contains 'video_gcs_url' with the GCS URL of the new video."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "video_url": {
                        "type": "string",
                        "description": (
                            "The GCS URL of the video whose audio track will be replaced. "
                            "The video stream (visual content) is preserved as-is."
                        ),
                    },
                    "audio_file_path": {
                        "type": "string",
                        "description": (
                            "The local file path of the new audio track to insert into the video. "
                            "This should be a path returned by another tool (e.g. ffmpeg_audio_extract "
                            "or elevenlabs_voice_change). Supported formats include WAV, MP3, and AAC."
                        ),
                    },
                },
                "required": ["video_url", "audio_file_path"],
            },
        },
        {
            "name": "elevenlabs_voice_change",
            "description": (
                "Converts the voice in an audio file to a different voice using ElevenLabs Speech-to-Speech API. "
                "The speech content and timing are preserved, but the vocal characteristics (timbre, tone) "
                "are transformed to match the target voice. The result is saved as a local temporary file. "
                "Use this tool when you want to change the speaker's voice in an audio recording "
                "while keeping the original words and pacing intact. "
                "The response contains 'audio_file_path' pointing to the local temporary file "
                "with the converted audio. This file is cleaned up automatically at the end of the job."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "audio_file_path": {
                        "type": "string",
                        "description": (
                            "The local file path of the source audio whose voice should be converted. "
                            "This should be a path returned by another tool (e.g. ffmpeg_audio_extract). "
                            "The audio must contain intelligible speech for the conversion to work properly."
                        ),
                    },
                    "voice_id": {
                        "type": "string",
                        "description": (
                            "The ElevenLabs voice ID specifying which target voice to convert to. "
                            "If omitted, the system's default voice is used. "
                            "Voice IDs can be found in the ElevenLabs voice library."
                        ),
                    },
                },
                "required": ["audio_file_path"],
            },
        },
        {
            "name": "firestore_create_asset",
            "description": (
                "Creates a persistent asset record in the Firestore database for a completed video. "
                "This registers the video so it can be retrieved, listed, and managed through the API. "
                "Use this tool once as the final step after the video is fully processed and "
                "uploaded to cloud storage. Do not call this tool until the video is in its final form. "
                "The response contains 'asset_id' (unique identifier for the new record), "
                "'final_video_url' (the URL that was registered), and 'status' (the record's initial status)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "final_video_url": {
                        "type": "string",
                        "description": (
                            "The GCS URL of the finished video to register as an asset. "
                            "This URL will be stored in the database and made available to clients. "
                            "It must point to an existing, fully uploaded video file."
                        ),
                    },
                },
                "required": ["final_video_url"],
            },
        },
    ]


class AgenticOrchestrator:
    """
    Claude-powered orchestrator for ad creation.

    Runs an agentic loop where Claude decides which tools to call,
    handles errors, and manages the full ad creation workflow.
    """

    def __init__(
        self,
        anthropic_api_key: str,
        tool_context: ToolContext,
        progress_callback: Optional[Callable[..., Coroutine]] = None,
        model: Optional[str] = None,
        max_iterations: Optional[int] = None,
        max_duration_seconds: Optional[int] = None,
        human_in_the_loop: bool = False,
    ):
        self.hitl = human_in_the_loop
        self.anthropic = AnthropicClient(
            api_key=anthropic_api_key,
            model=model or getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        )
        self.ctx = tool_context
        self.progress_callback = progress_callback
        self.max_iterations = max_iterations or getattr(settings, "AGENTIC_MAX_ITERATIONS", 25)
        self.max_duration = max_duration_seconds or getattr(settings, "AGENTIC_MAX_DURATION_SECONDS", 1800)

        self.tools = _build_tool_definitions()
        self.system = SYSTEM_INSTRUCTION

        # Track tool call counts for progress estimation
        self._tool_call_counts: Dict[str, int] = {}

    async def run(
        self,
        script: str,
        character_name: str,
        voice_id: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the agentic ad creation loop.

        Args:
            script: The ad dialogue script
            character_name: Character name for prompts
            voice_id: Optional ElevenLabs voice ID
            aspect_ratio: Video aspect ratio
            resolution: Video resolution

        Returns:
            Dict with final_video_url and metadata
        """
        aspect_ratio = aspect_ratio or settings.VEO_DEFAULT_ASPECT_RATIO
        resolution = resolution or settings.VEO_DEFAULT_RESOLUTION

        logger.info(f"[{self.ctx.job_id}] Starting agentic orchestrator")
        start_time = time.time()

        # Build initial user message
        user_message = self._build_user_message(
            script=script,
            character_name=character_name,
            character_image_gcs_url=self.ctx.character_image_gcs_url,
            voice_id=voice_id,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        messages = [{"role": "user", "content": user_message}]

        for iteration in range(self.max_iterations):
            elapsed = time.time() - start_time
            if elapsed > self.max_duration:
                logger.error(f"[{self.ctx.job_id}] Agentic loop timed out after {elapsed:.0f}s")
                return {"error": f"Orchestrator timed out after {elapsed:.0f}s", "final_video_url": None}

            logger.info(f"[{self.ctx.job_id}] Agentic iteration {iteration + 1}/{self.max_iterations}")

            # Call Claude
            try:
                response = await self.anthropic.create_message(
                    messages=messages,
                    system=self.system,
                    tools=self.tools,
                )
            except Exception as e:
                logger.error(f"[{self.ctx.job_id}] Anthropic API error: {e}", exc_info=True)
                return {"error": f"Anthropic API error: {str(e)}", "final_video_url": None}

            # Process response
            if response.stop_reason == "end_turn":
                # Agent is done — extract final result from text
                final_text = self._extract_text(response)
                logger.info(f"[{self.ctx.job_id}] Agent completed: {final_text}...")
                result = self._parse_final_result(final_text)
                return result

            elif response.stop_reason == "tool_use":
                # Execute tool calls and build result messages
                assistant_message = {"role": "assistant", "content": response.content}
                messages.append(assistant_message)

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        sep = "=" * 50
                        line = "-" * 50
                        parts = [f"\n{sep}", f"[HITL] Tool call: {tool_name}", line]
                        for key, value in tool_input.items():
                            parts.append(f"  {key}: {value}")
                        parts.append(line)
                        logger.info(f"[{self.ctx.job_id}] {"\n".join(parts)}")

                        # Human-in-the-loop gate
                        if self.hitl:
                            if not await self._hitl_prompt(tool_name, tool_input):
                                return {"error": "Aborted by developer", "final_video_url": None}

                        # Execute the tool
                        result = await self._execute_tool(tool_name, tool_input)

                        # Update progress
                        await self._update_progress(tool_name, result)

                        # Emit SSE event
                        await self._emit_progress(tool_name, result)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                messages.append({"role": "user", "content": tool_results})

            else:
                logger.warning(f"[{self.ctx.job_id}] Unexpected stop_reason: {response.stop_reason}")
                final_text = self._extract_text(response)
                return self._parse_final_result(final_text)

        logger.error(f"[{self.ctx.job_id}] Agentic loop exhausted max iterations ({self.max_iterations})")
        return {"error": "Max iterations reached", "final_video_url": None}

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a tool call to the appropriate handler."""
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = await handler(self.ctx, tool_input)
            return result
        except Exception as e:
            logger.error(f"[{self.ctx.job_id}] Tool {tool_name} raised: {e}", exc_info=True)
            return {"error": str(e), "error_type": "tool_execution_error"}

    async def _hitl_prompt(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        """Print tool call details and wait for developer approval. Returns True to continue, False to abort."""
        answer = await asyncio.to_thread(input, "[Enter] continue | [a] abort: ")
        if answer.strip().lower() == "a":
            logger.info(f"[{self.ctx.job_id}] Developer aborted at {tool_name}")
            return False
        return True

    async def _update_progress(self, tool_name: str, result: Dict[str, Any]) -> None:
        """Update job progress in Firestore based on which tool just executed."""
        self._tool_call_counts[tool_name] = self._tool_call_counts.get(tool_name, 0) + 1

        status_str, base_progress = PROGRESS_MAP.get(tool_name, (None, None))

        try:
            from app.database import get_db
            db = get_db()

            update_data = {"updated_at": datetime.utcnow()}
            if status_str:
                update_data["status"] = status_str
                update_data["current_step"] = f"Running {tool_name}..."
            if base_progress is not None:
                update_data["progress"] = min(base_progress, 99)

            await db.update_job(self.ctx.job_id, **update_data)
        except Exception as e:
            logger.warning(f"[{self.ctx.job_id}] Failed to update job progress: {e}")

    async def _emit_progress(self, tool_name: str, result: Dict[str, Any]) -> None:
        """Emit SSE progress event if callback is set."""
        if not self.progress_callback:
            return

        try:
            _, base_progress = PROGRESS_MAP.get(tool_name, (None, None))
            await self.progress_callback(f"tool_{tool_name}", {
                "tool": tool_name,
                "progress": base_progress or 0,
                "result_summary": {
                    k: v for k, v in result.items()
                    if k not in ("error",) and isinstance(v, (str, int, float, bool))
                },
            })
        except Exception as e:
            logger.warning(f"[{self.ctx.job_id}] Progress callback error: {e}")

    def _build_user_message(
        self,
        script: str,
        character_name: str,
        character_image_gcs_url: str,
        voice_id: Optional[str],
        aspect_ratio: str,
        resolution: str,
    ) -> str:
        """Build the initial user message for Claude."""
        parts = [
            f"Create a video ad with the following details:",
            f"",
            f"**Script:**",
            f"{script}",
            f"",
            f"**Character Name:** {character_name}",
            f"**Character Reference Image URL:** {character_image_gcs_url}",
            f"**Aspect Ratio:** {aspect_ratio}",
            f"**Resolution:** {resolution}",
            f"",
            f"{settings.CLIPS_PER_AD} clips, each {settings.CLIP_DURATION} seconds"
            f"Verification confidence threshold: >= {settings.VERIFICATION_THRESHOLD}"
            f"Voice enhancement is currently disabled — finalize with the merged video directly.",
            f"**When finished**, respond with JSON:"
            f"{{\"final_video_url\": \"<url>\"}}"
            f"If the process fails unrecoverably, respond with:"
            f"{{\"error\": \"<description>\", \"final_video_url\": null}}"
        ]

        if voice_id:
            parts.append(f"**Voice ID:** {voice_id}")
        else:
            parts.append(f"**Voice:** Use the default Bella voice")

        parts.extend([
            f"",
            f"Use the character reference image URL above as the `character_image_gcs_url` "
            f"parameter when calling `gemini_image` so the generated scene images feature this character.",
            f"",
            f"Please proceed with creating the ad.",
        ])

        return "\n".join(parts)

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from an Anthropic response."""
        texts = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)

    @staticmethod
    def _parse_final_result(text: str) -> Dict[str, Any]:
        """Extract final result JSON from Claude's last message."""
        # Try to find JSON block with final_video_url
        json_match = re.search(r'\{[^{}]*"final_video_url"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: try to extract URL from text
        url_match = re.search(r'https://storage\.googleapis\.com/[^\s"]+', text)
        if url_match:
            return {"final_video_url": url_match.group(), "parsed_from_text": True}

        logger.warning(f"Could not parse final result from agent response")
        return {"final_video_url": None, "raw_response": text}
