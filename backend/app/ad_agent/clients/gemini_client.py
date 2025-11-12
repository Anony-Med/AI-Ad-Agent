"""Direct Gemini API client for text/chat generation."""
import os
import logging
from typing import Optional, List, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for Google Gemini AI text generation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            api_key: Google AI API key. If not provided, reads from environment.
        """
        self.api_key = api_key or os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_AI_API_KEY or GEMINI_API_KEY environment variable required")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash-exp"  # Fast and efficient
        self.timeout = 120

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
● Each Veo 3.1 video can be a maximum of 7 seconds
● Character must be IN MOTION - walking, gesturing, pointing, demonstrating, interacting with environment
● Actions must RELATE TO the script content (e.g., if talking about houses, show houses; if talking about features, point to them)
● The character's lip-sync aligns with the dialogue
● Use DYNAMIC camera movements (walking with character, panning, tracking shots)
● Show visual elements that reinforce what's being said (scenery, setting, environment)
● Avoid static/stationary poses - character should be actively doing something
● Describe camera angles, lighting, character expressions AND movements

STRICT SCRIPT ADHERENCE RULES:
● Use ONLY the EXACT words from the script - do NOT add extra dialogue or paraphrase
● Do NOT repeat words from the script in the prompt
● Do NOT add filler words or extra speech not in the original script
● If a segment is short, let there be SILENCE with visual action only
● Better to have silence than to add words not in the script

FORBIDDEN ELEMENTS:
● NO text animations, captions, or on-screen text overlays in prompts
● NO repeating script words in the visual description
● NO going off-script or adding dialogue

Output format: Return a JSON object with two arrays:
- "prompts": Array of DYNAMIC Veo 3.1 video prompts with movement and actions (describe visuals, scenery, and actions ONLY - quote the EXACT script text separately)
- "script_segments": Array of EXACT script text from the original script (what's spoken in each clip)

Be precise - use the exact script words without modification."""

        prompt = f"""Script (USE EXACT WORDS):
"{script}"

Character: {character_name}

Break this script into:
1. DYNAMIC Veo 3.1 video prompts (describe camera, scenery, setting, ACTION, MOVEMENT - but DO NOT repeat the script words in the description)
2. Corresponding EXACT script segments (use exact words from the script above)

Each clip should be 7 seconds max.

CRITICAL RULES:
1. Use the EXACT WORDS from the script in script_segments - do not paraphrase or add dialogue
2. Split the script naturally across multiple clips (cover ALL the script text)
3. Character must be MOVING and SHOWING things related to the script
4. Include rich scenery/environment descriptions in prompts
5. DO NOT include text overlays, captions, or animations in prompts
6. DO NOT repeat the script words when describing the visual scene
7. If a segment is short, allow SILENCE with visual action only
8. Better to have silence than add words not in the script

Return in this JSON format with DYNAMIC prompts:
{{
  "prompts": [
    "Medium shot of {character_name} walking toward camera along a suburban street lined with houses, warm afternoon lighting. She gestures toward the houses. Camera tracks alongside her movement. Natural, engaging energy."
  ],
  "script_segments": [
    "Tired of hurricanes, repairs, or just ready for a change?"
  ]
}}

Generate DYNAMIC prompts NOW (remember: scenery descriptions YES, text overlays NO, exact script words only, allow silence):"""

        response = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.7,
            max_tokens=2048,
        )

        # Parse JSON from response
        import json
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
