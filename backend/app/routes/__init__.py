"""API routes."""
from .auth import router as auth_router
from .campaigns import router as campaigns_router
from .generate import router as generate_router
from .assets import router as assets_router
from .billing import router as billing_router

__all__ = [
    "auth_router",
    "campaigns_router",
    "generate_router",
    "assets_router",
    "billing_router",
]
