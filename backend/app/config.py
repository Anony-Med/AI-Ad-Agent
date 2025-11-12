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

    # Unified API
    UNIFIED_API_BASE_URL: str = "https://unified-api-interface-994684344365.europe-west1.run.app"
    UNIFIED_API_TIMEOUT: int = 300

    # Google Cloud Platform
    GCP_PROJECT_ID: str = "sound-invention-432122-m5"
    GCP_REGION: str = "europe-west1"
    FIRESTORE_DATABASE: str = "ai-ad-agent"  # AI Ad Agent Firestore database
    GCS_BUCKET_NAME: str = "ai-ad-agent-videos"  # AI Ad Agent GCS bucket

    # Optional: Path to service account key (for local development)
    # In production, use Workload Identity
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Secret Manager Configuration
    USE_SECRET_MANAGER: bool = True  # Set to False for local dev with .env

    # Secret names in Secret Manager (not the actual values!)
    SECRET_MANAGER_SECRET_KEY_NAME: str = "ai-ad-agent-secret-key"
    SECRET_MANAGER_API_CREDENTIALS_NAME: str = "unified-api-credentials"

    # Security (loaded from Secret Manager in production)
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Background Jobs
    JOB_POLL_INTERVAL: int = 5
    JOB_MAX_RETRIES: int = 3
    JOB_TIMEOUT: int = 600

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
