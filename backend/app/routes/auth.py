"""Authentication endpoints."""
import uuid
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.schemas import (
    UserLogin,
    UserRegister,
    Token,
    UserInfo,
    MessageResponse,
)
from app.auth import hash_password, verify_password, create_access_token
from app.middleware.auth import get_current_user
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister):
    """
    Register a new user.

    Creates a user record in Firestore and returns a JWT token.
    """
    db = get_db()

    # Check if email already exists
    existing = await db.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user_id = str(uuid.uuid4())
    hashed_pw = hash_password(user_data.password)

    await db.create_user(
        user_id=user_id,
        email=user_data.email,
        name=user_data.name or user_data.email,
        password_hash=hashed_pw,
    )

    # Generate token
    token = create_access_token({
        "user_id": user_id,
        "email": user_data.email,
        "name": user_data.name or user_data.email,
    })

    logger.info(f"User registered: {user_data.email}")
    return Token(access_token=token)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login to get JWT token.

    Authenticates against local Firestore and returns a JWT token.
    """
    db = get_db()

    # Look up user by email
    user = await db.get_user_by_email(credentials.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    stored_hash = user.get("password_hash", "")
    if not stored_hash or not verify_password(credentials.password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate token
    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "name": user.get("name", ""),
    })

    logger.info(f"User logged in: {credentials.email}")
    return Token(access_token=token)


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: UserInfo = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout (client-side token removal).

    Since we're using JWT tokens, logout is handled client-side by removing the token.
    """
    return MessageResponse(message="Logged out successfully. Please remove your token.")
