"""Google Gemini client using the google-genai SDK with Vertex AI."""
import os
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# Default system instruction for the legacy (non-agentic) pipeline.
# The agentic orchestrator passes its own system_prompt via the tool call.
DEFAULT_VEO_PROMPT_SYSTEM_INSTRUCTION = """You are an expert video director specialized in creating prompts for Google Veo 3.1.

Create DYNAMIC, ACTION-ORIENTED video ad prompts where a character moves, demonstrates, and shows things related to what they're saying, AND extract corresponding script segments.

REQUIREMENTS:
- Each segment should be 6-7 seconds of speaking time (15-20 words, 60-80 characters)
- Create BALANCED segments - avoid very short clips
- Character must be IN MOTION - walking, gesturing, pointing, demonstrating
- Actions must RELATE TO the script content
- Use DYNAMIC camera movements (tracking, panning)
- Describe camera angles, lighting, character expressions AND movements
- The avatar MUST speak ONLY the EXACT words from the script - NO paraphrasing
- Put the EXACT script text in the script_segments array
- After the script segment ends, the avatar should STOP SPEAKING - just smile, walk, or gesture silently
- NO text overlays, captions, or on-screen text in prompts
- NO repeating script words in the visual description

Output format: Return a JSON object with two arrays:
- "prompts": Array of Veo 3.1 video prompts (visuals and actions ONLY)
- "script_segments": Array of EXACT script text from the original script"""


