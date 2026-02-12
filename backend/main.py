"""Main FastAPI application."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.config import settings
from app.routes import (
    auth_router,
    campaigns_router,
    assets_router,
    billing_router,
)
from app.routes.ad_agent import router as ad_agent_router

# Configure logging to both console and file
import os
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(log_dir, exist_ok=True)

# Configure logging format
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_level = getattr(logging, settings.LOG_LEVEL)

# Create handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(logging.Formatter(log_format))

# File handler with rotation (max 10MB, keep 5 backups)
file_handler = RotatingFileHandler(
    os.path.join(log_dir, "ai_ad_agent.log"),
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter(log_format))

# Configure root logger
logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[console_handler, file_handler]
)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {os.path.join(log_dir, 'ai_ad_agent.log')}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"GCP Project: {settings.GCP_PROJECT_ID}")

    # Load secrets from Secret Manager
    try:
        from app.secrets import ensure_secrets_loaded
        ensure_secrets_loaded()
        logger.info("Secrets loaded from Secret Manager")
    except Exception as e:
        logger.warning(f"Failed to load secrets from Secret Manager: {e}")
        logger.warning("Continuing with environment variables...")

    # Initialize services
    try:
        from app.database import get_db, get_storage

        try:
            db = get_db()
            logger.info("Firestore initialized")
        except Exception as e:
            logger.warning(f"Firestore not initialized: {e}")

        try:
            storage = get_storage()
            logger.info("GCS Storage initialized")
        except Exception as e:
            logger.warning(f"GCS Storage not initialized: {e}")

    except Exception as e:
        logger.error(f"Failed to load database module: {e}")
        logger.warning("Continuing with limited functionality...")

    # Verify ffmpeg is available (required for video processing)
    try:
        from app.ad_agent.utils.video_utils import VideoProcessor
        if VideoProcessor.check_ffmpeg():
            logger.info("FFmpeg available for video processing")
        else:
            logger.error("FFmpeg not found - video processing will fail!")
            raise RuntimeError("FFmpeg is required but not installed")
    except Exception as e:
        logger.error(f"FFmpeg check failed: {e}")
        raise

    logger.info("Application startup complete!")

    yield

    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered ad creative generation agent",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


# Include routers
app.include_router(auth_router, prefix="/api")
app.include_router(campaigns_router, prefix="/api")
app.include_router(assets_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(ad_agent_router, prefix="/api")  # AI Ad Agent


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
