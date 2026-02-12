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
    tool_generate_scene_image,
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
    "generate_scene_image": tool_generate_scene_image,
    "generate_video_clip": tool_generate_video_clip,
    "verify_video_clip": tool_verify_video_clip,
    "merge_video_clips": tool_merge_video_clips,
    "enhance_voice": tool_enhance_voice,
    "upload_and_finalize": tool_upload_and_finalize,
}

# Progress mapping: tool name -> (job status string, base progress %)
PROGRESS_MAP = {
    "generate_veo_prompts": ("generating_prompts", 10),
    "generate_scene_image": ("generating_scene_images", None),  # calculated per clip
    "generate_video_clip": ("generating_videos", None),  # calculated per clip
    "verify_video_clip": ("verifying_clips", None),
    "merge_video_clips": ("merging_videos", 70),
    "enhance_voice": ("enhancing_voice", 85),
    "upload_and_finalize": ("finalizing", 95),
}

SYSTEM_INSTRUCTION = """You are an AI video ad creation agent. Your job is to create a professional video ad from a script and character image.

## What You Have
- A script (the dialogue the character will speak)
- A character reference image (already uploaded to cloud storage)
- Configuration: voice preference, aspect ratio, resolution

## Workflow (follow this order)

### Step 1: Generate Prompts
Call `generate_veo_prompts` with:
- The full script
- `num_segments`: 2 (for a 15-second ad with ~7s per clip)
- `system_prompt`: Use the following system instruction for Gemini:

```
You are an expert video director specialized in creating prompts for Google Veo 3.1.

Create DYNAMIC, ACTION-ORIENTED video ad prompts where a character moves, demonstrates, and shows things related to what they're saying, AND extract corresponding script segments.

REQUIREMENTS:
- Each segment should be 7 seconds of speaking time (15-20 words, 60-80 characters)
- Put the EXACT script text in the script_segments array
- After the script segment ends, the avatar should STOP SPEAKING - just smile, walk, or gesture silently
- Show variety in the segments, it shouldn not look too boring. Like the character simply walking in the whole video would look boring. Change poses, background, actions to show variety.
- NO text overlays, captions, or on-screen text in prompts
- Enforce warm, Friendly, approachable voice for females.

Output format: Return a JSON object with two arrays:
- "prompts": Array of Veo 3.1 video prompts (visuals and actions ONLY)
- "script_segments": Array of EXACT script text from the original script
```

### Step 2: Generate Scene Images (for each clip)
For EACH clip, call `generate_scene_image` with a prompt and the clip_number.
The tool automatically attaches the character's reference photo alongside your prompt. The image model will see BOTH your text prompt AND the reference photo.
Your prompt should include:
- An instruction to use the attached reference photo as the character (e.g., "Generate a photorealistic image of the person shown in the reference photo...")
- The visual scene description (camera angle, setting, lighting, environment)
- That the image should be suitable as a starting frame for a video ad
- Use cream and tans or warm colors for outfit.

This step is MANDATORY — every clip needs a scene image before video generation.
If scene image generation fails, retry with a simplified description (max 2 retries per clip).

### Step 3: Generate Video Clips (for each clip)
For EACH clip, call `generate_video_clip` with the veo_prompt, script_segment, clip_number, AND the `scene_image_gcs_url` from Step 2.
The scene_image_gcs_url is required — the tool will fail without it.
The tool generates multiple video variants per clip in a single API call and returns all their GCS URLs in `clip_variant_urls`.

### Step 4: Verify and Select Clips (for each clip)
For EACH clip, verify the variants returned by Step 3 by calling `verify_video_clip` on each variant URL.
Pick the variant with the highest confidence score that passes the threshold (>= 0.95).
If no variant passes, retry from Step 2 with an adjusted prompt (max 2 retries per clip).

Use the following `system_prompt` for verification:

```
You are a video content analyzer. Analyze BOTH the visual content AND the spoken audio/dialogue in the provided video.

Provide response in JSON format with:         

1) confidence_score: Float 0.0-1.0 calculated as follows:
- Dialogue accuracy : Does the character speak the COMPLETE expected script? Deduct heavily for missing words, gibberish, or words that don't match the expected script. Each word should be clearly articulated.
- Visual alignment : Does the scene match the visual prompt?
- Video quality : No abrupt starts/ends.
2) description: Description of your analysis.

Be strict with your analysis.
```

### Step 5: Merge Clips
Call `merge_video_clips` with the selected clip variant URLs (one per clip, the best from Step 4).

### Step 6: Enhance Voice(SKIP THIS STEP FOR NOW. DIRECTLY USE THE MERGED VIDEO FROM STEP 5 FOR FINALIZATION)
Call `enhance_voice` with the merged video URL. This is non-critical — if it fails, use the merged video.

### Step 7: Finalize
Call `upload_and_finalize` with the final video URL.

## Important Rules
- After finishing all steps, provide a final summary as JSON in this exact format:
  {"final_video_url": "<url>", "clips_generated": <number>, "total_duration_seconds": <number>}

## Error Handling
- If a tool returns an error, analyze it and decide: retry with adjusted parameters. If retries are exhausted, fail the whole process with an error message.
- Content policy errors from video generation: try adjusting the visual prompt to be less specific about people/faces.
"""


