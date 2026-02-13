"""
Secret Manager Integration

This module provides utilities for fetching API keys from GCP Secret Manager.
It supports both global secrets (ai_ad_agent_*) and user-specific secrets (ai_ad_agent_{user_id}_*).

Usage:
    from app.secrets import get_secret, get_user_secret

    # Get global API key
    gemini_key = get_secret("ai_ad_agent_gemini_api_key")

    # Get user-specific API key (falls back to global if not found)
    user_gemini_key = get_user_secret("user123", "gemini")  # returns str or None
"""

import os
from typing import Optional
from google.cloud import secretmanager
import logging

logger = logging.getLogger(__name__)

# GCP Project ID (from environment or hardcoded fallback)
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "sound-invention-432122-m5")

# Initialize Secret Manager client (singleton)
_client = None
_client_init_failed = False


def get_client() -> Optional[secretmanager.SecretManagerServiceClient]:
    """
    Get or create the Secret Manager client (singleton pattern).

    Returns:
        SecretManagerServiceClient instance
    """
    global _client, _client_init_failed
    if _client_init_failed:
        return None

    if _client is None:
        try:
            _client = secretmanager.SecretManagerServiceClient()
            logger.info(f"Initialized Secret Manager client for project: {PROJECT_ID}")
        except Exception as e:
            logger.error(f"Failed to initialize Secret Manager client: {e}")
            _client = None
            _client_init_failed = True
    return _client


def get_secret(secret_id: str, default: Optional[str] = None) -> Optional[str]:
    """
    Fetch a secret from GCP Secret Manager.

    Always fetches the latest version from Secret Manager (no caching).

    Args:
        secret_id: The secret ID (e.g., "ai_ad_agent_gemini_api_key")
        default: Default value if secret not found

    Returns:
        Secret value as string, or default if not found

    Example:
        >>> gemini_key = get_secret("ai_ad_agent_gemini_api_key")
        >>> elevenlabs_key = get_secret("ai_ad_agent_elevenlabs_api_key", "default-key")
    """
    client = get_client()
    if not client:
        logger.warning(f"Secret Manager client not available, using default for {secret_id}")
        return default

    try:
        # Construct the secret path
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"

        # Access the secret
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")

        logger.info(f"Successfully fetched secret: {secret_id}")
        return secret_value

    except Exception as e:
        logger.warning(f"Failed to fetch secret {secret_id}: {e}. Using default.")
        return default


def get_user_secret(user_id: str, provider: str) -> Optional[str]:
    """
    Fetch an API key from Secret Manager by provider name.

    Uses a direct mapping from provider to the known secret name in Secret Manager.

    Args:
        user_id: User identifier (for logging)
        provider: Provider name (gemini, elevenlabs, anthropic, google, openai)

    Returns:
        Secret value or None
    """
    from app.config import settings

    secret_names = {
        "gemini": settings.SECRET_NAME_GEMINI,
        "google": settings.SECRET_NAME_GEMINI,
        "elevenlabs": settings.SECRET_NAME_ELEVENLABS,
        "anthropic": settings.SECRET_NAME_ANTHROPIC,
    }

    if provider in secret_names:
        secret = get_secret(secret_names[provider])
        if secret:
            return secret

    logger.warning(f"No secret found for provider {provider} (user {user_id})")
    return None


