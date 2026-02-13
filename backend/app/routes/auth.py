"""Authentication endpoints."""
import uuid
import logging
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.schemas import (
    UserLogin,
    UserRegister,
    Token,
    UserInfo,
    UserUpdate,
    MessageResponse,
)
from app.auth import hash_password, verify_password, create_access_token
from app.middleware.auth import get_current_user, get_current_user_id
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class ForgotPasswordRequest(BaseModel):
    email: str


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
    name = user_data.full_name or user_data.name or user_data.username or user_data.email

    await db.create_user(
        user_id=user_id,
        email=user_data.email,
        name=name,
        password_hash=hashed_pw,
    )

    # Generate token
    token = create_access_token({
        "user_id": user_id,
        "email": user_data.email,
        "name": name,
    })

    logger.info(f"User registered: {user_data.email}")
    return Token(
        access_token=token,
        user_id=user_id,
        email=user_data.email,
        username=name,
    )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login to get JWT token.

    Accepts username (treated as email) or email field.
    """
    db = get_db()

    # Accept username as email alias
    email = credentials.email or credentials.username
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username is required",
        )

    # Look up user by email
    user = await db.get_user_by_email(email)
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

    name = user.get("name", "")

    # Generate token
    token = create_access_token({
        "user_id": user["id"],
        "email": user["email"],
        "name": name,
    })

    logger.info(f"User logged in: {email}")
    return Token(
        access_token=token,
        user_id=user["id"],
        email=user["email"],
        username=name,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: UserInfo = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.put("/me", response_model=UserInfo)
async def update_me(
    updates: UserUpdate,
    user_id: str = Depends(get_current_user_id),
):
    """Update current user profile."""
    db = get_db()

    update_fields = {}
    if updates.email is not None:
        update_fields["email"] = updates.email
    if updates.name is not None:
        update_fields["name"] = updates.name
    if updates.full_name is not None:
        update_fields["name"] = updates.full_name

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    updated_user = await db.update_user(user_id, **update_fields)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    name = updated_user.get("name", "")
    return UserInfo(
        user_id=updated_user["id"],
        email=updated_user["email"],
        username=name,
        name=name,
        full_name=name,
        created_at=updated_user.get("created_at"),
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Request password reset.

    Stub endpoint — always returns success to avoid leaking
    whether an email is registered.
    """
    logger.info(f"Password reset requested for: {request.email}")
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent.",
    )


@router.post("/logout", response_model=MessageResponse)
async def logout():
    """
    Logout (client-side token removal).

    Since we're using JWT tokens, logout is handled client-side by removing the token.
    """
    return MessageResponse(message="Logged out successfully. Please remove your token.")
