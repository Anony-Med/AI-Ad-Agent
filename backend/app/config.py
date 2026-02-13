"""Application configuration management."""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "AI Ad Agent"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Google Cloud Platform
    GCP_PROJECT_ID: str = "sound-invention-432122-m5"
    GCP_REGION: str = "europe-west1"
    FIRESTORE_DATABASE: str = "ai-ad-agent"  # AI Ad Agent Firestore database
    GCS_BUCKET_NAME: str = "ai-ad-agent-videos"  # AI Ad Agent GCS bucket

    # Optional: Path to service account key (not recommended - use ADC instead)
    # For local dev: Use 'gcloud auth application-default login'
    # For production: Workload Identity provides ADC automatically
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Secret Manager Configuration
    USE_SECRET_MANAGER: bool = True  # Set to False for local dev with .env

    # Secret names in Secret Manager (not the actual values!)
    SECRET_MANAGER_SECRET_KEY_NAME: str = "ai-ad-agent-jwt-secret-key"
    SECRET_NAME_GEMINI: str = "unified_api_google_api_key"
    SECRET_NAME_ELEVENLABS: str = "eleven-labs-api-key"
    SECRET_NAME_ANTHROPIC: str = "ai_ad_agent_anthropic_api_key"

    # JWT Authentication
    JWT_SECRET_KEY: str = "change-me-in-production"  # Override via env or Secret Manager
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Background Jobs
    JOB_POLL_INTERVAL: int = 5
    JOB_MAX_RETRIES: int = 3
    JOB_TIMEOUT: int = 600

    # ──────────────────────────────────────────────
    # AI Models
    # ──────────────────────────────────────────────
    # VEO_MODEL_ID: str = "veo-3.1-fast-generate-preview"
    VEO_MODEL_ID: str = "veo-3.1-generate-preview"
    VEO_REGION: str = "us-central1"  # Veo API region (may differ from GCP_REGION)
    # GEMINI_MODEL: str = "gemini-3-flash-preview"
    GEMINI_MODEL: str = "gemini-3-pro-preview"
    GEMINI_REGION: str = "global"  # Gemini 3 requires 'global' location
    ELEVENLABS_TTS_MODEL: str = "eleven_turbo_v2_5"
    ELEVENLABS_STS_MODEL: str = "eleven_english_sts_v2"  # Speech-to-Speech
    # ANTHROPIC_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_MODEL: str = "claude-opus-4-6"
    ANTHROPIC_MAX_TOKENS: int = 128000
    GEMINI_IMAGE_MODEL: str = "gemini-3-pro-image-preview"
    GEMINI_IMAGE_REGION: str = "global"  # Gemini 3 Pro Image requires 'global' location

    # ──────────────────────────────────────────────
    # Voice Defaults
    # ──────────────────────────────────────────────
    DEFAULT_VOICE_NAME: str = "Bella"
    DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"

    # ──────────────────────────────────────────────
    # External API URLs
    # ──────────────────────────────────────────────
    ELEVENLABS_API_BASE_URL: str = "https://api.elevenlabs.io"

    # ──────────────────────────────────────────────
    # Timeouts (seconds)
    # ──────────────────────────────────────────────
    GEMINI_TIMEOUT: int = 120
    ELEVENLABS_TIMEOUT: int = 300
    VEO_HTTP_TIMEOUT: float = 30.0
    VIDEO_GENERATION_TIMEOUT: int = 600
    VEO_POLL_INTERVAL: int = 10
    AUDIO_EXTRACTION_TIMEOUT: int = 120
    AUDIO_REPLACEMENT_TIMEOUT: int = 300
    AUDIO_SPEED_TIMEOUT: int = 60
    GEMINI_VISION_TIMEOUT: int = 300
    SSE_KEEPALIVE_SECONDS: float = 15.0

    # ──────────────────────────────────────────────
    # Video Generation (Veo)
    # ──────────────────────────────────────────────
    VEO_DEFAULT_ASPECT_RATIO: str = "16:9"
    VEO_DEFAULT_RESOLUTION: str = "1080p"
    VEO_PERSON_GENERATION: str = "allow_all"
    VEO_ADD_WATERMARK: bool = True
    VEO_SAMPLE_COUNT: int = 4
    DEFAULT_CLIP_DURATION: int = 8
    CLIP_DURATION: int = 8
    CLIPS_PER_AD: int = 2
    MAX_CLIP_RETRIES: int = 3

    # ──────────────────────────────────────────────
    # Image Optimization
    # ──────────────────────────────────────────────
    IMAGE_MAX_SIZE: int = 768  # Max dimension (px) for Veo API
    IMAGE_QUALITY_JPEG: int = 85

    # ──────────────────────────────────────────────
    # ElevenLabs Audio
    # ──────────────────────────────────────────────
    ELEVENLABS_STABILITY: float = 0.5
    ELEVENLABS_SIMILARITY_BOOST: float = 0.75
    ELEVENLABS_SPEED: float = 1.0
    ELEVENLABS_OUTPUT_FORMAT: str = "mp3_44100_128"
    ELEVENLABS_USE_SPEAKER_BOOST: bool = True
    AUDIO_BITRATE: str = "192k"
    DEFAULT_SFX_DURATION: float = 3.0

    # ──────────────────────────────────────────────
    # Audio Analysis
    # ──────────────────────────────────────────────
    AUDIO_MIN_SILENCE_MS: int = 300
    AUDIO_SILENCE_THRESHOLD_DBFS: int = -40
    AUDIO_BREAK_TOLERANCE_MS: int = 2000
    AUDIO_MIN_SPEED_FACTOR: float = 0.8
    AUDIO_MAX_SPEED_FACTOR: float = 1.3

    # ──────────────────────────────────────────────
    # Gemini Text Generation
    # ──────────────────────────────────────────────
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_TEMPERATURE_CREATIVE: float = 0.8
    GEMINI_VISION_TEMPERATURE: float = 0.3

    # ──────────────────────────────────────────────
    # Gemini Image Generation
    # ──────────────────────────────────────────────
    GEMINI_IMAGE_TEMPERATURE: float = 1.0
    GEMINI_IMAGE_TOP_P: float = 0.95
    GEMINI_IMAGE_MAX_TOKENS: int = 65535
    GEMINI_IMAGE_SIZE: str = "1K"
    GEMINI_IMAGE_OUTPUT_MIME: str = "image/png"
    GEMINI_IMAGE_GENERATION_ATTEMPTS: int = 3

    # ──────────────────────────────────────────────
    # Clip Verification
    # ──────────────────────────────────────────────
    VERIFICATION_THRESHOLD: float = 0.95
    VERIFICATION_MAX_RETRIES: int = 3

    # ──────────────────────────────────────────────
    # Video Composition
    # ──────────────────────────────────────────────
    BACKGROUND_MUSIC_VOLUME: float = 0.3
    SFX_VOLUME: float = 0.7
    TEXT_OVERLAY_FONT_SIZE: int = 36
    LOGO_DEFAULT_SIZE: int = 150
    LOGO_DEFAULT_OPACITY: float = 0.8

    # ──────────────────────────────────────────────
    # Agentic Orchestrator
    # ──────────────────────────────────────────────
    AGENTIC_MAX_ITERATIONS: int = 25
    AGENTIC_MAX_DURATION_SECONDS: int = 1800  # 30 minutes
    HUMAN_IN_THE_LOOP: bool = False  # Console approval gate before each tool call

    # Asset Storage
    ASSET_DOWNLOAD_ENABLED: bool = True
    ASSET_MAX_SIZE_MB: int = 100

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra fields in .env
    )


settings = Settings()
