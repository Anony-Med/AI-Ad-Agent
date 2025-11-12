"""Authentication middleware and dependencies."""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
from app.models.schemas import UserInfo

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify JWT token via Unified API and return user ID."""
    token = credentials.credentials

    # Set token for unified API client
    unified_api_client.set_token(token)

    try:
        # Verify token by fetching user info from Unified API
        user_info = await unified_api_client.get_user_info()
        return user_info.id
    except UnifiedAPIError as e:
        logger.error(f"Token verification failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Get current user ID from token."""
    return await verify_token(credentials)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInfo:
    """Get current user information from Unified API."""
    token = credentials.credentials
    unified_api_client.set_token(token)

    try:
        # Verify token with Unified API and get user info
        user_info = await unified_api_client.get_user_info()
        return user_info

    except UnifiedAPIError as e:
        if e.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify user: {e.message}",
        )
