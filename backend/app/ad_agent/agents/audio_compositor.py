"""Agent for audio composition (voice, music, SFX)."""
import logging
import os
import tempfile
from typing import Optional, List, Dict
from app.ad_agent.clients.elevenlabs_client import ElevenLabsClient
from app.ad_agent.utils.audio_utils import AudioAnalyzer

logger = logging.getLogger(__name__)


class AudioCompositorAgent:
    """Handles all audio generation and composition."""

    def __init__(self, api_key: str = None):
        """Initialize with ElevenLabs client."""
        self.elevenlabs = ElevenLabsClient(api_key=api_key)

    async def generate_voiceover(
        self,
        script: str,
        voice_id: Optional[str] = None,
        voice_name: Optional[str] = "Heather Bryant",
    ) -> str:
        """
        Generate voiceover for the script.

        Args:
            script: The dialogue script
            voice_id: ElevenLabs voice ID (optional)
            voice_name: Voice name to search for

        Returns:
            Path to generated audio file
        """
        logger.info(f"Generating voiceover ({len(script)} characters)")

        # Find voice by name if ID not provided
        if not voice_id and voice_name:
            voice_id = await self.elevenlabs.find_voice_by_name(voice_name)

        if not voice_id:
            logger.warning(f"Voice '{voice_name}' not found, using default")
            voice_id = "21m00Tcm4TlvDq8ikWAM"  # Default voice

        # Generate TTS
        audio_bytes = await self.elevenlabs.text_to_speech(
            text=script,
            voice_id=voice_id,
            stability=0.5,
            similarity_boost=0.75,
            speed=1.0,
        )

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(audio_bytes)
        temp_file.close()

        logger.info(f"Voiceover saved to {temp_file.name}")
        return temp_file.name

    async def generate_background_music(
        self,
        prompt: str = "upbeat inspiring background music, subtle, corporate"
    ) -> str:
        """
        Generate background music.

        Args:
            prompt: Music description

        Returns:
            Path to generated music file
        """
        logger.info(f"Generating background music: {prompt}")

        audio_bytes = await self.elevenlabs.generate_music(prompt)

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(audio_bytes)
        temp_file.close()

        logger.info(f"Background music saved to {temp_file.name}")
        return temp_file.name

    async def generate_sound_effects(
        self,
        prompts: list[str],
        duration: float = 3.0,
    ) -> list[str]:
        """
        Generate sound effects.

        Args:
            prompts: List of SFX descriptions
            duration: Duration per effect

        Returns:
            List of paths to generated SFX files
        """
        logger.info(f"Generating {len(prompts)} sound effects")

        sfx_files = []

        for i, prompt in enumerate(prompts):
            try:
                audio_bytes = await self.elevenlabs.generate_sound_effect(
                    prompt=prompt,
                    duration_seconds=duration,
                    loop=False,
                )

                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_sfx_{i}.mp3")
                temp_file.write(audio_bytes)
                temp_file.close()

                sfx_files.append(temp_file.name)
                logger.info(f"SFX {i+1}/{len(prompts)}: {prompt} -> {temp_file.name}")

            except Exception as e:
                logger.error(f"Failed to generate SFX '{prompt}': {e}")

        logger.info(f"Generated {len(sfx_files)}/{len(prompts)} sound effects")
        return sfx_files

    async def generate_and_segment_voiceover(
        self,
        script_segments: List[str],
        voice_id: Optional[str] = None,
        voice_name: Optional[str] = "Heather Bryant",
    ) -> List[Dict]:
        """
        Generate voiceover and segment it based on script segments.

        This is the NEW audio-first workflow:
        1. Generate complete voiceover for entire script
        2. Segment the audio intelligently based on script segments
        3. Return segment info with durations for video generation

        Args:
            script_segments: List of script text segments
            voice_id: ElevenLabs voice ID (optional)
            voice_name: Voice name to search for

        Returns:
            List of segment dicts with audio_path, duration, script_text, etc.
        """
        logger.info(f"Generating voiceover for {len(script_segments)} script segments")

        # Generate complete voiceover
        full_script = " ".join(script_segments)
        full_voiceover_path = await self.generate_voiceover(
            script=full_script,
            voice_id=voice_id,
            voice_name=voice_name,
        )

        # Segment the audio based on script segments
        logger.info("Segmenting voiceover to match script segments")
        audio_analyzer = AudioAnalyzer()
        segments = audio_analyzer.segment_audio_by_script(
            audio_path=full_voiceover_path,
            script_segments=script_segments,
        )

        durations_list = [f"{s['duration']:.2f}s" for s in segments]
        logger.info(
            f"Generated and segmented voiceover into {len(segments)} parts. "
            f"Durations: {durations_list}"
        )

        # Cleanup full voiceover file (we now have segments)
        if os.path.exists(full_voiceover_path):
            os.remove(full_voiceover_path)

        return segments

    def get_audio_duration(self, audio_path: str) -> float:
        """
        Get audio file duration.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        audio_analyzer = AudioAnalyzer()
        return audio_analyzer.get_audio_duration(audio_path)

    async def extract_audio_from_video(self, video_path: str) -> str:
        """
        Extract audio track from video file or URL.

        Args:
            video_path: Path to video file OR signed URL

        Returns:
            Path to extracted audio file (AAC format in .m4a container)
        """
        import subprocess

        logger.info(f"Extracting audio from video: {video_path[:100]}...")

        # Create temp file for audio (use .m4a for AAC)
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".m4a")
        temp_audio.close()

        try:
            # FFmpeg can handle URLs directly - no need to download!
            # Extract audio using ffmpeg (use AAC instead of MP3)
            cmd = [
                "ffmpeg",
                "-i", video_path,  # FFmpeg streams from URLs automatically
                "-vn",  # No video
                "-acodec", "aac",  # Use AAC instead of libmp3lame
                "-b:a", "192k",  # High quality bitrate
                "-y",  # Overwrite
                temp_audio.name,
            ]

            logger.info(f"Extracting audio via FFmpeg streaming (no download)...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg extraction error: {result.stderr}")
                raise RuntimeError(f"Audio extraction failed: {result.stderr}")

            # Get file size for logging
            audio_size = os.path.getsize(temp_audio.name)
            logger.info(f"Extracted audio: {audio_size} bytes (~{audio_size / 1024 / 1024:.1f} MB)")
            return temp_audio.name

        except Exception as e:
            logger.error(f"Failed to extract audio: {e}")
            if os.path.exists(temp_audio.name):
                os.remove(temp_audio.name)
            raise

    async def replace_audio_track(self, video_path: str, audio_path: str) -> str:
        """
        Replace audio track in video with new audio.

        Args:
            video_path: Path to video file OR signed URL
            audio_path: Path to new audio file

        Returns:
            Path to video with replaced audio
        """
        import subprocess

        logger.info(f"Replacing audio track in video: {video_path[:100]}...")

        # Create temp file for output video
        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_video.close()

        try:
            # FFmpeg can stream from URLs - no need to download!
            # Replace audio using ffmpeg
            cmd = [
                "ffmpeg",
                "-i", video_path,  # Input video (URL or file path)
                "-i", audio_path,  # Input audio
                "-c:v", "copy",  # Copy video stream (no re-encoding)
                "-c:a", "aac",  # Encode audio as AAC
                "-map", "0:v:0",  # Use video from first input
                "-map", "1:a:0",  # Use audio from second input
                "-shortest",  # Match shortest duration
                "-y",  # Overwrite
                temp_video.name,
            ]

            logger.info(f"Replacing audio via FFmpeg streaming (no download)...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg replacement error: {result.stderr}")
                raise RuntimeError(f"Audio replacement failed: {result.stderr}")

            output_size = os.path.getsize(temp_video.name)
            logger.info(f"Audio replaced, output: {temp_video.name} ({output_size / 1024 / 1024:.1f} MB)")
            return temp_video.name

        except Exception as e:
            logger.error(f"Failed to replace audio: {e}")
            if os.path.exists(temp_video.name):
                os.remove(temp_video.name)
            raise

    @staticmethod
    def cleanup_temp_files(*file_paths):
        """Clean up temporary audio files."""
        for file_path in file_paths:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {file_path}: {e}")