def get_ai_agent_credentials(user_id: str = "global") -> dict:
    """
    Fetch all AI Ad Agent credentials for a user.

    Args:
        user_id: User identifier (defaults to "global" for shared credentials)

    Returns:
        Dictionary with provider credentials:
        {
            "GEMINI_API_KEY": "...",       # Google Gemini for text generation
            "GOOGLE_AI_API_KEY": "...",    # Alias for Gemini
            "ELEVENLABS_API_KEY": "...",   # ElevenLabs for audio
        }

    Example:
        >>> creds = get_ai_agent_credentials("user123")
        >>> gemini_key = creds.get("GEMINI_API_KEY")
    """
    credentials = {}

    from app.config import settings

    if user_id == "global":
        # Global startup: fetch from known secret names directly
        gemini_key = get_secret(settings.SECRET_NAME_GEMINI)
        elevenlabs_key = get_secret(settings.SECRET_NAME_ELEVENLABS)
    else:
        # User-specific: use fallback chain
        gemini_key = get_user_secret(user_id, "gemini")
        if not gemini_key:
            gemini_key = get_user_secret(user_id, "google")
        elevenlabs_key = get_user_secret(user_id, "elevenlabs")

    if gemini_key:
        credentials["GEMINI_API_KEY"] = gemini_key
        credentials["GOOGLE_AI_API_KEY"] = gemini_key  # Alias

    if elevenlabs_key:
        credentials["ELEVENLABS_API_KEY"] = elevenlabs_key

    # GCS Bucket Name (from env, or Secret Manager if stored there)
    credentials["GCS_BUCKET_NAME"] = os.getenv("GCS_BUCKET_NAME", "")

    return credentials


def set_env_from_secrets(user_id: str = "global"):
    """
    Load all AI Agent credentials from Secret Manager and set as environment variables.

    This is useful for agents that expect environment variables to be set.

    Args:
        user_id: User identifier (defaults to "global" for shared credentials)

    Example:
        >>> set_env_from_secrets()  # Load global credentials
        >>> set_env_from_secrets("user123")  # Load user-specific credentials
    """
    credentials = get_ai_agent_credentials(user_id)

    for key, value in credentials.items():
        os.environ[key] = value
        logger.info(f"Set environment variable: {key}")

    logger.info(f"Loaded {len(credentials)} credentials from Secret Manager for user: {user_id}")


# Cache for environment variable check
_env_loaded = False


def ensure_secrets_loaded():
    """
    Ensure that secrets have been loaded from Secret Manager into environment variables.

    This function should be called at application startup to populate environment
    variables from Secret Manager. It only runs once (singleton pattern).

    Example:
        >>> from app.secrets import ensure_secrets_loaded
        >>> ensure_secrets_loaded()
    """
    global _env_loaded
    if not _env_loaded:
        logger.info("Loading secrets from Secret Manager...")
        set_env_from_secrets()
        _env_loaded = True
        logger.info("Secrets loaded successfully")
    else:
        logger.debug("Secrets already loaded, skipping")


def save_user_secret(user_id: str, provider: str, key_type: str, secret_value: str) -> bool:
    """
    Save a user-specific API key to Secret Manager.

    Naming convention: ai_ad_agent_{user_id}_{provider}_{key_type}

    Args:
        user_id: User identifier
        provider: Provider name (gemini, elevenlabs, google, etc.)
        key_type: Key type (api_key, secret_key)
        secret_value: The API key value to save

    Returns:
        True if successful, False otherwise

    Example:
        >>> save_user_secret("user123", "gemini", "api_key", "AIzaSy...")
    """
    client = get_client()
    if not client:
        logger.error("Secret Manager client not available")
        return False

    try:
        secret_id = f"ai_ad_agent_{user_id}_{provider}_{key_type}"
        parent = f"projects/{PROJECT_ID}"

        # Try to create the secret first (if it doesn't exist)
        try:
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            logger.info(f"Created new secret: {secret_id}")
        except Exception as e:
            # Secret already exists, that's fine
            if "already exists" not in str(e).lower():
                logger.warning(f"Error creating secret (may already exist): {e}")

        # Add the secret version with the value
        secret_name = f"{parent}/secrets/{secret_id}"
        client.add_secret_version(
            request={
                "parent": secret_name,
                "payload": {"data": secret_value.encode("UTF-8")},
            }
        )

        logger.info(f"Successfully saved secret: {secret_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save secret {provider}/{key_type} for user {user_id}: {e}")
        return False
