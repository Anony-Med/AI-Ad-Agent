"""Direct ElevenLabs API client for audio generation."""
import os
import logging
from typing import Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ElevenLabsClient:
    """Client for ElevenLabs audio generation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize ElevenLabs client.

        Args:
            api_key: ElevenLabs API key. If not provided, reads from environment.
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable required")

        self.base_url = "https://api.elevenlabs.io"
        self.timeout = 300  # 5 minutes for longer generations

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def text_to_speech(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Default voice (Rachel)
        model_id: str = "eleven_turbo_v2_5",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        speed: float = 1.0,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """
        Generate speech from text.

        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID
            model_id: Model to use
            stability: Voice stability (0-1)
            similarity_boost: Similarity to original voice (0-1)
            speed: Playback speed (0.25-4.0)
            output_format: Audio format

        Returns:
            Audio bytes (MP3)
        """
        url = f"{self.base_url}/v1/text-to-speech/{voice_id}"

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "speed": speed,
                "use_speaker_boost": True,
            },
        }

        params = {"output_format": output_format}
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, params=params, headers=headers)
                response.raise_for_status()

                audio_bytes = response.content
                logger.info(f"Generated TTS audio: {len(audio_bytes)} bytes")
                return audio_bytes

            except httpx.HTTPStatusError as e:
                logger.error(f"ElevenLabs TTS error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"ElevenLabs TTS request failed: {e}")
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_sound_effect(
        self,
        prompt: str,
        duration_seconds: float = 3.0,
        loop: bool = False,
    ) -> bytes:
        """
        Generate sound effects.

        Args:
            prompt: Description of sound effect
            duration_seconds: Duration in seconds
            loop: Whether to loop the sound

        Returns:
            Audio bytes (MP3)
        """
        url = f"{self.base_url}/v1/text-to-sound-effects"

        payload = {
            "text": prompt,
            "duration_seconds": duration_seconds,
            "loop": loop,
        }

        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                audio_bytes = response.content
                logger.info(f"Generated SFX audio: {len(audio_bytes)} bytes")
                return audio_bytes

            except httpx.HTTPStatusError as e:
                logger.error(f"ElevenLabs SFX error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"ElevenLabs SFX request failed: {e}")
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_music(
        self,
        prompt: str,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """
        Generate background music.

        Args:
            prompt: Description of music style
            output_format: Audio format

        Returns:
            Audio bytes (MP3)
        """
        url = f"{self.base_url}/v1/music/stream"

        payload = {"text": prompt}
        params = {"output_format": output_format}
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, params=params, headers=headers)
                response.raise_for_status()

                audio_bytes = response.content
                logger.info(f"Generated music audio: {len(audio_bytes)} bytes")
                return audio_bytes

            except httpx.HTTPStatusError as e:
                logger.error(f"ElevenLabs Music error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"ElevenLabs Music request failed: {e}")
                raise

    async def get_voices(self) -> Dict[str, Any]:
        """
        Get available voices from user's library.

        Returns:
            Dict with voices list
        """
        url = f"{self.base_url}/v2/voices"
        headers = {"xi-api-key": self.api_key}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                voices = response.json()
                logger.info(f"Retrieved {len(voices.get('voices', []))} voices")
                return voices

            except httpx.HTTPStatusError as e:
                logger.error(f"ElevenLabs get voices error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"ElevenLabs get voices failed: {e}")
                raise

    async def find_voice_by_name(self, name: str) -> Optional[str]:
        """
        Find voice ID by name.

        Args:
            name: Voice name to search for

        Returns:
            Voice ID if found, None otherwise
        """
        voices_data = await self.get_voices()
        voices = voices_data.get("voices", [])

        for voice in voices:
            if voice["name"].lower() == name.lower():
                logger.info(f"Found voice '{name}': {voice['voice_id']}")
                return voice["voice_id"]

        logger.warning(f"Voice '{name}' not found")
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def voice_changer(
        self,
        audio_file_path: str,
        voice_id: str,
        model_id: str = "eleven_english_sts_v2",
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """
        Apply voice conversion to an audio file or URL.

        This is the "Speech-to-Speech" feature from ElevenLabs that takes an existing
        audio/video file and applies a different voice to it.

        Args:
            audio_file_path: Path to audio/video file OR signed URL
            voice_id: ElevenLabs voice ID to apply
            model_id: Model to use for speech-to-speech conversion (default: eleven_english_sts_v2)
            output_format: Output audio format

        Returns:
            Converted audio bytes (MP3)
        """
        url = f"{self.base_url}/v1/speech-to-speech/{voice_id}"

        headers = {"xi-api-key": self.api_key}
        params = {"model_id": model_id, "output_format": output_format}

        # Check if input is a URL or file path
        if audio_file_path.startswith("http://") or audio_file_path.startswith("https://"):
            # Download from URL
            logger.info(f"Downloading audio from URL for voice conversion...")
            async with httpx.AsyncClient(timeout=self.timeout) as download_client:
                download_response = await download_client.get(audio_file_path)
                download_response.raise_for_status()
                audio_bytes = download_response.content
                logger.info(f"Downloaded {len(audio_bytes)} bytes from URL")
        else:
            # Read from local file
            with open(audio_file_path, "rb") as f:
                audio_bytes = f.read()

        # Prepare multipart form data
        files = {"audio": ("audio.mp4", audio_bytes, "audio/mp4")}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    files=files,
                )
                response.raise_for_status()

                converted_audio = response.content
                logger.info(f"Voice conversion complete: {len(converted_audio)} bytes")
                return converted_audio

            except httpx.HTTPStatusError as e:
                logger.error(f"ElevenLabs Voice Changer error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"ElevenLabs Voice Changer request failed: {e}")
                raise
