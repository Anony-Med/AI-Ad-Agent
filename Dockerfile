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
RUN apt-get update && apt-get install -y \
    gcc \
    ffmpeg \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first for better Docker layer caching
# This layer only rebuilds when requirements.txt changes
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# This includes all modules, routes, and utilities
COPY backend/app/ ./app/
COPY backend/main.py ./main.py

# Create necessary directories for runtime
# - outputs: Local cache for generated files before GCS upload
# - logs: Application logs
RUN mkdir -p outputs logs

# Set default port (Cloud Run will override with PORT=8080)
ENV PORT=8000

# Expose port (dynamic based on PORT env var)
EXPOSE $PORT

# Note: Health check disabled for Cloud Run compatibility
# Cloud Run has its own health check mechanism
# HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:${PORT}/api/ad-agent/health')" || exit 1

# Run the FastAPI application using uvicorn
# - host 0.0.0.0: Accept connections from outside container
# - port $PORT: Uses PORT environment variable (8000 locally, 8080 on Cloud Run)
# Note: API keys are fetched from GCP Secret Manager at startup
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
