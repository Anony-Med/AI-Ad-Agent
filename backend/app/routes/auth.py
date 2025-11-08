"""Authentication endpoints."""
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.schemas import (
    UserLogin,
    UserRegister,
    Token,
    UserInfo,
    MessageResponse,
)
from app.services.unified_api_client import unified_api_client, UnifiedAPIError
from app.middleware.auth import get_current_user
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    """
    Register a new user via Unified API.

    Creates an account in the Unified API and returns a JWT token.
    Also creates a user record in Firestore for campaign management.
    """
    try:
        # Register via Unified API
        token = await unified_api_client.register(
            email=user_data.email,
            password=user_data.password,
            name=user_data.name,
        )

        # Get user info to extract user_id
        user_info = await unified_api_client.get_user_info()

        # Create user record in Firestore
        db = get_db()
        await db.create_user(
            user_id=user_info.id,
            email=user_info.email,
            name=user_data.name,
        )

        logger.info(f"User registered: {user_info.email}")
        return token

    except UnifiedAPIError as e:
        logger.error(f"Registration failed: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login to get JWT token.

    Authenticates with the Unified API and returns a JWT token
    that can be used for subsequent authenticated requests.
    """
    try:
        token = await unified_api_client.login(
            email=credentials.email,
            password=credentials.password,
        )

        logger.info(f"User logged in: {credentials.email}")
        return token

    except UnifiedAPIError as e:
        logger.error(f"Login failed: {e.message}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: UserInfo = Depends(get_current_user)):
    """
    Get current user information.

    Returns user profile data including credits and spending from Unified API.
    """
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout (client-side token removal).

    Since we're using JWT tokens, logout is handled client-side by removing the token.
    This endpoint is provided for consistency with typical auth flows.
    """
    return MessageResponse(message="Logged out successfully. Please remove your token.")
