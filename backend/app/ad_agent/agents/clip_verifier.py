"""Clip Verification Agent - Verifies video clips match script content."""
import logging
from typing import Optional
from app.ad_agent.clients.gemini_client import GeminiClient
from app.ad_agent.interfaces.ad_schemas import ClipVerification
from app.config import settings

logger = logging.getLogger(__name__)


class ClipVerifierAgent:
    """Verifies generated video clips match their script segments using Gemini Vision."""

    def __init__(self, api_key: Optional[str] = None, confidence_threshold: Optional[float] = None):
        self.gemini = GeminiClient(api_key=api_key)
        self.confidence_threshold = confidence_threshold if confidence_threshold is not None else settings.VERIFICATION_THRESHOLD

    async def verify_clip_from_url(
        self,
        clip_gcs_url: str,
        system_prompt: str,
        script_segment: str,
        veo_prompt: str,
        clip_number: int = 0,
        variant_index: int = 0,
    ) -> ClipVerification:
        """Gemini Vision: verify a video clip matches its script."""
        logger.info(f"Verifying clip {clip_number} from URL: {clip_gcs_url[:80]}...")

        if not clip_gcs_url:
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                description="No video URL provided for verification",
            )

        try:
            analysis = await self.gemini.analyze_video_content(
                video_url=clip_gcs_url,
                system_instruction=system_prompt,
                script_segment=script_segment,
                prompt=veo_prompt,
                clip_label=f"clip{clip_number}_v{variant_index}",
            )

            confidence_score = analysis.get("confidence_score", 0.0)
            description = analysis.get("description", "")

            verified = confidence_score >= self.confidence_threshold

            logger.info(
                f"Clip {clip_number} verification: "
                f"verified={verified}, confidence={confidence_score:.2f}"
            )

            return ClipVerification(
                verified=verified,
                confidence_score=confidence_score,
                description=description,
                script_segment=script_segment,
                retry_count=0,
            )

        except Exception as e:
            logger.error(f"Failed to verify clip {clip_number}: {e}", exc_info=True)
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                description=f"Verification failed: {str(e)}",
            )
