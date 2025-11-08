"""Agent for final video composition and editing."""
import logging
import os
import tempfile
from typing import List, Optional
from app.ad_agent.utils.video_utils import VideoProcessor

logger = logging.getLogger(__name__)


class VideoCompositorAgent:
    """Handles final video assembly and editing."""

    def __init__(self):
        """Initialize video compositor."""
        self.video_processor = VideoProcessor()

    async def merge_video_clips(
        self,
        video_urls: List[str],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Merge all video clips into one.

        Args:
            video_urls: List of video URLs from Veo
            output_path: Optional output path

        Returns:
            Path to merged video
        """
        if not output_path:
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix="_merged.mp4",
            ).name

        logger.info(f"Merging {len(video_urls)} video clips")

        merged_path = await self.video_processor.merge_videos(
            video_urls=video_urls,
            output_path=output_path,
            include_audio=True,
        )

        logger.info(f"Merged video saved to {merged_path}")
        return merged_path

    def add_audio_layers(
        self,
        video_path: str,
        music_path: Optional[str] = None,
        sfx_path: Optional[str] = None,
        output_path: Optional[str] = None,
        music_volume: float = 0.3,
        sfx_volume: float = 0.7,
    ) -> str:
        """
        Add music and sound effects to video.

        Args:
            video_path: Path to video with voice
            music_path: Path to background music
            sfx_path: Path to sound effects
            output_path: Optional output path
            music_volume: Music volume (0.0-1.0)
            sfx_volume: SFX volume (0.0-1.0)

        Returns:
            Path to final video
        """
        if not output_path:
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix="_final.mp4",
            ).name

        logger.info("Adding audio layers to video")

        if music_path and os.path.exists(music_path):
            final_path = self.video_processor.mix_audio_tracks(
                video_path=video_path,
                music_path=music_path,
                sfx_path=sfx_path if sfx_path and os.path.exists(sfx_path) else None,
                output_path=output_path,
                music_volume=music_volume,
                sfx_volume=sfx_volume,
            )
        else:
            # No music, just use original video
            logger.info("No background music provided, using original video")
            final_path = video_path

        logger.info(f"Final video with audio saved to {final_path}")
        return final_path

    def get_video_info(self, video_path: str) -> dict:
        """
        Get video metadata.

        Args:
            video_path: Path to video

        Returns:
            Dict with video info
        """
        return self.video_processor.get_video_info(video_path)
