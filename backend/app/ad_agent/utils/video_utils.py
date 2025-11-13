"""Video processing utilities using ffmpeg."""
import os
import logging
import tempfile
import subprocess
from typing import List, Optional
import httpx
import re
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Handles video merging and editing using ffmpeg."""

    # GCS Fuse mount point (Option 1)
    GCS_MOUNT_POINT = "/mnt/gcs"

    @staticmethod
    def extract_gcs_path_from_signed_url(signed_url: str) -> Optional[str]:
        """
        Extract GCS path from a signed URL.

        Args:
            signed_url: GCS signed URL (e.g., https://storage.googleapis.com/bucket/path?...)

        Returns:
            GCS path without bucket (e.g., "user123/job456/clip_0.mp4")
            or None if not a valid GCS URL

        Example:
            Input: "https://storage.googleapis.com/ai-ad-agent-assets/user123/job456/clip_0.mp4?X-Goog-..."
            Output: "user123/job456/clip_0.mp4"
        """
        try:
            # Parse URL
            parsed = urlparse(signed_url)

            # Check if it's a GCS URL
            if "storage.googleapis.com" not in parsed.netloc:
                return None

            # Extract path (remove leading slash and bucket name)
            # Path format: /bucket-name/path/to/file.mp4
            path_parts = parsed.path.strip("/").split("/", 1)
            if len(path_parts) < 2:
                return None

            # Return path without bucket name
            gcs_path = path_parts[1]
            logger.debug(f"Extracted GCS path: {gcs_path}")
            return gcs_path

        except Exception as e:
            logger.error(f"Failed to extract GCS path from URL: {e}")
            return None

    @staticmethod
    def is_gcsfuse_available() -> bool:
        """Check if gcsfuse is installed and available."""
        try:
            result = subprocess.run(
                ["gcsfuse", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"gcsfuse available: {result.stdout.strip()}")
                return True
            return False
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            logger.warning(f"gcsfuse not available: {e}")
            return False

    @staticmethod
    def is_gcs_mounted() -> bool:
        """Check if GCS bucket is mounted via gcsfuse."""
        return os.path.ismount(VideoProcessor.GCS_MOUNT_POINT) or os.path.exists(VideoProcessor.GCS_MOUNT_POINT)

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
            if result.returncode == 0:
                logger.debug(f"ffmpeg check passed: {result.stdout[:100]}")
                return True
            else:
                logger.error(f"ffmpeg check failed with return code {result.returncode}: {result.stderr}")
                return False
        except FileNotFoundError as e:
            logger.error(f"ffmpeg not found in PATH: {e}")
            return False
        except subprocess.SubprocessError as e:
            logger.error(f"ffmpeg subprocess error: {e}")
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
        use_streaming: bool = True,
    ) -> str:
        """
        Merge multiple videos into one.

        Args:
            video_urls: List of video URLs to merge (GCS signed URLs or local paths)
            output_path: Path for output video
            include_audio: Whether to include audio
            use_streaming: If True, stream from URLs directly (no download). If False, download first.

        Returns:
            Path to merged video

        Note:
            ffmpeg availability is checked once at application startup.
            Streaming mode (use_streaming=True) eliminates downloads and saves memory/time.
        """

        if not video_urls:
            raise ValueError("No videos to merge")

        temp_dir = tempfile.mkdtemp()
        concat_file = os.path.join(temp_dir, "concat.txt")

        try:
            if use_streaming:
                # OPTION 2: Stream from URLs directly (NO DOWNLOAD)
                logger.info(f"Merging {len(video_urls)} videos via HTTP streaming (no local download)")

                # Create concat file with URLs directly
                with open(concat_file, "w") as f:
                    for url in video_urls:
                        # FFmpeg concat requires proper escaping of URLs
                        f.write(f"file '{url}'\n")

                # Merge using ffmpeg with HTTP protocol enabled
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-protocol_whitelist", "file,https,tls,tcp,http",  # Allow HTTPS streaming
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy" if include_audio else "-c:v copy -an",
                    "-y",  # Overwrite output
                    output_path,
                ]

                logger.info("FFmpeg merging videos via streaming (no downloads)...")

            else:
                # LEGACY: Download all videos to temp directory (OLD METHOD)
                logger.warning("Using legacy download mode - consider switching to streaming mode")
                temp_files = []

                # Download videos
                for i, url in enumerate(video_urls):
                    temp_file = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
                    logger.info(f"Downloading clip {i+1}/{len(video_urls)} from GCS...")
                    await VideoProcessor.download_video(url, temp_file)
                    temp_files.append(temp_file)

                # Create concat file for ffmpeg
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

            # Run FFmpeg
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise RuntimeError(f"Video merge failed: {result.stderr}")

            logger.info(f"✅ Merged {len(video_urls)} videos to {output_path} (streaming mode: {use_streaming})")
            return output_path

        finally:
            # Cleanup temp files (only concat file in streaming mode)
            if not use_streaming:
                for temp_file in temp_files:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
            if os.path.exists(concat_file):
                os.remove(concat_file)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)

    @staticmethod
    async def merge_videos_with_gcsfuse(
        video_urls: List[str],
        output_path: str,
        include_audio: bool = True,
    ) -> str:
        """
        Merge videos using GCS Fuse (Option 1).

        This method reads videos directly from GCS via gcsfuse mount,
        eliminating downloads entirely.

        Args:
            video_urls: List of GCS signed URLs
            output_path: Path for output video
            include_audio: Whether to include audio

        Returns:
            Path to merged video

        Raises:
            RuntimeError: If gcsfuse is not available or mounted

        Note:
            Requires gcsfuse to be installed and GCS bucket mounted at /mnt/gcs
        """
        if not VideoProcessor.is_gcsfuse_available():
            raise RuntimeError("gcsfuse is not installed - cannot use GCS Fuse merge")

        if not VideoProcessor.is_gcs_mounted():
            raise RuntimeError(f"GCS bucket not mounted at {VideoProcessor.GCS_MOUNT_POINT}")

        logger.info(f"Merging {len(video_urls)} videos via GCS Fuse (ZERO downloads)")

        temp_dir = tempfile.mkdtemp()
        concat_file = os.path.join(temp_dir, "concat.txt")

        try:
            # Create concat file with GCS Fuse paths
            with open(concat_file, "w") as f:
                for url in video_urls:
                    # Extract GCS path from signed URL
                    gcs_path = VideoProcessor.extract_gcs_path_from_signed_url(url)
                    if not gcs_path:
                        raise ValueError(f"Invalid GCS URL: {url}")

                    # Create full path to mounted GCS file
                    mounted_path = os.path.join(VideoProcessor.GCS_MOUNT_POINT, gcs_path)
                    f.write(f"file '{mounted_path}'\n")

            # Merge using ffmpeg (reads directly from GCS via fuse)
            ffmpeg_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy" if include_audio else "-c:v copy -an",
                "-y",  # Overwrite output
                output_path,
            ]

            logger.info("FFmpeg reading videos from GCS Fuse mount (zero downloads)...")

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise RuntimeError(f"Video merge failed: {result.stderr}")

            logger.info(f"✅ Merged {len(video_urls)} videos via GCS Fuse (ZERO downloads)")
            return output_path

        finally:
            # Cleanup concat file
            if os.path.exists(concat_file):
                os.remove(concat_file)
            if os.path.exists(temp_dir):
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

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """
        Get audio file duration using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                duration = float(data.get("format", {}).get("duration", 0))
                logger.info(f"Audio duration: {duration:.2f}s")
                return duration

        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")

        return 0.0

    @staticmethod
    def add_text_overlay(
        video_path: str,
        text: str,
        output_path: str,
        position: str = "center",
        font_size: int = 48,
        font_color: str = "white",
        box_color: str = "black@0.5",
        start_time: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> str:
        """
        Add text overlay to video using ffmpeg drawtext filter.

        Args:
            video_path: Input video path
            text: Text to overlay
            output_path: Output video path
            position: Position (center, top, bottom, top-left, etc.)
            font_size: Font size in pixels
            font_color: Font color
            box_color: Background box color (supports transparency)
            start_time: When to start showing text (seconds)
            duration: How long to show text (seconds)

        Returns:
            Path to output video
        """

        # Position mapping
        positions = {
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "top": "x=(w-text_w)/2:y=50",
            "bottom": "x=(w-text_w)/2:y=h-th-50",
            "top-left": "x=50:y=50",
            "top-right": "x=w-text_w-50:y=50",
            "bottom-left": "x=50:y=h-th-50",
            "bottom-right": "x=w-text_w-50:y=h-th-50",
        }

        pos_coords = positions.get(position, positions["center"])

        # Build drawtext filter
        drawtext_filter = (
            f"drawtext=text='{text}':"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"box=1:boxcolor={box_color}:"
            f"boxborderw=10:"
            f"{pos_coords}"
        )

        # Add timing if specified
        if start_time is not None and duration is not None:
            end_time = start_time + duration
            drawtext_filter += f":enable='between(t,{start_time},{end_time})'"
        elif start_time is not None:
            drawtext_filter += f":enable='gte(t,{start_time})'"

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", drawtext_filter,
            "-c:a", "copy",
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
            raise RuntimeError(f"Text overlay failed: {result.stderr}")

        logger.info(f"Added text overlay: {output_path}")
        return output_path

    @staticmethod
    def add_multiple_text_overlays(
        video_path: str,
        text_overlays: List[dict],
        output_path: str,
    ) -> str:
        """
        Add multiple text overlays to video.

        Args:
            video_path: Input video path
            text_overlays: List of overlay configs with text, position, timing, etc.
            output_path: Output video path

        Returns:
            Path to output video
        """
        if not text_overlays:
            return video_path


        # Build complex filter with multiple drawtext filters
        filters = []
        for i, overlay in enumerate(text_overlays):
            text = overlay.get("text", "")
            position = overlay.get("position", "center")
            font_size = overlay.get("font_size", 48)
            font_color = overlay.get("font_color", "white")
            box_color = overlay.get("box_color", "black@0.5")
            start_time = overlay.get("start_time")
            duration = overlay.get("duration")

            positions = {
                "center": "x=(w-text_w)/2:y=(h-text_h)/2",
                "top": "x=(w-text_w)/2:y=50",
                "bottom": "x=(w-text_w)/2:y=h-th-50",
            }
            pos_coords = positions.get(position, positions["center"])

            drawtext = (
                f"drawtext=text='{text}':"
                f"fontsize={font_size}:"
                f"fontcolor={font_color}:"
                f"box=1:boxcolor={box_color}:"
                f"boxborderw=10:"
                f"{pos_coords}"
            )

            if start_time is not None and duration is not None:
                end_time = start_time + duration
                drawtext += f":enable='between(t,{start_time},{end_time})'"

            filters.append(drawtext)

        # Chain all filters
        filter_complex = ",".join(filters)

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:a", "copy",
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
            raise RuntimeError(f"Multiple text overlays failed: {result.stderr}")

        logger.info(f"Added {len(text_overlays)} text overlays: {output_path}")
        return output_path

    @staticmethod
    def apply_video_effects(
        video_path: str,
        effects: List[str],
        output_path: str,
    ) -> str:
        """
        Apply visual effects to video.

        Args:
            video_path: Input video path
            effects: List of effect names (fade_in, fade_out, zoom, blur, etc.)
            output_path: Output video path

        Returns:
            Path to output video
        """
        if not effects:
            return video_path


        # Get video info for effect calculations
        info = VideoProcessor.get_video_info(video_path)
        duration = info.get("duration", 10)

        # Build filter chain
        filters = []

        for effect in effects:
            if effect == "fade_in":
                filters.append("fade=t=in:st=0:d=1")
            elif effect == "fade_out":
                filters.append(f"fade=t=out:st={duration-1}:d=1")
            elif effect == "zoom_in":
                filters.append("zoompan=z='min(zoom+0.0015,1.5)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'")
            elif effect == "blur":
                filters.append("boxblur=2:1")
            elif effect == "sharpen":
                filters.append("unsharp=5:5:1.0:5:5:0.0")
            elif effect == "brightness":
                filters.append("eq=brightness=0.1")
            elif effect == "contrast":
                filters.append("eq=contrast=1.2")

        if not filters:
            logger.warning("No valid effects to apply")
            return video_path

        filter_complex = ",".join(filters)

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:a", "copy",
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
            raise RuntimeError(f"Video effects failed: {result.stderr}")

        logger.info(f"Applied {len(effects)} effects: {output_path}")
        return output_path

    @staticmethod
    def add_logo_overlay(
        video_path: str,
        logo_path: str,
        output_path: str,
        position: str = "bottom-right",
        size: int = 150,
        opacity: float = 0.8,
        margin: int = 20,
        start_time: Optional[float] = None,
        duration: Optional[float] = None,
    ) -> str:
        """
        Add logo overlay to video.

        Args:
            video_path: Input video path
            logo_path: Path to logo image (PNG with transparency recommended)
            output_path: Output video path
            position: Logo position (top-left, top-right, bottom-left, bottom-right, center)
            size: Logo width in pixels (height auto-scaled)
            opacity: Logo opacity 0.0-1.0 (1.0 = fully opaque)
            margin: Margin from edges in pixels
            start_time: When to start showing logo (seconds, None = from beginning)
            duration: How long to show logo (seconds, None = until end)

        Returns:
            Path to output video
        """

        # Position mapping for overlay filter
        positions = {
            "top-left": f"{margin}:{margin}",
            "top-right": f"main_w-overlay_w-{margin}:{margin}",
            "bottom-left": f"{margin}:main_h-overlay_h-{margin}",
            "bottom-right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
            "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
        }

        pos_coords = positions.get(position, positions["bottom-right"])

        # Build overlay filter
        # Scale logo, add transparency, then overlay on video
        filter_complex = (
            f"[1:v]scale={size}:-1[logo];"  # Scale logo to specified width
            f"[logo]format=rgba,colorchannelmixer=aa={opacity}[logo_transparent];"  # Apply opacity
            f"[0:v][logo_transparent]overlay={pos_coords}"  # Overlay at position
        )

        # Add timing if specified
        if start_time is not None or duration is not None:
            timing = ":enable='"
            if start_time is not None and duration is not None:
                end_time = start_time + duration
                timing += f"between(t,{start_time},{end_time})"
            elif start_time is not None:
                timing += f"gte(t,{start_time})"
            elif duration is not None:
                timing += f"lte(t,{duration})"
            timing += "'"
            filter_complex += timing

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", logo_path,
            "-filter_complex", filter_complex,
            "-c:a", "copy",  # Copy audio unchanged
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
            raise RuntimeError(f"Logo overlay failed: {result.stderr}")

        logger.info(f"Added logo overlay ({position}): {output_path}")
        return output_path

    @staticmethod
    def save_base64_image(base64_data: str, output_path: str) -> str:
        """
        Save base64 encoded image to file.

        Args:
            base64_data: Base64 encoded image string
            output_path: Path to save image

        Returns:
            Path to saved image
        """
        import base64

        # Remove data URL prefix if present
        if "," in base64_data:
            base64_data = base64_data.split(",")[1]

        # Decode and save
        image_data = base64.b64decode(base64_data)
        with open(output_path, "wb") as f:
            f.write(image_data)

        logger.info(f"Saved base64 image to {output_path}")
        return output_path

    @staticmethod
    def extract_last_frame(video_path: str, output_path: str, max_retries: int = 3) -> str:
        """
        Extract the last frame from a video as an image using cv2 (OpenCV).

        Args:
            video_path: Path to input video
            output_path: Path to save output image (e.g., frame.jpg)
            max_retries: Maximum number of retry attempts (not used with cv2, kept for compatibility)

        Returns:
            Path to extracted frame image

        Raises:
            RuntimeError: If extraction fails

        Note:
            Uses cv2.VideoCapture instead of FFmpeg - much faster and more reliable.
        """
        import cv2

        logger.info(f"Extracting last frame using cv2 from {video_path}")

        try:
            # Open video file
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"Could not open video: {video_path}")

            # Get total number of frames
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                cap.release()
                raise RuntimeError(f"Video has no frames: {video_path}")

            # Seek to last frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)

            # Read last frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                raise RuntimeError(f"Failed to read last frame from {video_path}")

            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save frame as JPEG
            success = cv2.imwrite(output_path, frame)
            if not success:
                raise RuntimeError(f"Failed to write frame to {output_path}")

            logger.info(f"✅ Extracted last frame to {output_path} (cv2)")
            return output_path

        except Exception as e:
            logger.error(f"cv2 frame extraction failed: {e}")
            raise RuntimeError(f"Failed to extract frame with cv2: {str(e)}")

    @staticmethod
    def extract_frame_to_base64(video_path: str) -> str:
        """
        Extract the last frame from a video and return as base64 string using cv2.

        Args:
            video_path: Path to input video

        Returns:
            Base64 encoded JPEG image string

        Raises:
            RuntimeError: If extraction fails
        """
        import cv2
        import base64

        logger.info(f"Extracting last frame to base64 using cv2")

        try:
            # Open video file
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"Could not open video: {video_path}")

            # Get total number of frames
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                cap.release()
                raise RuntimeError(f"Video has no frames: {video_path}")

            # Seek to last frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)

            # Read last frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                raise RuntimeError(f"Failed to read last frame from {video_path}")

            # Encode frame to JPEG in memory
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ret:
                raise RuntimeError(f"Failed to encode frame to JPEG")

            # Convert to base64
            b64_data = base64.b64encode(buffer).decode("utf-8")

            logger.info(f"✅ Extracted last frame as base64 ({len(b64_data)} chars) using cv2")
            return b64_data

        except Exception as e:
            logger.error(f"cv2 frame extraction to base64 failed: {e}")
            raise RuntimeError(f"Failed to extract frame with cv2: {str(e)}")
