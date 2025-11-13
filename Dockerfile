##############################################################################
# Dockerfile for AI Ad Agent
#
# This container runs the FastAPI application with:
# - Python 3.11 slim base image
# - Video generation pipeline (Veo, ElevenLabs, Gemini)
# - GCP Secret Manager integration for API keys
# - GCP Cloud Storage integration for video storage
# - FFmpeg for video processing
#
# Environment variables required:
#   - GCP_PROJECT_ID: GCP project ID (for Secret Manager and GCS)
#   - GCS_BUCKET_NAME: GCS bucket for storing videos
#
# Exposed ports:
#   - 8000: FastAPI application
#
# Health check:
#   - GET /api/ad-agent/health endpoint checked every 30s
##############################################################################

# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Set environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for Python packages and video processing
# gcc: Required for building some Python packages
# ffmpeg: Required for video processing and merging clips
# libpq-dev: PostgreSQL library
# gcsfuse: Mount GCS bucket as local filesystem (OPTION 1 for zero-download video merging)
# curl, lsb-release, gnupg: Required for gcsfuse installation
RUN apt-get update && apt-get install -y \
    gcc \
    ffmpeg \
    libpq-dev \
    curl \
    lsb-release \
    gnupg \
    fuse \
    && rm -rf /var/lib/apt/lists/* \
    && which ffmpeg \
    && ffmpeg -version

# Install gcsfuse for GCS Fuse mounting (Option 1)
# This allows FFmpeg to read videos directly from GCS without downloading
RUN export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s` \
    && echo "deb https://packages.cloud.google.com/apt $GCSFUSE_REPO main" | tee /etc/apt/sources.list.d/gcsfuse.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - \
    && apt-get update \
    && apt-get install -y gcsfuse \
    && rm -rf /var/lib/apt/lists/* \
    && which gcsfuse \
    && gcsfuse --version

# Copy requirements file first for better Docker layer caching
# This layer only rebuilds when requirements.txt changes
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# This includes all modules, routes, and utilities
COPY backend/app/ ./app/
COPY backend/main.py ./main.py
COPY backend/startup.sh ./startup.sh

# Make startup script executable
RUN chmod +x ./startup.sh

# Create necessary directories for runtime
# - outputs: Local cache for generated files before GCS upload
# - logs: Application logs
# - /mnt/gcs: Mount point for GCS Fuse (Option 1)
RUN mkdir -p outputs logs /mnt/gcs

# Set default port (Cloud Run will override with PORT=8080)
ENV PORT=8000

# Expose port (dynamic based on PORT env var)
EXPOSE $PORT

# Note: Health check disabled for Cloud Run compatibility
# Cloud Run has its own health check mechanism
# HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:${PORT}/api/ad-agent/health')" || exit 1

# Run the startup script which:
# 1. Attempts to mount GCS bucket via gcsfuse (Option 1 for zero-download merging)
# 2. Starts the FastAPI application using uvicorn
# - host 0.0.0.0: Accept connections from outside container
# - port $PORT: Uses PORT environment variable (8000 locally, 8080 on Cloud Run)
# Note: API keys are fetched from GCP Secret Manager at startup
CMD ["./startup.sh"]
