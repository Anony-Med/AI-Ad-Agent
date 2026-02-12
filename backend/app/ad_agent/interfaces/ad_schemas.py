"""Schemas for AI Ad Agent."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from app.config import settings


class AdJobStatus(str, Enum):
    """Status of ad creation job."""
    PENDING = "pending"
    ANALYZING_SCRIPT = "analyzing_script"
    GENERATING_VOICEOVER = "generating_voiceover"  # NEW: Generate audio first
    SEGMENTING_AUDIO = "segmenting_audio"  # NEW: Segment audio by script
    GENERATING_PROMPTS = "generating_prompts"
    GENERATING_SCENE_IMAGES = "generating_scene_images"
    GENERATING_VIDEOS = "generating_videos"
    VERIFYING_CLIPS = "verifying_clips"  # Verify clips match script
    MERGING_VIDEOS = "merging_videos"
    GETTING_SUGGESTIONS = "getting_suggestions"
    APPLYING_ENHANCEMENTS = "applying_enhancements"  # NEW: Apply creative suggestions
    ENHANCING_VOICE = "enhancing_voice"
    ADDING_AUDIO = "adding_audio"
    ORCHESTRATING = "orchestrating"  # Claude agent is deciding next step
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class ClipVerification(BaseModel):
    """Verification results for a video clip."""
    verified: bool = False
    confidence_score: float = 0.0  # 0.0 to 1.0
    description: Optional[str] = None  # Gemini's analysis description
    script_segment: Optional[str] = None  # Expected script content
    retry_count: int = 0


class VideoClip(BaseModel):
    """Individual video clip information."""
    clip_number: int
    prompt: str
    script_segment: Optional[str] = None  # Corresponding script text
    audio_segment_path: Optional[str] = None  # Path to audio segment for this clip
    target_duration: float = 7.0  # Target duration from audio analysis
    veo_job_id: Optional[str] = None
    video_url: Optional[str] = None  # Unified API video URL (legacy)
    video_b64: Optional[str] = None  # Base64 encoded video from Direct Veo API
    gcs_url: Optional[str] = None  # Our GCS bucket URL (for checkpoint/resume)
    duration: float = 7.0  # Actual duration (may differ from target)
    status: str = "pending"
    error: Optional[str] = None
    verification: Optional[ClipVerification] = None  # Clip verification results


class CreativeSuggestion(BaseModel):
    """Creative suggestions from Gemini."""
    animations: List[str] = Field(default_factory=list)
    text_overlays: List[str] = Field(default_factory=list)
    gifs: List[str] = Field(default_factory=list)
    effects: List[str] = Field(default_factory=list)
    general_feedback: Optional[str] = None


class AdRequest(BaseModel):
    """Request to create an AI video ad."""
    campaign_id: str = Field(..., description="Campaign ID from campaigns table")
    script: str = Field(..., description="The dialogue/script for the ad")
    character_image: str = Field(..., description="Base64 encoded image of the character (e.g., Heather)")
    character_name: Optional[str] = Field(default="character", description="Name of the character")
    voice_id: Optional[str] = Field(default=None, description="ElevenLabs voice ID (e.g., Bella)")
    background_music_prompt: Optional[str] = Field(default=None, description="Prompt for background music")
    add_sound_effects: bool = Field(default=True, description="Whether to add sound effects")
    aspect_ratio: str = Field(default_factory=lambda: settings.VEO_DEFAULT_ASPECT_RATIO, description="Aspect ratio for videos")
    resolution: str = Field(default_factory=lambda: settings.VEO_DEFAULT_RESOLUTION, description="Video resolution")
    # Verification settings
    enable_verification: bool = Field(
        default=True,
        description="Verify generated clips match script content using Gemini Vision"
    )
    verification_threshold: float = Field(
        default_factory=lambda: settings.VERIFICATION_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score (0.0-1.0) for clip verification to pass"
    )
    # Logo settings (NEW)
    logo_image: Optional[str] = Field(
        default=None,
        description="Base64 encoded logo image (PNG with transparency recommended)"
    )
    logo_position: str = Field(
        default="bottom-right",
        description="Logo position: top-left, top-right, bottom-left, bottom-right, center"
    )
    logo_size: int = Field(
        default_factory=lambda: settings.LOGO_DEFAULT_SIZE,
        ge=50,
        le=500,
        description="Logo width in pixels (height auto-scaled)"
    )
    logo_opacity: float = Field(
        default_factory=lambda: settings.LOGO_DEFAULT_OPACITY,
        ge=0.0,
        le=1.0,
        description="Logo opacity (0.0 = transparent, 1.0 = opaque)"
    )
    logo_timing: str = Field(
        default="always",
        description="When to show logo: always, intro (first 3s), outro (last 3s), none"
    )


class AdJob(BaseModel):
    """Ad creation job status."""
    job_id: str
    campaign_id: str
    user_id: str
    status: AdJobStatus
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    current_step: Optional[str] = None

    # Input
    script: str
    character_image: str  # Base64 or GCS URL (kept for backward compatibility)
    character_image_gcs_url: Optional[str] = None  # GCS URL for large images
    character_name: str

    # Generated outputs
    audio_segments: List[Dict[str, Any]] = Field(default_factory=list)  # NEW: Audio segments with durations
    veo_prompts: List[str] = Field(default_factory=list)
    video_clips: List[VideoClip] = Field(default_factory=list)
    merged_video_url: Optional[str] = None
    creative_suggestions: Optional[CreativeSuggestion] = None
    final_video_url: Optional[str] = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Costs
    total_cost: float = 0.0
    cost_breakdown: Dict[str, float] = Field(default_factory=dict)


class AdJobResponse(BaseModel):
    """Response for ad job status."""
    job_id: str
    status: AdJobStatus
    progress: int
    current_step: Optional[str] = None
    final_video_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class VeoPromptRequest(BaseModel):
    """Request to generate Veo prompts from script."""
    script: str
    character_name: str = "character"
    max_clip_duration: int = Field(default_factory=lambda: settings.DEFAULT_CLIP_DURATION)


class VeoPromptResponse(BaseModel):
    """Response with generated Veo prompts."""
    prompts: List[str]
    total_clips: int
    estimated_duration: float
