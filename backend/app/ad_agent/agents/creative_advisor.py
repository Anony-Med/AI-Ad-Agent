"""Agent for providing creative enhancement suggestions."""
import logging
from typing import Optional
from app.ad_agent.clients.gemini_client import GeminiClient
from app.ad_agent.interfaces.ad_schemas import CreativeSuggestion

logger = logging.getLogger(__name__)


class CreativeAdvisorAgent:
    """Provides creative suggestions for video enhancement."""

    def __init__(self, api_key: str = None):
        """Initialize with Gemini client."""
        self.gemini = GeminiClient(api_key=api_key)

    async def get_suggestions(
        self,
        script: str,
        video_description: Optional[str] = None,
    ) -> CreativeSuggestion:
        """
        Get creative enhancement suggestions.

        Args:
            script: The ad script
            video_description: Optional description of the merged video

        Returns:
            CreativeSuggestion with ideas
        """
        logger.info("Getting creative enhancement suggestions")

        # Build description
        desc = video_description or f"Video ad with script: {script}"

        # Get suggestions from Gemini
        suggestions_dict = await self.gemini.get_creative_suggestions(desc)

        # Convert to CreativeSuggestion model
        suggestion = CreativeSuggestion(
            animations=suggestions_dict.get("animations", []),
            text_overlays=suggestions_dict.get("text_overlays", []),
            gifs=suggestions_dict.get("gifs", []),
            effects=suggestions_dict.get("effects", []),
            general_feedback=suggestions_dict.get("general_feedback"),
        )

        logger.info(
            f"Generated suggestions: "
            f"{len(suggestion.animations)} animations, "
            f"{len(suggestion.text_overlays)} text overlays, "
            f"{len(suggestion.gifs)} gifs, "
            f"{len(suggestion.effects)} effects"
        )

        return suggestion
