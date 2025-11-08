"""Google Secret Manager integration."""
import logging
from typing import Optional, Dict, Any
from google.cloud import secretmanager
from google.api_core import exceptions
from app.config import settings

logger = logging.getLogger(__name__)


class SecretsManager:
    """Manage secrets from Google Cloud Secret Manager."""

    def __init__(self):
        """Initialize Secret Manager client."""
        self.client = None
        self.project_id = settings.GCP_PROJECT_ID
        self._cache: Dict[str, str] = {}

        if settings.USE_SECRET_MANAGER:
            try:
                self.client = secretmanager.SecretManagerServiceClient()
                logger.info("Secret Manager client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Secret Manager: {e}")
                logger.warning("Falling back to environment variables")

    def get_secret(self, secret_name: str, version: str = "latest") -> Optional[str]:
        """
        Retrieve a secret from Secret Manager.

        Args:
            secret_name: Name of the secret
            version: Version of the secret (default: latest)

        Returns:
            Secret value as string, or None if not found
        """
        # Check cache first
        cache_key = f"{secret_name}:{version}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # If Secret Manager is disabled or not available, return None
        if not self.client or not settings.USE_SECRET_MANAGER:
            logger.debug(f"Secret Manager disabled, secret '{secret_name}' not loaded")
            return None

        try:
            # Build the secret version name
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/{version}"

            # Access the secret
            response = self.client.access_secret_version(request={"name": name})
            secret_value = response.payload.data.decode("UTF-8")

            # Cache the value
            self._cache[cache_key] = secret_value

            logger.info(f"Successfully loaded secret: {secret_name}")
            return secret_value

        except exceptions.NotFound:
            logger.error(f"Secret not found: {secret_name}")
            return None
        except exceptions.PermissionDenied:
            logger.error(f"Permission denied for secret: {secret_name}")
            logger.error("Ensure the service account has 'Secret Manager Secret Accessor' role")
            return None
        except Exception as e:
            logger.error(f"Error accessing secret {secret_name}: {e}")
            return None

    def create_secret(self, secret_name: str, secret_value: str) -> bool:
        """
        Create a new secret in Secret Manager.

        Args:
            secret_name: Name of the secret
            secret_value: Value to store

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("Secret Manager client not initialized")
            return False

        try:
            # Create the parent project resource
            parent = f"projects/{self.project_id}"

            # Create the secret
            try:
                secret = self.client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_name,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
                logger.info(f"Created secret: {secret_name}")
            except exceptions.AlreadyExists:
                logger.info(f"Secret {secret_name} already exists, adding new version")

            # Add the secret version
            parent_secret = f"projects/{self.project_id}/secrets/{secret_name}"
            payload = secret_value.encode("UTF-8")

            self.client.add_secret_version(
                request={
                    "parent": parent_secret,
                    "payload": {"data": payload},
                }
            )

            logger.info(f"Added version to secret: {secret_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating secret {secret_name}: {e}")
            return False

    def update_secret(self, secret_name: str, secret_value: str) -> bool:
        """
        Update a secret by adding a new version.

        Args:
            secret_name: Name of the secret
            secret_value: New value

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.error("Secret Manager client not initialized")
            return False

        try:
            parent = f"projects/{self.project_id}/secrets/{secret_name}"
            payload = secret_value.encode("UTF-8")

            self.client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": payload},
                }
            )

            # Invalidate cache
            cache_key = f"{secret_name}:latest"
            if cache_key in self._cache:
                del self._cache[cache_key]

            logger.info(f"Updated secret: {secret_name}")
            return True

        except Exception as e:
            logger.error(f"Error updating secret {secret_name}: {e}")
            return False

    def list_secrets(self) -> list:
        """
        List all secrets in the project.

        Returns:
            List of secret names
        """
        if not self.client:
            logger.error("Secret Manager client not initialized")
            return []

        try:
            parent = f"projects/{self.project_id}"
            secrets = self.client.list_secrets(request={"parent": parent})

            secret_names = []
            for secret in secrets:
                # Extract secret name from full path
                name = secret.name.split("/")[-1]
                secret_names.append(name)

            return secret_names

        except Exception as e:
            logger.error(f"Error listing secrets: {e}")
            return []


# Singleton instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get or create SecretsManager singleton."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def load_secrets_to_config():
    """
    Load secrets from Secret Manager into settings.
    Called during application startup.
    """
    if not settings.USE_SECRET_MANAGER:
        logger.info("Secret Manager disabled, using environment variables")
        return

    secrets_mgr = get_secrets_manager()

    # Load SECRET_KEY if not set
    if not settings.SECRET_KEY:
        secret_key = secrets_mgr.get_secret(settings.SECRET_MANAGER_SECRET_KEY_NAME)
        if secret_key:
            settings.SECRET_KEY = secret_key
            logger.info("Loaded SECRET_KEY from Secret Manager")
        else:
            logger.warning("SECRET_KEY not found in Secret Manager")

    # Load other secrets as needed
    # You can add more secrets here

    logger.info("Secrets loaded from Secret Manager")
