"""Clip Verification Agent - Verifies video clips match script content."""
import logging
from typing import List, Optional
from app.ad_agent.clients.gemini_client import GeminiClient
from app.ad_agent.interfaces.ad_schemas import VideoClip, ClipVerification
from app.config import settings

logger = logging.getLogger(__name__)


class ClipVerifierAgent:
    """
    Agent responsible for verifying that generated video clips match their script segments.

    Uses Gemini Vision to analyze video content and compare against expected script.
    Ensures visual content aligns with script (e.g., "leaky roofs" in script → roofs shown in video).
    """

    def __init__(self, api_key: Optional[str] = None, confidence_threshold: Optional[float] = None):
        """
        Initialize the clip verifier.

        Args:
            api_key: Google AI API key for Gemini Vision
            confidence_threshold: Minimum confidence score to pass verification (0.0-1.0)
        """
        self.gemini = GeminiClient(api_key=api_key)
        self.confidence_threshold = confidence_threshold if confidence_threshold is not None else settings.VERIFICATION_THRESHOLD

    async def verify_clip(
        self,
        clip: VideoClip,
        script_segment: str,
    ) -> ClipVerification:
        """
        Verify a single video clip matches its script segment.

        Args:
            clip: The video clip to verify
            script_segment: The script text this clip should represent

        Returns:
            ClipVerification with analysis results
        """
        logger.info(f"Verifying clip {clip.clip_number}: {clip.video_url[:50]}...")

        if not clip.video_url:
            logger.warning(f"Clip {clip.clip_number} has no video URL, skipping verification")
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                alignment_feedback="No video URL available for verification",
            )

        try:
            # Use Gemini Vision to analyze the video
            analysis = await self.gemini.analyze_video_content(
                video_url=clip.video_url,
                script_segment=script_segment,
                prompt=clip.prompt,
            )

            # Extract results
            visual_description = analysis.get("visual_description", "")
            matches_script = analysis.get("matches_script", False)
            confidence_score = analysis.get("confidence_score", 0.0)
            alignment_feedback = analysis.get("alignment_feedback", "")

            # Determine if verified based on confidence threshold
            verified = confidence_score >= self.confidence_threshold and matches_script

            logger.info(
                f"Clip {clip.clip_number} verification: "
                f"verified={verified}, confidence={confidence_score:.2f}"
            )

            return ClipVerification(
                verified=verified,
                confidence_score=confidence_score,
                visual_description=visual_description,
                script_segment=script_segment,
                alignment_feedback=alignment_feedback,
                retry_count=0,
            )

        except Exception as e:
            logger.error(f"Failed to verify clip {clip.clip_number}: {e}", exc_info=True)
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                alignment_feedback=f"Verification failed: {str(e)}",
            )

    async def verify_clip_from_url(
        self,
        clip_gcs_url: str,
        script_segment: str,
        veo_prompt: str,
        clip_number: int = 0,
    ) -> ClipVerification:
        """
        Verify a video clip from its GCS URL against script content.

        This is used by the agentic orchestrator which passes GCS URLs
        directly instead of VideoClip objects.

        Args:
            clip_gcs_url: Signed GCS URL of the video clip
            script_segment: The script text this clip should represent
            veo_prompt: The Veo prompt used to generate this clip
            clip_number: Clip index (for logging)

        Returns:
            ClipVerification with analysis results
        """
        logger.info(f"Verifying clip {clip_number} from URL: {clip_gcs_url[:80]}...")

        if not clip_gcs_url:
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                alignment_feedback="No video URL provided for verification",
            )

        try:
            analysis = await self.gemini.analyze_video_content(
                video_url=clip_gcs_url,
                script_segment=script_segment,
                prompt=veo_prompt,
            )

            visual_description = analysis.get("visual_description", "")
            matches_script = analysis.get("matches_script", False)
            confidence_score = analysis.get("confidence_score", 0.0)
            alignment_feedback = analysis.get("alignment_feedback", "")

            verified = confidence_score >= self.confidence_threshold and matches_script

            logger.info(
                f"Clip {clip_number} verification: "
                f"verified={verified}, confidence={confidence_score:.2f}"
            )

            return ClipVerification(
                verified=verified,
                confidence_score=confidence_score,
                visual_description=visual_description,
                script_segment=script_segment,
                alignment_feedback=alignment_feedback,
                retry_count=0,
            )

        except Exception as e:
            logger.error(f"Failed to verify clip {clip_number}: {e}", exc_info=True)
            return ClipVerification(
                verified=False,
                confidence_score=0.0,
                script_segment=script_segment,
                alignment_feedback=f"Verification failed: {str(e)}",
            )

    async def verify_all_clips(
        self,
        clips: List[VideoClip],
        script_segments: List[str],
    ) -> List[VideoClip]:
        """
        Verify all video clips match their corresponding script segments.

        Args:
            clips: List of video clips to verify
            script_segments: List of script segments (one per clip)

        Returns:
            Updated clips with verification results
        """
        logger.info(f"Verifying {len(clips)} clips against script segments")

        if len(clips) != len(script_segments):
            logger.warning(
                f"Mismatch: {len(clips)} clips but {len(script_segments)} script segments. "
                "Will verify as many as possible."
            )

        verified_clips = []

        for i, clip in enumerate(clips):
            # Skip clips that aren't completed
            if clip.status != "completed" or not clip.video_url:
                logger.info(f"Skipping clip {clip.clip_number} (status: {clip.status})")
                verified_clips.append(clip)
                continue

            # Get corresponding script segment
            script_segment = script_segments[i] if i < len(script_segments) else "Unknown"

            # Verify the clip
            verification = await self.verify_clip(clip, script_segment)

            # Update clip with verification results
            clip.script_segment = script_segment
            clip.verification = verification

            verified_clips.append(clip)

        # Log summary
        total_verified = sum(1 for c in verified_clips if c.verification and c.verification.verified)
        avg_confidence = sum(
            c.verification.confidence_score for c in verified_clips if c.verification
        ) / len(verified_clips) if verified_clips else 0.0

        logger.info(
            f"Verification complete: {total_verified}/{len(verified_clips)} clips verified "
            f"(avg confidence: {avg_confidence:.2f})"
        )

        return verified_clips

    def get_failed_clips(self, clips: List[VideoClip]) -> List[VideoClip]:
        """
        Get clips that failed verification.

        Args:
            clips: List of verified clips

        Returns:
            List of clips that didn't pass verification
        """
        failed = [
            clip for clip in clips
            if clip.verification and not clip.verification.verified
        ]

        logger.info(f"Found {len(failed)} failed clips")
        return failed

    def get_verification_summary(self, clips: List[VideoClip]) -> dict:
        """
        Get summary statistics of verification results.

        Args:
            clips: List of verified clips

        Returns:
            Dict with verification statistics
        """
        verified_clips = [c for c in clips if c.verification]

        if not verified_clips:
            return {
                "total_clips": len(clips),
                "verified": 0,
                "failed": 0,
                "avg_confidence": 0.0,
                "min_confidence": 0.0,
                "max_confidence": 0.0,
            }

        verified_count = sum(1 for c in verified_clips if c.verification.verified)
        failed_count = len(verified_clips) - verified_count

        confidence_scores = [c.verification.confidence_score for c in verified_clips]
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        min_confidence = min(confidence_scores)
        max_confidence = max(confidence_scores)

        return {
            "total_clips": len(clips),
            "verified": verified_count,
            "failed": failed_count,
            "avg_confidence": avg_confidence,
            "min_confidence": min_confidence,
            "max_confidence": max_confidence,
        }
