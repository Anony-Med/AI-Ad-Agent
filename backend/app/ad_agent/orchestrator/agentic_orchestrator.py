"""Agentic orchestrator for AI Ad Agent.

Claude acts as the decision-making orchestrator, receiving a natural language
instruction and a set of tools. It decides which tools to call, in what order,
and how to handle failures (e.g., retrying clips that fail verification with
adjusted prompts).
"""
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.ad_agent.clients.anthropic_client import AnthropicClient
from app.ad_agent.orchestrator.tool_wrappers import (
    ToolContext,
    tool_generate_veo_prompts,
    tool_generate_video_clip,
    tool_verify_video_clip,
    tool_merge_video_clips,
    tool_enhance_voice,
    tool_upload_and_finalize,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Map tool names to handler functions
TOOL_HANDLERS = {
    "generate_veo_prompts": tool_generate_veo_prompts,
    "generate_video_clip": tool_generate_video_clip,
    "verify_video_clip": tool_verify_video_clip,
    "merge_video_clips": tool_merge_video_clips,
    "enhance_voice": tool_enhance_voice,
    "upload_and_finalize": tool_upload_and_finalize,
}

# Progress mapping: tool name -> (job status string, base progress %)
PROGRESS_MAP = {
    "generate_veo_prompts": ("generating_prompts", 15),
    "generate_video_clip": ("generating_videos", None),  # calculated per clip
    "verify_video_clip": ("verifying_clips", None),
    "merge_video_clips": ("merging_videos", 70),
    "enhance_voice": ("enhancing_voice", 85),
    "upload_and_finalize": ("finalizing", 95),
}

SYSTEM_INSTRUCTION = """You are an AI video ad creation agent. Your job is to create a professional video ad from a script and character image.

## What You Have
- A script (the dialogue the character will speak)
- A character image (already uploaded to cloud storage — you don't need to handle it)
- Configuration: voice preference, aspect ratio, resolution

## Your Goal
Create a final video ad (maximum 15 seconds total, maximum 2 clips) by:
1. Breaking the script into 1-2 segments and generating Veo video prompts
2. Generating video clips using Veo 3.1 (image-to-video with built-in lip-sync)
3. Verifying each clip matches the script (MANDATORY — every clip must be verified)
4. If verification fails (confidence < 0.6), regenerate the clip with an adjusted prompt (max 2 retries per clip)
5. Merging the verified clips into one video
6. Enhancing the voice using ElevenLabs Voice Changer
7. Uploading the final video and creating an asset record

## Important Rules
- The total ad duration must not exceed 15 seconds.
- Generate at most 2 video clips.
- ALWAYS verify clips after generation. If a clip fails verification, adjust the visual prompt to better match the script and regenerate.
- Do NOT try to pass image or video data in your messages. Always work with cloud storage URLs that the tools return.
- When generating Veo prompts, the exact script text will be preserved for lip-sync. Do not paraphrase the dialogue.
- After finishing all steps, provide a final summary as JSON in this exact format:
  {"final_video_url": "<url>", "clips_generated": <number>, "total_duration_seconds": <number>}

## Error Handling
- If a tool returns an error, analyze it and decide: retry with adjusted parameters, or skip the step if non-critical.
- Content policy errors from video generation: try adjusting the visual prompt to be less specific about people/faces.
- Voice enhancement failures: the merged video without enhancement is still usable.
- If all retries for a clip fail, proceed with whatever clips succeeded."""


def _build_tool_definitions() -> List[Dict[str, Any]]:
    """Build Anthropic tool definitions for all 6 tools."""
    return [
        {
            "name": "generate_veo_prompts",
            "description": (
                "Break an ad script into 1-2 segments and generate optimized Veo 3.1 "
                "video prompts for each segment. Each prompt describes camera angles, "
                "character actions, scenery, and movement. The script text is preserved "
                "exactly as-is for lip-sync — never paraphrased.\n\n"
                "Returns an array of objects, each with a 'veo_prompt' (visual description "
                "for Veo) and 'script_segment' (exact dialogue for that clip).\n\n"
                "Limitations:\n"
                "- Maximum 2 segments (clips) to keep total ad under 15 seconds\n"
                "- Each clip will be 6-8 seconds\n"
                "- Script segments use the EXACT words from the original script\n\n"
                "Call this first to plan the video clips before generating them."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "The full ad script (dialogue the character will speak)",
                    },
                    "character_name": {
                        "type": "string",
                        "description": "Name of the character (used in visual descriptions). Defaults to 'character'.",
                    },
                },
                "required": ["script"],
            },
        },
        {
            "name": "generate_video_clip",
            "description": (
                "Generate a single video clip using Google Veo 3.1 image-to-video. "
                "The character image is used as the starting frame, and Veo generates "
                "a video with built-in lip-sync matching the script dialogue.\n\n"
                "This tool blocks until the video is fully generated and uploaded to "
                "cloud storage (typically 2-5 minutes per clip). Returns a cloud storage "
                "URL for the generated clip.\n\n"
                "IMPORTANT: The tool always uses the original character image for every "
                "clip. Do NOT try to extract frames from previous clips.\n\n"
                "Limitations:\n"
                "- Valid durations: 6 or 8 seconds only\n"
                "- May fail due to content safety filters — retry with a less specific "
                "visual prompt if this happens\n"
                "- Retries internally up to 3 times on timeout\n\n"
                "Call this once per clip after generating prompts. Pass the veo_prompt "
                "and script_segment from generate_veo_prompts."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_number": {
                        "type": "integer",
                        "description": "Zero-based clip index (0 for first clip, 1 for second)",
                    },
                    "veo_prompt": {
                        "type": "string",
                        "description": "The visual description prompt for Veo (camera angles, actions, scenery)",
                    },
                    "script_segment": {
                        "type": "string",
                        "description": "The exact dialogue text the character should speak in this clip",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "enum": [6, 8],
                        "description": "Clip duration in seconds. Use 8 for most clips.",
                    },
                },
                "required": ["clip_number", "veo_prompt", "script_segment"],
            },
        },
        {
            "name": "verify_video_clip",
            "description": (
                "Verify that a generated video clip matches its intended script content "
                "using Gemini Vision analysis. The tool downloads the clip from its cloud "
                "storage URL, analyzes it, and returns a verification score.\n\n"
                "Returns a confidence score (0.0-1.0) and detailed feedback. A score >= 0.6 "
                "is considered passing.\n\n"
                "MANDATORY: Call this after EVERY generate_video_clip call. If verification "
                "fails (score < 0.6), regenerate the clip with an adjusted visual prompt "
                "(max 2 retries per clip).\n\n"
                "Example adjustment: If feedback says 'character appears static', add more "
                "movement and gesture descriptions to the veo_prompt."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_number": {
                        "type": "integer",
                        "description": "Zero-based clip index being verified",
                    },
                    "clip_gcs_url": {
                        "type": "string",
                        "description": "Cloud storage URL of the video clip to verify",
                    },
                    "script_segment": {
                        "type": "string",
                        "description": "The expected dialogue/script text for this clip",
                    },
                    "veo_prompt": {
                        "type": "string",
                        "description": "The Veo prompt that was used to generate this clip",
                    },
                },
                "required": ["clip_number", "clip_gcs_url", "script_segment", "veo_prompt"],
            },
        },
        {
            "name": "merge_video_clips",
            "description": (
                "Merge multiple video clips into a single continuous video using ffmpeg. "
                "Takes cloud storage URLs of individual clips and produces one merged video.\n\n"
                "Streams clips directly from cloud storage (no local download of source clips). "
                "Returns a cloud storage URL for the merged video.\n\n"
                "For a single clip, this returns the same URL without re-encoding.\n\n"
                "Limitations:\n"
                "- All clips must be the same resolution and aspect ratio\n"
                "- Audio tracks are preserved and concatenated\n"
                "- Maximum 2 clips supported\n\n"
                "Call this after all clips have been generated and verified."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_gcs_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of cloud storage URLs for clips to merge (first clip first)",
                    },
                },
                "required": ["clip_gcs_urls"],
            },
        },
        {
            "name": "enhance_voice",
            "description": (
                "Enhance the voice quality in a merged video using ElevenLabs Voice "
                "Changer (Speech-to-Speech). Extracts the audio track, applies professional "
                "voice enhancement, and replaces the original audio.\n\n"
                "Returns a cloud storage URL for the voice-enhanced video.\n\n"
                "The default voice is 'Bella'. If no voice_id is provided, the tool "
                "searches for Bella automatically.\n\n"
                "Limitations:\n"
                "- Processing takes 30-60 seconds\n"
                "- If the voice is not found, returns the original merged video URL unchanged\n"
                "- Non-critical step: if enhancement fails, the merged video is still usable\n\n"
                "Call this after merge_video_clips."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "merged_video_url": {
                        "type": "string",
                        "description": "Cloud storage URL of the merged video",
                    },
                    "voice_id": {
                        "type": "string",
                        "description": "ElevenLabs voice ID to use. If omitted, uses the Bella voice.",
                    },
                },
                "required": ["merged_video_url"],
            },
        },
        {
            "name": "upload_and_finalize",
            "description": (
                "Finalize the ad creation by creating an asset record in the database. "
                "The video should already be in cloud storage from previous steps.\n\n"
                "Returns the final signed URL (valid for 7 days) and the asset ID.\n\n"
                "Call this as the very last step after voice enhancement is complete."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "final_video_url": {
                        "type": "string",
                        "description": "Cloud storage URL of the final enhanced video",
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
    ):
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

        # Track clips generated/verified for progress calculation
        self._clips_generated = 0
        self._clips_verified = 0
        self._total_clips = 0

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
                logger.info(f"[{self.ctx.job_id}] Agent completed: {final_text[:200]}...")
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

                        logger.info(f"[{self.ctx.job_id}] Executing tool: {tool_name}")

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

    async def _update_progress(self, tool_name: str, result: Dict[str, Any]) -> None:
        """Update job progress in Firestore based on which tool just executed."""
        status_str, base_progress = PROGRESS_MAP.get(tool_name, (None, None))

        # Calculate dynamic progress for clip-related tools
        if tool_name == "generate_veo_prompts" and "total_clips" in result:
            self._total_clips = result["total_clips"]

        if tool_name == "generate_video_clip" and result.get("status") == "completed":
            self._clips_generated += 1
            # Progress: 20% (prompts done) + clip generation spans 20-55%
            if self._total_clips > 0:
                base_progress = 20 + int((self._clips_generated / self._total_clips) * 35)

        if tool_name == "verify_video_clip":
            self._clips_verified += 1
            if self._total_clips > 0:
                base_progress = 55 + int((self._clips_verified / self._total_clips) * 10)

        # Update Firestore job
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
            f"**Aspect Ratio:** {aspect_ratio}",
            f"**Resolution:** {resolution}",
        ]

        if voice_id:
            parts.append(f"**Voice ID:** {voice_id}")
        else:
            parts.append(f"**Voice:** Use the default Bella voice")

        parts.extend([
            f"",
            f"The character image is already uploaded to cloud storage and will be "
            f"used automatically by the video generation tool. You do not need to "
            f"handle the image.",
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
        return {"final_video_url": None, "raw_response": text[:500]}
