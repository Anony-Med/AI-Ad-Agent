"""API routes."""
from .auth import router as auth_router
from .campaigns import router as campaigns_router
from .assets import router as assets_router
from .billing import router as billing_router
from .history import router as history_router

__all__ = [
    "auth_router",
    "campaigns_router",
    "assets_router",
    "billing_router",
    "history_router",
]
