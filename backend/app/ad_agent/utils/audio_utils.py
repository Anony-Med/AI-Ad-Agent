"""Audio analysis and segmentation utilities."""
import logging
import os
import subprocess
import tempfile
from typing import List, Dict, Tuple
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """Analyzes and segments audio for video synchronization."""

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """
        Get audio file duration.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            duration = len(audio) / 1000.0  # Convert ms to seconds
            logger.info(f"Audio duration: {duration:.2f}s")
            return duration
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 0.0

    @staticmethod
    def segment_audio_by_script(
        audio_path: str,
        script_segments: List[str],
        output_dir: str = None,
    ) -> List[Dict[str, any]]:
        """
        Segment audio file based on script segments using intelligent analysis.

        Strategy:
        1. Calculate expected duration per segment based on character count
        2. Use silence detection to find natural breaks
        3. Align segments with detected breaks
        4. Export each segment as a separate file

        Args:
            audio_path: Path to full voiceover audio
            script_segments: List of script text segments
            output_dir: Directory to save segment files

        Returns:
            List of dicts with segment info (path, duration, text, start_time, end_time)
        """
        logger.info(f"Segmenting audio into {len(script_segments)} parts")

        if not output_dir:
            output_dir = tempfile.mkdtemp()

        try:
            # Load audio
            audio = AudioSegment.from_file(audio_path)
            total_duration_ms = len(audio)
            total_duration_s = total_duration_ms / 1000.0

            logger.info(f"Total audio duration: {total_duration_s:.2f}s")

            # Calculate expected duration per segment based on character count
            total_chars = sum(len(seg.strip()) for seg in script_segments)
            segment_weights = [len(seg.strip()) / total_chars for seg in script_segments]

            # Detect silence (natural breaks) - helps find good split points
            # silence_thresh: dBFS below average to be considered silence
            # min_silence_len: minimum length of silence to be considered a break
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=300,  # 300ms minimum silence
                silence_thresh=-40,  # -40 dBFS
            )

            logger.info(f"Detected {len(nonsilent_ranges)} non-silent ranges")

            # Create segments
            segments = []
            current_pos_ms = 0

            for i, (script_text, weight) in enumerate(zip(script_segments, segment_weights)):
                # Calculate expected duration for this segment
                expected_duration_ms = int(weight * total_duration_ms)

                # For the last segment, take everything remaining
                if i == len(script_segments) - 1:
                    end_pos_ms = total_duration_ms
                else:
                    # Find the closest silence break near expected position
                    expected_end_ms = current_pos_ms + expected_duration_ms
                    end_pos_ms = AudioAnalyzer._find_nearest_break(
                        expected_end_ms,
                        nonsilent_ranges,
                        total_duration_ms,
                    )

                # Extract segment
                segment_audio = audio[current_pos_ms:end_pos_ms]
                segment_duration_ms = len(segment_audio)
                segment_duration_s = segment_duration_ms / 1000.0

                # Save segment
                segment_path = os.path.join(output_dir, f"segment_{i:03d}.mp3")
                segment_audio.export(segment_path, format="mp3")

                segments.append({
                    "segment_number": i,
                    "script_text": script_text,
                    "audio_path": segment_path,
                    "duration": segment_duration_s,
                    "start_time": current_pos_ms / 1000.0,
                    "end_time": end_pos_ms / 1000.0,
                })

                logger.info(
                    f"Segment {i}: {segment_duration_s:.2f}s "
                    f"({current_pos_ms/1000:.2f}s - {end_pos_ms/1000:.2f}s) "
                    f'- "{script_text[:50]}..."'
                )

                current_pos_ms = end_pos_ms

            return segments

        except Exception as e:
            logger.error(f"Audio segmentation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to segment audio: {e}")

    @staticmethod
    def _find_nearest_break(
        target_ms: int,
        nonsilent_ranges: List[Tuple[int, int]],
        max_duration_ms: int,
        tolerance_ms: int = 2000,
    ) -> int:
        """
        Find the nearest silence break to the target position.

        Args:
            target_ms: Target position in milliseconds
            nonsilent_ranges: List of (start, end) tuples for non-silent ranges
            max_duration_ms: Maximum audio duration
            tolerance_ms: How far to search for breaks (default 2 seconds)

        Returns:
            Position in milliseconds for the split
        """
        # Look for gaps (silence) between non-silent ranges
        silence_breaks = []

        for i in range(len(nonsilent_ranges) - 1):
            end_of_current = nonsilent_ranges[i][1]
            start_of_next = nonsilent_ranges[i + 1][0]

            # If there's a gap, that's a silence break
            if start_of_next > end_of_current:
                # Use the midpoint of the silence
                break_point = (end_of_current + start_of_next) // 2
                silence_breaks.append(break_point)

        # Find the closest break to target within tolerance
        closest_break = None
        min_distance = float('inf')

        for break_point in silence_breaks:
            distance = abs(break_point - target_ms)
            if distance < min_distance and distance <= tolerance_ms:
                min_distance = distance
                closest_break = break_point

        # If no good break found, use target position
        if closest_break is None:
            logger.debug(f"No silence break found near {target_ms}ms, using target position")
            closest_break = min(target_ms, max_duration_ms)

        return closest_break

    @staticmethod
    def merge_audio_segments(
        segment_paths: List[str],
        output_path: str,
    ) -> str:
        """
        Merge multiple audio segments into one file.

        Args:
            segment_paths: List of audio file paths
            output_path: Output file path

        Returns:
            Path to merged audio
        """
        logger.info(f"Merging {len(segment_paths)} audio segments")

        try:
            combined = AudioSegment.empty()

            for segment_path in segment_paths:
                segment = AudioSegment.from_file(segment_path)
                combined += segment

            combined.export(output_path, format="mp3")

            logger.info(f"Merged audio saved to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Audio merge failed: {e}")
            raise RuntimeError(f"Failed to merge audio: {e}")

    @staticmethod
    def adjust_audio_speed(
        audio_path: str,
        target_duration: float,
        output_path: str,
    ) -> str:
        """
        Adjust audio speed to match target duration.

        Args:
            audio_path: Input audio path
            target_duration: Desired duration in seconds
            output_path: Output audio path

        Returns:
            Path to adjusted audio
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            current_duration = len(audio) / 1000.0

            speed_factor = current_duration / target_duration

            # Limit speed adjustment to 0.8x - 1.3x for naturalness
            if speed_factor < 0.8:
                logger.warning(
                    f"Speed adjustment {speed_factor:.2f}x is too slow, capping at 0.8x"
                )
                speed_factor = 0.8
            elif speed_factor > 1.3:
                logger.warning(
                    f"Speed adjustment {speed_factor:.2f}x is too fast, capping at 1.3x"
                )
                speed_factor = 1.3

            logger.info(
                f"Adjusting audio speed: {current_duration:.2f}s -> {target_duration:.2f}s "
                f"(factor: {speed_factor:.2f}x)"
            )

            # Use ffmpeg for better quality speed adjustment
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-filter:a", f"atempo={speed_factor}",
                "-y",
                output_path,
            ]

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise RuntimeError(f"Speed adjustment failed: {result.stderr}")

            logger.info(f"Adjusted audio saved to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Audio speed adjustment failed: {e}")
            raise RuntimeError(f"Failed to adjust audio speed: {e}")