def _build_tool_definitions() -> List[Dict[str, Any]]:
    """Build Anthropic tool definitions for all 7 tools."""
    return [
        {
            "name": "generate_veo_prompts",
            "description": (
                "Calls Gemini text generation to break a script into segments and generate "
                "a Veo 3.1 video prompt for each segment. Returns {prompts: [{clip_number, "
                "veo_prompt, script_segment}], total_clips}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "The complete ad script with all dialogue.",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "System instruction for Gemini controlling how Veo prompts are generated.",
                    },
                    "num_segments": {
                        "type": "integer",
                        "description": "Number of segments to split the script into.",
                    },
                    "character_name": {
                        "type": "string",
                        "description": "Character name used in generated prompts. Defaults to 'character'.",
                    },
                },
                "required": ["script", "system_prompt", "num_segments"],
            },
        },
        {
            "name": "generate_scene_image",
            "description": (
                "Calls Gemini image generation to create a scene image from a prompt and the "
                "character reference photo. Saves the result to GCS. Returns {status, "
                "clip_number, scene_image_gcs_url}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Image generation prompt describing the scene, character pose, camera angle, and lighting.",
                    },
                    "clip_number": {
                        "type": "integer",
                        "description": "Zero-based clip index this scene image is for.",
                    },
                },
                "required": ["prompt", "clip_number"],
            },
        },
        {
            "name": "generate_video_clip",
            "description": (
                "Calls Veo 3.1 image-to-video API to generate multiple video clip variants from a "
                "scene image with lip-synced dialogue. Saves all variants to GCS. Returns {status, "
                "clip_number, clip_variant_urls, variants_generated}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_number": {
                        "type": "integer",
                        "description": "Zero-based clip index.",
                    },
                    "veo_prompt": {
                        "type": "string",
                        "description": "Visual description prompt for Veo (camera angles, actions, scenery).",
                    },
                    "script_segment": {
                        "type": "string",
                        "description": "Exact dialogue text for lip-sync.",
                    },
                    "scene_image_gcs_url": {
                        "type": "string",
                        "description": "GCS URL of the scene image to use as the starting frame.",
                    },
                },
                "required": ["clip_number", "veo_prompt", "script_segment", "scene_image_gcs_url"],
            },
        },
        {
            "name": "verify_video_clip",
            "description": (
                "Calls Gemini Vision to analyze a video clip and verify it matches the intended "
                "script and prompt. Returns {clip_number, verified, confidence_score, "
                "description}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_number": {
                        "type": "integer",
                        "description": "Zero-based clip index.",
                    },
                    "clip_gcs_url": {
                        "type": "string",
                        "description": "GCS URL of the video clip to analyze.",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "System instruction for Gemini Vision controlling how verification is performed.",
                    },
                    "script_segment": {
                        "type": "string",
                        "description": "Expected dialogue for this clip.",
                    },
                    "veo_prompt": {
                        "type": "string",
                        "description": "Visual prompt used to generate this clip.",
                    },
                },
                "required": ["clip_number", "clip_gcs_url", "system_prompt", "script_segment", "veo_prompt"],
            },
        },
        {
            "name": "merge_video_clips",
            "description": (
                "Uses ffmpeg to concatenate multiple video clips into a single video. "
                "Uploads the merged result to GCS. Returns {merged_video_url, "
                "total_duration_seconds}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "clip_gcs_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of GCS URLs for the clips to merge.",
                    },
                },
                "required": ["clip_gcs_urls"],
            },
        },
        {
            "name": "enhance_voice",
            "description": (
                "Runs the audio track through ElevenLabs Speech-to-Speech voice changer, "
                "then replaces the original audio. Uploads the result to GCS. Returns "
                "{enhanced_video_url, voice_used}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "merged_video_url": {
                        "type": "string",
                        "description": "GCS URL of the video whose audio should be enhanced.",
                    },
                    "voice_id": {
                        "type": "string",
                        "description": "ElevenLabs voice ID. Defaults to the configured voice if omitted.",
                    },
                },
                "required": ["merged_video_url"],
            },
        },
        {
            "name": "upload_and_finalize",
            "description": (
                "Creates an asset record in Firestore for the final video. Returns "
                "{final_video_url, asset_id, status}."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "final_video_url": {
                        "type": "string",
                        "description": "GCS URL of the finished video to register.",
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
        self._scene_images_generated = 0
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

        if tool_name == "generate_scene_image" and result.get("status") == "completed":
            self._scene_images_generated += 1
            # Progress: 10-18% range (after prompts, before video gen)
            if self._total_clips > 0:
                base_progress = 10 + int((self._scene_images_generated / self._total_clips) * 8)

        if tool_name == "generate_video_clip" and result.get("status") == "completed":
            self._clips_generated += 1
            # Progress: 18-55% range (after scene images)
            if self._total_clips > 0:
                base_progress = 18 + int((self._clips_generated / self._total_clips) * 37)

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
            f"The character reference image is already uploaded to cloud storage "
            f"and will be automatically included by the scene image generation tool. "
            f"You do not need to handle the image directly.",
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
