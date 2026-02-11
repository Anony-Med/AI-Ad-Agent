"""
Secret Manager Integration (Unified API Pattern)

This module provides utilities for fetching API keys from GCP Secret Manager.
It supports both global secrets (ai_ad_agent_*) and user-specific secrets (ai_ad_agent_{user_id}_*).

Pattern from Unified API for consistency across projects.

Usage:
    from app.secrets import get_secret, get_user_secret

    # Get global API key
    gemini_key = get_secret("ai_ad_agent_gemini_api_key")

    # Get user-specific API key (falls back to global if not found)
    user_gemini_key = get_user_secret("user123", "gemini")
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


def get_user_secret(
    user_id: str,
    provider: str,
    key_type: str = "api_key",
    fallback_to_global: bool = True
) -> Optional[str]:
    """
    Fetch a user-specific API key from Secret Manager.

    Naming convention: ai_ad_agent_{user_id}_{provider}_{key_type}

    Fallback chain (if fallback_to_global=True):
    1. ai_ad_agent_{user_id}_{provider}_{key_type} (user-specific)
    2. ai_ad_agent_{provider}_{key_type} (global AI ad agent)
    3. unified_api_{provider}_{key_type} (shared with Unified API)
    4. Environment variable

    Args:
        user_id: User identifier
        provider: Provider name (gemini, elevenlabs, google, etc.)
        key_type: Key type (api_key, secret_key)
        fallback_to_global: If True, fall back to global secret if user secret not found

    Returns:
        Secret value or None

    Example:
        >>> # Try user-specific, fall back to global, then unified API
        >>> key = get_user_secret("user123", "gemini", "api_key")

        >>> # User-specific only (no fallback)
        >>> key = get_user_secret("user123", "elevenlabs", "api_key", fallback_to_global=False)
    """
    # Try user-specific secret first
    user_secret_id = f"ai_ad_agent_{user_id}_{provider}_{key_type}"
    secret = get_secret(user_secret_id)

    if secret:
        logger.info(f"Using user-specific secret for {user_id}/{provider}")
        return secret

    # Fall back to global secret if enabled
    if fallback_to_global:
        # Try AI Ad Agent global secret
        global_secret_id = f"ai_ad_agent_{provider}_{key_type}"
        secret = get_secret(global_secret_id)
        if secret:
            logger.info(f"Using AI ad agent global secret for {provider} (user {user_id})")
            return secret

        # Fall back to Unified API secret (for compatibility)
        unified_secret_id = f"unified_api_{provider}_{key_type}"
        secret = get_secret(unified_secret_id)
        if secret:
            logger.info(f"Using Unified API secret for {provider} (user {user_id})")
            return secret

        # Try alternate naming patterns (for compatibility with existing secrets)
        alternate_names = {
            "elevenlabs": ["eleven-labs-api-key", "unified_api_elevenlabs_api_key"],
            "google": ["unified_api_google_api_key", "GOOGLE_API_KEY"],
            "gemini": ["unified_api_google_api_key", "GOOGLE_API_KEY"],
            "openai": ["unified_api_openai_api_key", "openai-api-key"],
        }

        if provider in alternate_names:
            for alternate_secret_id in alternate_names[provider]:
                secret = get_secret(alternate_secret_id)
                if secret:
                    logger.info(f"Using alternate secret '{alternate_secret_id}' for {provider} (user {user_id})")
                    return secret

    logger.warning(f"No secret found for user {user_id}, provider {provider}, key_type {key_type}")
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
            "UNIFIED_API_BASE_URL": "..."  # Unified API endpoint
        }

    Example:
        >>> creds = get_ai_agent_credentials("user123")
        >>> gemini_key = creds.get("GEMINI_API_KEY")
    """
    # Determine if we're fetching user-specific or global credentials
    fallback = (user_id == "global")

    credentials = {}

    # Gemini API Key (for prompt generation and creative suggestions)
    gemini_key = get_user_secret(user_id, "gemini", "api_key", fallback_to_global=fallback)
    if not gemini_key:
        # Try google as fallback (compatible with unified API naming)
        gemini_key = get_user_secret(user_id, "google", "api_key", fallback_to_global=fallback)
    if gemini_key:
        credentials["GEMINI_API_KEY"] = gemini_key
        credentials["GOOGLE_AI_API_KEY"] = gemini_key  # Alias

    # ElevenLabs API Key (for audio: TTS, music, SFX)
    elevenlabs_key = get_user_secret(user_id, "elevenlabs", "api_key", fallback_to_global=fallback)
    if elevenlabs_key:
        credentials["ELEVENLABS_API_KEY"] = elevenlabs_key

    # Unified API Base URL (same for all users, but configurable per environment)
    unified_api_url = get_secret("ai_ad_agent_unified_api_url")
    if unified_api_url:
        credentials["UNIFIED_API_BASE_URL"] = unified_api_url
    else:
        # Fallback to environment variable
        credentials["UNIFIED_API_BASE_URL"] = os.getenv(
            "UNIFIED_API_BASE_URL",
            "https://unified-api-interface-994684344365.europe-west1.run.app"
        )

    # GCS Bucket Name
    bucket_name = get_secret("ai_ad_agent_gcs_bucket")
    if bucket_name:
        credentials["GCS_BUCKET_NAME"] = bucket_name
    else:
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
