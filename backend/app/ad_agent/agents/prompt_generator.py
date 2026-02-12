"""Agent for generating Veo 3.1 prompts from scripts."""
import logging
from typing import List, Tuple
from app.ad_agent.clients.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class PromptGeneratorAgent:
    """Generates optimized Veo 3.1 prompts from ad scripts."""

    def __init__(self, api_key: str = None, storage_client=None, job_id: str = None, user_id: str = None):
        """Initialize with Gemini client."""
        self.gemini = GeminiClient(
            api_key=api_key,
            storage_client=storage_client,
            job_id=job_id,
            user_id=user_id
        )

    @staticmethod
    def normalize_script(script: str) -> str:
        """
        Normalize script text to avoid character encoding issues in Veo.

        Replaces special characters with ASCII equivalents to prevent
        gibberish speech generation.

        Args:
            script: Original script text

        Returns:
            Normalized script with ASCII characters only
        """
        # Replace em dash with regular hyphen
        script = script.replace("—", "-")
        script = script.replace("–", "-")

        # Replace curly quotes with straight quotes
        script = script.replace(""", '"')
        script = script.replace(""", '"')
        script = script.replace("'", "'")
        script = script.replace("'", "'")

        # Replace ellipsis
        script = script.replace("…", "...")

        # Ensure UTF-8 compatibility
        script = script.encode('ascii', 'ignore').decode('ascii')

        logger.debug(f"Normalized script: {script[:100]}...")
        return script

    async def generate_prompts_with_segments(
        self,
        script: str,
        system_prompt: str,
        num_segments: int,
        character_name: str = "character",
    ) -> Tuple[List[str], List[str]]:
        """Gemini text generation: break script into segments with Veo prompts."""
        # Normalize script to remove special characters that cause gibberish speech
        script = self.normalize_script(script)
        logger.info(f"Generating Veo prompts with script segments ({len(script)} characters, {num_segments} segments)")

        prompts, segments = await self.gemini.generate_veo_prompts_with_segments(
            script=script,
            system_instruction=system_prompt,
            num_segments=num_segments,
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