class GeminiClient:
    """Client for Google Gemini AI via the google-genai SDK (Vertex AI)."""

    def __init__(self, api_key: Optional[str] = None, storage_client=None, job_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Initialize Gemini client using google-genai SDK with Vertex AI.

        Args:
            api_key: Not used — Vertex AI uses ADC
            storage_client: Optional GCS storage client for saving prompts/responses
            job_id: Optional job ID for GCS logging
            user_id: Optional user ID for GCS logging
        """
        self.model = settings.GEMINI_MODEL
        self.timeout = settings.GEMINI_TIMEOUT
        self.storage = storage_client
        self.job_id = job_id
        self.user_id = user_id

        # Initialize google-genai client with Vertex AI
        self.client = genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=settings.GEMINI_REGION,
        )

        # Lazy-init client for image generation (may need different region)
        self._image_client: Optional[genai.Client] = None
        self._image_model = settings.GEMINI_IMAGE_MODEL
        self._image_region = settings.GEMINI_IMAGE_REGION

        logger.info(f"GeminiClient initialized with google-genai SDK (Vertex AI) "
                     f"project={settings.GCP_PROJECT_ID}, location={settings.GEMINI_REGION}, model={self.model}")

    async def _save_to_gcs(self, filename: str, data: dict):
        """Save data to GCS for debugging and analysis."""
        if not self.storage or not self.job_id or not self.user_id:
            logger.debug("GCS storage not configured, skipping save")
            return

        try:
            blob_path = f"{self.user_id}/{self.job_id}/{filename}"
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            blob = self.storage.bucket.blob(blob_path)
            blob.upload_from_string(json_data, content_type="application/json")
            logger.info(f"Saved Gemini log to GCS: {blob_path}")
        except Exception as e:
            logger.warning(f"Failed to save to GCS: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Generate text using Gemini via the google-genai SDK.

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Creativity level (0.0-1.0)

        Returns:
            Generated text response
        """
        if temperature is None:
            temperature = settings.GEMINI_TEMPERATURE

        config = types.GenerateContentConfig(
            temperature=temperature,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            text = response.text
            logger.info(f"Gemini generated {len(text)} characters using model {self.model}")
            return text

        except Exception as e:
            logger.error(f"Gemini generate_text failed: {e}")
            raise

    async def generate_veo_prompts_with_segments(
        self,
        script: str,
        system_instruction: str,
        num_segments: int,
        character_name: str = "character",
    ) -> tuple[List[str], List[str]]:
        """Gemini text generation: break script into segments with Veo prompts."""
        prompt = f"""Script (USE THESE EXACT WORDS ONLY - VERBATIM):
"{script}"

Character: {character_name}
Number of segments: {num_segments}
"""

        response = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
        )

        # Save prompt and response to GCS for debugging
        await self._save_to_gcs("gemini_prompt_generation.json", {
            "timestamp": datetime.utcnow().isoformat(),
            "model": self.model,
            "system_instruction": system_instruction,
            "user_prompt": prompt,
            "response": response,
            "original_script": script,
            "character_name": character_name,
        })

        # Parse JSON from response
        import re

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            prompts = data.get("prompts", [])
            segments = data.get("script_segments", [])

            if len(prompts) != len(segments):
                raise RuntimeError(
                    f"Gemini returned {len(prompts)} prompts but {len(segments)} script_segments — arrays must match"
                )

            if len(prompts) != num_segments:
                raise RuntimeError(
                    f"Requested {num_segments} segments but Gemini returned {len(prompts)}"
                )

            # Save parsed results to GCS
            await self._save_to_gcs("gemini_parsed_prompts.json", {
                "timestamp": datetime.utcnow().isoformat(),
                "prompts": prompts,
                "script_segments": segments,
                "total_clips": len(prompts),
            })

            logger.info(f"Generated {len(prompts)} prompts with script segments")
            return prompts, segments
        else:
            raise RuntimeError(f"Gemini returned unparseable response: {response}")

    async def analyze_video_content(
        self,
        video_url: str,
        system_instruction: str,
        script_segment: str,
        prompt: str,
        clip_label: str = "clip",
    ) -> Dict[str, Any]:
        """Gemini Vision: analyze a video clip against script and prompt."""
        import tempfile

        # Download the video
        video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name

        async with httpx.AsyncClient(timeout=self.timeout) as http_client:
            try:
                response = await http_client.get(video_url)
                response.raise_for_status()
                with open(video_path, 'wb') as f:
                    f.write(response.content)
            except Exception as e:
                logger.error(f"Failed to download video for analysis: {e}")
                raise

        try:
            with open(video_path, 'rb') as f:
                video_bytes = f.read()
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

        analysis_prompt = f"""Analyze this video clip. Listen to the spoken dialogue AND evaluate the visuals.

**Expected Script Segment:**
"{script_segment}"

**Veo Prompt Used:**
"{prompt}"

Return your analysis as JSON with keys: confidence_score, description."""

        try:
            config = types.GenerateContentConfig(
                temperature=settings.GEMINI_VISION_TEMPERATURE,
                system_instruction=system_instruction,
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
                        types.Part.from_text(text=analysis_prompt),
                    ],
                ),
                config=config,
            )

            text = response.text

            # Parse JSON from response
            import re

            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                logger.info(f"Video analysis complete: confidence={analysis.get('confidence_score', 0)}")

                await self._save_to_gcs(f"clip_verification_{clip_label}.json", {
                    "timestamp": datetime.utcnow().isoformat(),
                    "model": self.model,
                    "video_url": video_url,
                    "system_instruction": system_instruction,
                    "script_segment": script_segment,
                    "veo_prompt": prompt,
                    "raw_response": text,
                    "parsed_analysis": analysis,
                })

                return analysis
            else:
                logger.warning("Could not parse video analysis JSON")

                await self._save_to_gcs(f"clip_verification_{clip_label}.json", {
                    "timestamp": datetime.utcnow().isoformat(),
                    "model": self.model,
                    "video_url": video_url,
                    "script_segment": script_segment,
                    "raw_response": text,
                    "parse_error": True,
                })

                return {
                    "confidence_score": 0.0,
                    "description": f"Failed to parse analysis response. Raw: {text}",
                }

        except Exception as e:
            logger.error(f"Video analysis failed: {e}")
            raise

    def _get_image_client(self) -> genai.Client:
        """Get or create a genai client for image generation.

        Image generation models may require a different region than text models.
        Lazily creates a separate client instance if needed.
        """
        if self._image_client is None:
            if self._image_region == settings.GEMINI_REGION:
                self._image_client = self.client
            else:
                self._image_client = genai.Client(
                    vertexai=True,
                    project=settings.GCP_PROJECT_ID,
                    location=self._image_region,
                )
                logger.info(
                    f"Initialized image generation client "
                    f"(region={self._image_region}, model={self._image_model})"
                )
        return self._image_client

    async def generate_scene_image(
        self,
        prompt: str,
        character_image_b64: Optional[str] = None,
        aspect_ratio: str = "16:9",
    ) -> bytes:
        """
        Generate a scene image using Gemini's image generation model.

        The prompt is passed directly to the model. When a character reference
        image is provided, it is included alongside the prompt so the generated
        image features that character.

        Args:
            prompt: The image generation prompt (crafted by the orchestrator)
            character_image_b64: Optional base64-encoded character reference image
            aspect_ratio: Desired aspect ratio (e.g., "16:9", "9:16")

        Returns:
            Generated image as raw bytes (PNG)

        Raises:
            RuntimeError: If image generation fails or no image is returned
        """
        import base64

        image_client = self._get_image_client()

        image_aspect = aspect_ratio or settings.VEO_DEFAULT_ASPECT_RATIO

        safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ]

        config = types.GenerateContentConfig(
            temperature=settings.GEMINI_IMAGE_TEMPERATURE,
            top_p=settings.GEMINI_IMAGE_TOP_P,
            max_output_tokens=settings.GEMINI_IMAGE_MAX_TOKENS,
            response_modalities=["TEXT", "IMAGE"],
            safety_settings=safety_settings,
            image_config=types.ImageConfig(
                aspect_ratio=image_aspect,
                image_size=settings.GEMINI_IMAGE_SIZE,
                output_mime_type=settings.GEMINI_IMAGE_OUTPUT_MIME,
            ),
        )

        parts = []
        if character_image_b64:
            character_bytes = base64.b64decode(character_image_b64)
            parts.append(types.Part.from_bytes(data=character_bytes, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=prompt))

        contents = types.Content(role="user", parts=parts)

        try:
            response = await image_client.aio.models.generate_content(
                model=self._image_model,
                contents=contents,
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    image_bytes = part.inline_data.data
                    logger.info(
                        f"Scene image generated: {len(image_bytes)} bytes "
                        f"(model={self._image_model})"
                    )

                    await self._save_to_gcs("scene_image_generation.json", {
                        "timestamp": datetime.utcnow().isoformat(),
                        "model": self._image_model,
                        "prompt": prompt,
                        "aspect_ratio": image_aspect,
                        "image_size_bytes": len(image_bytes),
                    })

                    return image_bytes

            response_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    response_text += part.text

            raise RuntimeError(
                f"Gemini returned no image. Text response: {response_text}"
            )

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Scene image generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Scene image generation failed: {e}")
