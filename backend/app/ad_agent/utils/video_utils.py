"""Video processing utilities using ffmpeg."""
import os
import logging
import tempfile
import subprocess
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles video merging and editing using ffmpeg."""

    @staticmethod
    def check_ffmpeg() -> bool:
        """Check if ffmpeg is installed."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @staticmethod
    async def download_video(url: str, output_path: str) -> str:
        """
        Download video from URL.

        Args:
            url: Video URL
            output_path: Path to save video

        Returns:
            Path to downloaded video
        """
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded video to {output_path}")
            return output_path

    @staticmethod
    async def merge_videos(
        video_urls: List[str],
        output_path: str,
        include_audio: bool = True,
    ) -> str:
        """
        Merge multiple videos into one.

        Args:
            video_urls: List of video URLs to merge
            output_path: Path for output video
            include_audio: Whether to include audio

        Returns:
            Path to merged video
        """
        if not VideoProcessor.check_ffmpeg():
            raise RuntimeError("ffmpeg not installed. Install with: apt-get install ffmpeg")

        if not video_urls:
            raise ValueError("No videos to merge")

        # Download all videos to temp directory
        temp_dir = tempfile.mkdtemp()
        temp_files = []

        try:
            # Download videos
            for i, url in enumerate(video_urls):
                temp_file = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
                await VideoProcessor.download_video(url, temp_file)
                temp_files.append(temp_file)

            # Create concat file for ffmpeg
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for temp_file in temp_files:
                    f.write(f"file '{temp_file}'\n")

            # Merge using ffmpeg
            ffmpeg_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy" if include_audio else "-c:v copy -an",
                "-y",  # Overwrite output
                output_path,
            ]

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise RuntimeError(f"Video merge failed: {result.stderr}")

            logger.info(f"Merged {len(video_urls)} videos to {output_path}")
            return output_path

        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            if os.path.exists(concat_file):
                os.remove(concat_file)
            os.rmdir(temp_dir)

    @staticmethod
    def add_audio_to_video(
        video_path: str,
        audio_path: str,
        output_path: str,
        audio_volume: float = 1.0,
    ) -> str:
        """
        Add or replace audio in a video.

        Args:
            video_path: Input video path
            audio_path: Audio file path
            output_path: Output video path
            audio_volume: Audio volume (0.0-1.0)

        Returns:
            Path to output video
        """
        if not VideoProcessor.check_ffmpeg():
            raise RuntimeError("ffmpeg not installed")

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",  # Video from first input
            "-map", "1:a:0",  # Audio from second input
            "-filter:a", f"volume={audio_volume}",
            "-shortest",  # Match shortest stream duration
            "-y",
            output_path,
        ]

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            raise RuntimeError(f"Audio addition failed: {result.stderr}")

        logger.info(f"Added audio to video: {output_path}")
        return output_path

    @staticmethod
    def mix_audio_tracks(
        video_path: str,
        music_path: str,
        sfx_path: Optional[str],
        output_path: str,
        music_volume: float = 0.3,
        sfx_volume: float = 0.7,
    ) -> str:
        """
        Mix background music and sound effects with video.

        Args:
            video_path: Input video with voice
            music_path: Background music path
            sfx_path: Sound effects path (optional)
            output_path: Output video path
            music_volume: Music volume (0.0-1.0)
            sfx_volume: SFX volume (0.0-1.0)

        Returns:
            Path to output video
        """
        if not VideoProcessor.check_ffmpeg():
            raise RuntimeError("ffmpeg not installed")

        if sfx_path and os.path.exists(sfx_path):
            # Mix all three: video audio, music, and SFX
            filter_complex = (
                f"[0:a]volume=1.0[voice];"
                f"[1:a]volume={music_volume}[music];"
                f"[2:a]volume={sfx_volume}[sfx];"
                f"[voice][music][sfx]amix=inputs=3:duration=first:dropout_transition=2[aout]"
            )

            ffmpeg_cmd = [
                "ffmpeg",
                "-i", video_path,
                "-i", music_path,
                "-i", sfx_path,
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-y",
                output_path,
            ]
        else:
            # Mix just video audio and music
            filter_complex = (
                f"[0:a]volume=1.0[voice];"
                f"[1:a]volume={music_volume}[music];"
                f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )

            ffmpeg_cmd = [
                "ffmpeg",
                "-i", video_path,
                "-i", music_path,
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-y",
                output_path,
            ]

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            raise RuntimeError(f"Audio mixing failed: {result.stderr}")

        logger.info(f"Mixed audio tracks: {output_path}")
        return output_path

    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """
        Get video metadata using ffprobe.

        Args:
            video_path: Path to video file

        Returns:
            Dict with duration, resolution, etc.
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)

                # Extract video stream info
                video_stream = next(
                    (s for s in data.get("streams", []) if s["codec_type"] == "video"),
                    None,
                )

                if video_stream:
                    return {
                        "duration": float(data["format"].get("duration", 0)),
                        "width": video_stream.get("width"),
                        "height": video_stream.get("height"),
                        "codec": video_stream.get("codec_name"),
                        "fps": eval(video_stream.get("r_frame_rate", "0/1")),
                    }

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")

        return {}
