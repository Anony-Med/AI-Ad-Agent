"""Agent for audio composition (voice, music, SFX)."""
import logging
import os
import tempfile
from typing import Optional
from app.ad_agent.clients.elevenlabs_client import ElevenLabsClient

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
