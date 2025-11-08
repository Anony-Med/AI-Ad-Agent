"""Agent for generating Veo 3.1 prompts from scripts."""
import logging
from typing import List, Tuple
from app.ad_agent.clients.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class PromptGeneratorAgent:
    """Generates optimized Veo 3.1 prompts from ad scripts."""

    def __init__(self, api_key: str = None):
        """Initialize with Gemini client."""
        self.gemini = GeminiClient(api_key=api_key)

    async def generate_prompts(
        self,
        script: str,
        character_name: str = "character",
        max_clip_duration: int = 7,
    ) -> List[str]:
        """
        Generate Veo 3.1 video prompts from script.

        Args:
            script: The dialogue script
            character_name: Name of the character
            max_clip_duration: Max duration per clip (seconds)

        Returns:
            List of optimized Veo prompts
        """
        logger.info(f"Generating Veo prompts for script ({len(script)} characters)")

        prompts = await self.gemini.generate_veo_prompts(
            script=script,
            character_name=character_name,
        )

        # Validate and clean prompts
        valid_prompts = []
        for i, prompt in enumerate(prompts):
            if prompt and len(prompt.strip()) > 10:
                valid_prompts.append(prompt.strip())
                logger.info(f"Clip {i+1}: {len(prompt)} characters")
            else:
                logger.warning(f"Skipping invalid prompt at index {i}")

        if not valid_prompts:
            raise ValueError("No valid prompts generated from script")

        logger.info(f"Generated {len(valid_prompts)} valid Veo prompts")
        return valid_prompts

    async def generate_prompts_with_segments(
        self,
        script: str,
        character_name: str = "character",
        max_clip_duration: int = 7,
    ) -> Tuple[List[str], List[str]]:
        """
        Generate Veo 3.1 video prompts AND corresponding script segments.

        This is used for clip verification - we need to know which part of the
        script each clip should represent.

        Args:
            script: The dialogue script
            character_name: Name of the character
            max_clip_duration: Max duration per clip (seconds)

        Returns:
            Tuple of (prompts, script_segments)
        """
        logger.info(f"Generating Veo prompts with script segments ({len(script)} characters)")

        prompts, segments = await self.gemini.generate_veo_prompts_with_segments(
            script=script,
            character_name=character_name,
        )

        # Validate and clean
        valid_prompts = []
        valid_segments = []

        for i, (prompt, segment) in enumerate(zip(prompts, segments)):
            if prompt and len(prompt.strip()) > 10:
                valid_prompts.append(prompt.strip())
                valid_segments.append(segment.strip() if segment else "")
                logger.info(f"Clip {i+1}: {len(prompt)} chars prompt, {len(segment) if segment else 0} chars segment")
            else:
                logger.warning(f"Skipping invalid prompt at index {i}")

        if not valid_prompts:
            raise ValueError("No valid prompts generated from script")

        logger.info(f"Generated {len(valid_prompts)} valid prompts with segments")
        return valid_prompts, valid_segments

    async def enhance_prompt(self, base_prompt: str, character_image_description: str = None) -> str:
        """
        Enhance a single prompt with additional details.

        Args:
            base_prompt: The base prompt
            character_image_description: Optional character description

        Returns:
            Enhanced prompt
        """
        if not character_image_description:
            return base_prompt

        # Add character description to prompt
        enhanced = f"{base_prompt}\nCharacter details: {character_image_description}"
        return enhanced
