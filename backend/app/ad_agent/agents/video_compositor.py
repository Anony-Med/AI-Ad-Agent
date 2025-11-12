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

    def apply_creative_enhancements(
        self,
        video_path: str,
        creative_suggestions: dict,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Apply creative enhancements from suggestions.

        Args:
            video_path: Path to input video
            creative_suggestions: CreativeSuggestion object with text_overlays and effects
            output_path: Optional output path

        Returns:
            Path to enhanced video
        """
        if not output_path:
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix="_enhanced.mp4",
            ).name

        logger.info("Applying creative enhancements to video")

        current_video = video_path
        temp_files = []

        # Step 1: Apply text overlays if any
        text_overlays = creative_suggestions.get("text_overlays", [])
        if text_overlays:
            logger.info(f"Applying {len(text_overlays)} text overlays")

            # Parse text overlays into structured format
            overlay_configs = []
            video_info = self.video_processor.get_video_info(current_video)
            video_duration = video_info.get("duration", 10)

            for i, text in enumerate(text_overlays[:3]):  # Limit to 3 overlays
                # Simple parsing: show each overlay for 1/3 of video duration
                segment_duration = video_duration / min(len(text_overlays), 3)
                overlay_configs.append({
                    "text": text,
                    "position": "bottom" if i % 2 == 0 else "top",
                    "font_size": 36,
                    "font_color": "white",
                    "box_color": "black@0.5",
                    "start_time": i * segment_duration,
                    "duration": segment_duration,
                })

            temp_with_text = tempfile.NamedTemporaryFile(
                delete=False,
                suffix="_with_text.mp4",
            ).name
            temp_files.append(temp_with_text)

            current_video = self.video_processor.add_multiple_text_overlays(
                video_path=current_video,
                text_overlays=overlay_configs,
                output_path=temp_with_text,
            )

        # Step 2: Apply visual effects if any
        effects = creative_suggestions.get("effects", [])
        if effects:
            logger.info(f"Applying {len(effects)} visual effects")

            # Parse effect suggestions and map to supported effects
            effect_keywords = {
                "fade": ["fade_in", "fade_out"],
                "zoom": ["zoom_in"],
                "blur": ["blur"],
                "sharp": ["sharpen"],
                "bright": ["brightness"],
                "contrast": ["contrast"],
            }

            effects_to_apply = []
            for effect_suggestion in effects[:2]:  # Limit to 2 effects
                effect_lower = effect_suggestion.lower()
                for keyword, effect_list in effect_keywords.items():
                    if keyword in effect_lower:
                        effects_to_apply.extend(effect_list)
                        break

            if effects_to_apply:
                temp_with_effects = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix="_with_effects.mp4",
                ).name
                temp_files.append(temp_with_effects)

                current_video = self.video_processor.apply_video_effects(
                    video_path=current_video,
                    effects=list(set(effects_to_apply)),  # Remove duplicates
                    output_path=temp_with_effects,
                )

        # Copy to final output if different
        if current_video != output_path:
            import shutil
            shutil.copy(current_video, output_path)

        # Cleanup temp files (except the ones we're tracking in video_path chain)
        for temp_file in temp_files:
            if temp_file != output_path and os.path.exists(temp_file):
                try:
                    if temp_file != current_video:  # Don't delete the final result
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to cleanup {temp_file}: {e}")

        logger.info(f"Creative enhancements applied: {output_path}")
        return output_path

    def add_logo_to_video(
        self,
        video_path: str,
        logo_image_base64: str,
        output_path: Optional[str] = None,
        position: str = "bottom-right",
        size: int = 150,
        opacity: float = 0.8,
        timing: str = "always",
    ) -> str:
        """
        Add logo overlay to video.

        Args:
            video_path: Path to input video
            logo_image_base64: Base64 encoded logo image
            output_path: Optional output path
            position: Logo position (top-left, top-right, bottom-left, bottom-right, center)
            size: Logo width in pixels
            opacity: Logo opacity (0.0-1.0)
            timing: When to show logo (always, intro, outro, none)

        Returns:
            Path to video with logo
        """
        if timing == "none":
            logger.info("Logo timing set to 'none', skipping logo overlay")
            return video_path

        if not output_path:
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix="_with_logo.mp4",
            ).name

        logger.info(f"Adding logo overlay ({position}, {timing})")

        # Save base64 logo to temp file
        logo_temp_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".png",
        ).name

        self.video_processor.save_base64_image(logo_image_base64, logo_temp_path)

        # Get video duration for timing calculations
        video_info = self.video_processor.get_video_info(video_path)
        video_duration = video_info.get("duration", 10)

        # Calculate timing
        start_time = None
        duration = None

        if timing == "intro":
            start_time = 0
            duration = min(3, video_duration)  # First 3 seconds or less
        elif timing == "outro":
            start_time = max(0, video_duration - 3)  # Last 3 seconds
            duration = 3
        # "always" = None, None (show throughout)

        # Apply logo overlay
        try:
            result_path = self.video_processor.add_logo_overlay(
                video_path=video_path,
                logo_path=logo_temp_path,
                output_path=output_path,
                position=position,
                size=size,
                opacity=opacity,
                start_time=start_time,
                duration=duration,
            )

            logger.info(f"Logo overlay applied: {result_path}")
            return result_path

        finally:
            # Cleanup temp logo file
            if os.path.exists(logo_temp_path):
                os.remove(logo_temp_path)
