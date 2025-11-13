"""Direct Gemini API client for text/chat generation."""
import os
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for Google Gemini AI text generation."""

    def __init__(self, api_key: Optional[str] = None, storage_client=None, job_id: Optional[str] = None, user_id: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            api_key: Google AI API key. If not provided, reads from environment.
            storage_client: Optional GCS storage client for saving prompts/responses
            job_id: Optional job ID for GCS logging
            user_id: Optional user ID for GCS logging
        """
        self.api_key = api_key or os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_AI_API_KEY or GEMINI_API_KEY environment variable required")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash-exp"  # Fast and efficient
        self.timeout = 120
        self.storage = storage_client
        self.job_id = job_id
        self.user_id = user_id

    async def _save_to_gcs(self, filename: str, data: dict):
        """Save data to GCS for debugging and analysis."""
        if not self.storage or not self.job_id or not self.user_id:
            logger.debug("GCS storage not configured, skipping save")
            return

        try:
            from app.config import settings
            blob_path = f"{self.user_id}/{self.job_id}/{filename}"

            # Convert data to JSON string
            json_data = json.dumps(data, indent=2, ensure_ascii=False)

            # Upload to GCS
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
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate text using Gemini.

        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        # Build request payload
        contents = [{"role": "user", "parts": [{"text": prompt}]}]

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]

                logger.info(f"Gemini generated {len(text)} characters")
                return text

            except httpx.HTTPStatusError as e:
                logger.error(f"Gemini API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Gemini request failed: {e}")
                raise

    async def generate_veo_prompts(self, script: str, character_name: str = "character") -> List[str]:
        """
        Generate Veo 3.1 prompts from a script.

        Args:
            script: The dialogue script
            character_name: Name of the character

        Returns:
            List of Veo prompts (max 7 seconds each)
        """
        system_instruction = """You are an expert video director specialized in creating prompts for Google Veo 3.1.

Your task: Create DYNAMIC, ACTION-ORIENTED video ad prompts where a character moves, demonstrates, and shows things related to what they're saying.

CRITICAL REQUIREMENTS:
● Each Veo 3.1 video can be a maximum of 7 seconds
● Character must be IN MOTION - walking, gesturing, pointing, demonstrating, interacting with environment
● Actions must RELATE TO the script content (e.g., if talking about houses, show houses; if talking about features, point to them)
● The character's lip-sync aligns with the dialogue
● Use DYNAMIC camera movements (walking with character, panning, tracking shots)
● Show visual elements that reinforce what's being said
● Avoid static/stationary poses - character should be actively doing something
● Describe camera angles, lighting, character expressions AND movements
● Focus on natural, professional presentation with energy and purpose

Output format: Return ONLY a JSON array of prompt strings, no additional text."""

        prompt = f"""Script:
"{script}"

Character: {character_name}

Break this script into DYNAMIC Veo 3.1 video prompts. Each clip should be 7 seconds max.

IMPORTANT: Character must be MOVING and SHOWING things related to the script, NOT standing still.

Example format with MOVEMENT:
[
  "Medium shot of {character_name} walking toward camera along a suburban street lined with houses, warm afternoon lighting. She gestures toward the houses while speaking energetically: 'Tired of hurricanes and repairs?' Camera tracks alongside her movement. She points at a damaged roof, showing concern.",
  "Close-up tracking shot of {character_name} walking through a bright, modern home interior. She runs her hand along a pristine countertop while saying: 'We buy houses as-is.' Camera follows her fluid movement through the space. Natural window light.",
  "{character_name} walks up to a house's front door, camera following from behind, then she turns to face camera with a warm smile: 'No repairs needed.' She gestures broadly at the house behind her. Confident, reassuring energy."
]

Generate DYNAMIC prompts with movement and actions now:"""

        response = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=2048,
        )

        # Parse JSON from response
        import json
        import re

        # Try to extract JSON array from response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            prompts = json.loads(json_match.group())
            logger.info(f"Generated {len(prompts)} Veo prompts")
            return prompts
        else:
            # Fallback: split by newlines
            prompts = [line.strip() for line in response.split('\n') if line.strip() and not line.strip().startswith('#')]
            logger.warning("Could not parse JSON, using fallback parsing")
            return prompts

    async def generate_veo_prompts_with_segments(
        self,
        script: str,
        character_name: str = "character"
    ) -> tuple[List[str], List[str]]:
        """
        Generate Veo 3.1 prompts AND extract corresponding script segments.

        Args:
            script: The dialogue script
            character_name: Name of the character

        Returns:
            Tuple of (prompts, script_segments) where each prompt has a corresponding segment
        """
        system_instruction = """You are an expert video director specialized in creating prompts for Google Veo 3.1.

Your task: Create DYNAMIC, ACTION-ORIENTED video ad prompts where a character moves, demonstrates, and shows things related to what they're saying, AND extract corresponding script segments.

CRITICAL REQUIREMENTS:
● Each Veo 3.1 video should be 6-7 seconds of speaking time (not too short!)
● Segment the script into BALANCED chunks of 15-20 words each (60-80 characters)
● Avoid creating very short 2-3 second segments - combine them to reach 6-7 seconds
● Character must be IN MOTION - walking, gesturing, pointing, demonstrating, interacting with environment
● Actions must RELATE TO the script content (e.g., if talking about houses, show houses; if talking about features, point to them)
● The character's lip-sync aligns with the dialogue
● Use DYNAMIC camera movements (walking with character, panning, tracking shots)
● Show visual elements that reinforce what's being said (scenery, setting, environment)
● Avoid static/stationary poses - character should be actively doing something
● Describe camera angles, lighting, character expressions AND movements

STRICT SCRIPT ADHERENCE RULES - CRITICAL:
● The avatar MUST speak ONLY the EXACT words from the script - NO paraphrasing, NO additions
● Put the EXACT script text in "quotes" in the script_segments array
● The avatar will lip-sync to these EXACT words - any deviation will cause misalignment
● Do NOT add filler words, extra dialogue, or modify the script in ANY way
● If a segment is short, allow SILENCE with visual action only
● Better to have silence than to add words not in the original script
● The script text is SACRED - use it verbatim without ANY changes

AFTER SCRIPT FINISHES - CRITICAL:
● If the avatar finishes speaking the script segment before the video ends, DO NOT SPEAK ANYTHING ELSE
● NO gibberish, NO additional words, NO mumbling, NO mouth movements that look like speaking
● Instead: smile, walk, gesture, look at camera, interact with environment - VISUAL ACTIONS ONLY
● The avatar should continue the scene naturally but SILENTLY after the script is done
● Example: After saying the line, avatar smiles warmly at camera, or continues walking, or gestures confidently
● NEVER add dialogue or speaking beyond the exact script segment

FORBIDDEN ELEMENTS:
● NO text animations, captions, or on-screen text overlays in prompts
● NO repeating script words in the visual description
● NO going off-script or adding dialogue
● NO speaking gibberish or additional words after the script segment ends

Output format: Return a JSON object with two arrays:
- "prompts": Array of DYNAMIC Veo 3.1 video prompts with movement and actions (describe visuals, scenery, and actions ONLY - quote the EXACT script text separately)
- "script_segments": Array of EXACT script text from the original script (what's spoken in each clip)

Be precise - use the exact script words without modification."""

        prompt = f"""Script (USE THESE EXACT WORDS ONLY - VERBATIM):
"{script}"

Character: {character_name}

Break this script into:
1. DYNAMIC Veo 3.1 video prompts (describe camera, scenery, setting, ACTION, MOVEMENT - but DO NOT repeat the script words in the description)
2. Corresponding EXACT script segments - COPY the exact words from the script above, word-for-word

SEGMENT LENGTH REQUIREMENTS:
● Each clip should be 6-7 seconds of speaking time (approximately 15-20 words or 60-80 characters per segment)
● Create BALANCED segments - avoid very short clips (2-3 seconds) that leave the avatar with nothing to say
● Distribute the script text EVENLY across all clips
● If a natural break creates a short segment, combine it with the previous or next segment to reach 6-7 seconds

🚨 CRITICAL RULES - THE AVATAR WILL SPEAK ONLY THESE EXACT WORDS:
1. Copy the EXACT WORDS from the script into script_segments - character by character, no modifications
2. The avatar's lip-sync depends on these EXACT words - any change will break synchronization
3. Put each script segment in "quotes" to ensure exact text is preserved
4. Split the script naturally across multiple clips (cover ALL the script text)
5. Character must be MOVING and SHOWING things related to the script
6. Include rich scenery/environment descriptions in prompts
7. DO NOT include text overlays, captions, or animations in prompts
8. DO NOT repeat the script words when describing the visual scene
9. If a segment is short, allow SILENCE with visual action only
10. Better to have silence than add words not in the script
11. NEVER paraphrase, summarize, or reword the script - use it VERBATIM
12. 🚨 AFTER SCRIPT ENDS: Avatar should STOP SPEAKING completely - just smile, walk, gesture, or do visual actions ONLY. NO gibberish, NO additional words, NO mouth movements that look like speaking

Return in this JSON format with DYNAMIC prompts:
{{
  "prompts": [
    "Medium shot of {character_name} walking toward camera along a suburban street lined with houses, warm afternoon lighting. She gestures toward the houses. Camera tracks alongside her movement. Natural, engaging energy."
  ],
  "script_segments": [
    "Tired of hurricanes, repairs, or just ready for a change?"
  ]
}}

Generate DYNAMIC prompts NOW (remember: scenery descriptions YES, text overlays NO, exact script words only, NO gibberish after script ends):"""

        response = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=2048,
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

        # Try to extract JSON object from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            prompts = data.get("prompts", [])
            segments = data.get("script_segments", [])

            # Ensure equal lengths
            min_len = min(len(prompts), len(segments))
            prompts = prompts[:min_len]
            segments = segments[:min_len]

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
            # Fallback: use simple method and split script evenly
            logger.warning("Could not parse JSON with segments, using fallback")
            prompts = await self.generate_veo_prompts(script, character_name)

            # Split script into equal segments
            words = script.split()
            words_per_segment = max(1, len(words) // len(prompts))

            segments = []
            for i in range(len(prompts)):
                start = i * words_per_segment
                end = start + words_per_segment if i < len(prompts) - 1 else len(words)
                segment = " ".join(words[start:end])
                segments.append(segment)

            return prompts, segments

    async def get_creative_suggestions(self, video_description: str) -> Dict[str, Any]:
        """
        Get creative enhancement suggestions for a video.

        Args:
            video_description: Description of the merged video

        Returns:
            Dict with suggestions for animations, text overlays, GIFs, effects
        """
        system_instruction = """You are a creative video editor expert specializing in social media ads.
Provide specific, actionable suggestions for enhancing videos.

Output format: Return ONLY a JSON object with these keys:
- animations: List of animation ideas
- text_overlays: List of text overlay suggestions
- gifs: List of GIF/emoji placement ideas
- effects: List of video effects to apply
- general_feedback: Brief overall feedback

Be specific and concise."""

        prompt = f"""Video description:
{video_description}

What animations, GIFs, text overlays, and effects would make this video more engaging?
Focus on:
- Highlighting key messages
- Adding visual interest
- Maintaining professional quality
- Suitable for ad campaigns

Provide suggestions in JSON format:"""

        response = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.8,
            max_tokens=1024,
        )

        # Parse JSON
        import json
        import re

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            suggestions = json.loads(json_match.group())
            logger.info("Generated creative suggestions")
            return suggestions
        else:
            logger.warning("Could not parse creative suggestions JSON")
            return {
                "animations": [],
                "text_overlays": [],
                "gifs": [],
                "effects": [],
                "general_feedback": response,
            }

    async def analyze_video_content(
        self,
        video_url: str,
        script_segment: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Analyze video content using Gemini Vision and verify it matches the script.

        Args:
            video_url: URL of the video to analyze
            script_segment: The script text this clip should represent
            prompt: The Veo prompt used to generate this clip

        Returns:
            Dict with verification results:
            {
                "visual_description": str,  # What's in the video
                "matches_script": bool,     # Does it match the script?
                "confidence_score": float,  # 0.0 to 1.0
                "alignment_feedback": str   # Detailed explanation
            }
        """
        # Download video to analyze
        import tempfile
        import base64

        video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(video_url)
                response.raise_for_status()
                with open(video_path, 'wb') as f:
                    f.write(response.content)
            except Exception as e:
                logger.error(f"Failed to download video for analysis: {e}")
                raise

        # Read and encode video
        try:
            with open(video_path, 'rb') as f:
                video_data = base64.b64encode(f.read()).decode('utf-8')
        finally:
            # Cleanup
            import os
            if os.path.exists(video_path):
                os.remove(video_path)

        # Use Gemini Vision to analyze the video
        url = f"{self.base_url}/models/gemini-2.0-flash-exp:generateContent?key={self.api_key}"

        system_instruction = """You are a video content analyzer. Analyze the provided video and verify if it matches the intended script and prompt.

Provide a detailed analysis in JSON format with:
1. visual_description: Describe what you see in the video (scene, character actions, expressions, setting)
2. matches_script: Boolean - does the visual content align with the script segment?
3. confidence_score: Float 0.0-1.0 indicating alignment confidence
4. alignment_feedback: Detailed explanation of how well it matches or what's missing

Be objective and specific in your analysis."""

        analysis_prompt = f"""Analyze this video clip and verify it matches the intended content.

**Expected Script Segment:**
"{script_segment}"

**Veo Prompt Used:**
"{prompt}"

**Your Task:**
1. Describe what you see in the video
2. Check if the visual content matches the script segment
3. Provide a confidence score (0.0 = no match, 1.0 = perfect match)
4. Explain alignment or misalignment

Return your analysis in this JSON format:
{{
  "visual_description": "what you see in the video",
  "matches_script": true/false,
  "confidence_score": 0.85,
  "alignment_feedback": "detailed explanation"
}}"""

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "video/mp4",
                            "data": video_data
                        }
                    },
                    {
                        "text": analysis_prompt
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.3,  # Lower temperature for objective analysis
                "maxOutputTokens": 1024,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=300) as client:  # Longer timeout for video analysis
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]

                # Parse JSON from response
                import json
                import re

                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    logger.info(f"Video analysis complete: confidence={analysis.get('confidence_score', 0)}")
                    return analysis
                else:
                    logger.warning("Could not parse video analysis JSON")
                    return {
                        "visual_description": text,
                        "matches_script": False,
                        "confidence_score": 0.0,
                        "alignment_feedback": "Failed to parse analysis response"
                    }

            except httpx.HTTPStatusError as e:
                logger.error(f"Gemini Vision API error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Video analysis failed: {e}")
                raise
