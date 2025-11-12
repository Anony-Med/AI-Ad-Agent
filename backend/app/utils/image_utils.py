"""
Image utilities for processing avatar and character images.

Includes base64 encoding/decoding and resizing for Veo API compatibility.
"""

import base64
import io
import logging
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)


def resize_image_for_veo(
    image_b64: str,
    max_size: int = 768,
    quality: int = 85,
) -> str:
    """
    Resize and optimize an image for Veo API.

    Veo API has payload size limits. This function:
    1. Decodes the base64 image
    2. Resizes to max_size while maintaining aspect ratio
    3. Converts to JPEG (smaller than PNG)
    4. Re-encodes to base64

    Args:
        image_b64: Base64 encoded image string
        max_size: Maximum dimension (width or height) in pixels
        quality: JPEG quality (1-100)

    Returns:
        Resized and optimized base64 encoded image string

    Raises:
        ValueError: If image cannot be decoded or processed
    """
    try:
        # Strip data URI prefix if present (e.g., "data:image/jpeg;base64,")
        if ',' in image_b64 and image_b64.startswith('data:'):
            image_b64 = image_b64.split(',', 1)[1]
            logger.info("Stripped data URI prefix")

        logger.info(f"Base64 string length: {len(image_b64)} chars (first 50: {image_b64[:50]}...)")

        # Decode base64
        image_bytes = base64.b64decode(image_b64)
        logger.info(f"Decoded image size: {len(image_bytes)} bytes (first 20 bytes: {image_bytes[:20].hex()})")

        # Open image
        buffer = io.BytesIO(image_bytes)
        img = Image.open(buffer)
        original_size = img.size
        logger.info(f"Successfully opened image with dimensions: {original_size}")

        # Calculate new size maintaining aspect ratio
        width, height = img.size
        if width <= max_size and height <= max_size:
            # Already small enough
            logger.debug("Image already within size limits")
            new_width, new_height = width, height
        else:
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))

        # Resize if needed
        if (new_width, new_height) != (width, height):
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image from {original_size} to {img.size}")

        # Convert to JPEG (smaller than PNG)
        buffer = io.BytesIO()
        img.convert('RGB').save(buffer, format='JPEG', quality=quality)
        optimized_bytes = buffer.getvalue()

        logger.info(f"Optimized image: {len(optimized_bytes)} bytes ({len(optimized_bytes) / 1024:.1f} KB)")

        # Re-encode to base64
        optimized_b64 = base64.b64encode(optimized_bytes).decode('utf-8')
        logger.debug(f"Base64 length: {len(optimized_b64)} chars")

        return optimized_b64

    except Exception as e:
        logger.error(f"Failed to resize image: {e}")
        raise ValueError(f"Image processing failed: {e}")


def decode_base64_image(image_b64: str) -> bytes:
    """
    Decode a base64 image to bytes.

    Args:
        image_b64: Base64 encoded image string

    Returns:
        Image bytes

    Raises:
        ValueError: If decoding fails
    """
    try:
        return base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 image: {e}")


def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string.

    Args:
        image_bytes: Image bytes

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(image_bytes).decode('utf-8')


def get_image_info(image_b64: str) -> dict:
    """
    Get information about a base64 encoded image.

    Args:
        image_b64: Base64 encoded image string

    Returns:
        Dictionary with image info:
        - width: Image width in pixels
        - height: Image height in pixels
        - format: Image format (JPEG, PNG, etc.)
        - mode: Color mode (RGB, RGBA, etc.)
        - size_bytes: Size in bytes
        - size_kb: Size in kilobytes
    """
    try:
        # Strip data URI prefix if present
        if ',' in image_b64 and image_b64.startswith('data:'):
            image_b64 = image_b64.split(',', 1)[1]

        image_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(image_bytes))

        return {
            "width": img.width,
            "height": img.height,
            "format": img.format,
            "mode": img.mode,
            "size_bytes": len(image_bytes),
            "size_kb": len(image_bytes) / 1024,
        }
    except Exception as e:
        logger.error(f"Failed to get image info: {e}")
        return {}
