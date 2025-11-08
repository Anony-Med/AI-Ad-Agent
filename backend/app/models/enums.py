"""Enumerations for the application."""
from enum import Enum


class AdType(str, Enum):
    """Type of ad creative."""
    VIDEO = "video"
    IMAGE = "image"


class Platform(str, Enum):
    """Social media platforms."""
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    SNAPCHAT = "snapchat"
    CUSTOM = "custom"


class AspectRatio(str, Enum):
    """Video/Image aspect ratios."""
    RATIO_16_9 = "16:9"      # Landscape - YouTube, Facebook
    RATIO_9_16 = "9:16"      # Portrait - TikTok, Instagram Stories
    RATIO_1_1 = "1:1"        # Square - Instagram Feed
    RATIO_4_5 = "4:5"        # Portrait - Instagram Feed
    RATIO_4_3 = "4:3"        # Standard
    RATIO_21_9 = "21:9"      # Ultrawide


class JobStatus(str, Enum):
    """Status of generation jobs."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelType(str, Enum):
    """AI model types."""
    # Video models
    VEO = "veo"
    SORA = "sora"
    KLING = "kling"
    SEEDANCE = "seedance"

    # Image models
    NANOBANANA = "nanobanana"
    SEEDREAM = "seedream"
    DALL_E = "dall-e"
    MIDJOURNEY = "midjourney"


class CampaignStatus(str, Enum):
    """Campaign status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"
