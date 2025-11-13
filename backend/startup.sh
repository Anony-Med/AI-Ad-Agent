#!/bin/bash
##############################################################################
# Startup script for AI Ad Agent
#
# This script:
# 1. Attempts to mount GCS bucket using gcsfuse (Option 1 - zero downloads)
# 2. Falls back gracefully if gcsfuse mount fails
# 3. Starts the FastAPI application
#
# Environment variables:
#   - GCS_BUCKET_NAME: GCS bucket to mount (required for gcsfuse)
#   - PORT: Application port (default: 8000)
##############################################################################

set -e

echo "========================================="
echo "AI Ad Agent - Startup"
echo "========================================="

# Check if GCS_BUCKET_NAME is set
if [ -z "$GCS_BUCKET_NAME" ]; then
    echo "⚠️  WARNING: GCS_BUCKET_NAME not set, skipping gcsfuse mount"
    echo "   Video merging will use HTTP streaming (Option 2)"
else
    # Try to mount GCS bucket using gcsfuse
    echo "📦 Attempting to mount GCS bucket: $GCS_BUCKET_NAME"

    if command -v gcsfuse &> /dev/null; then
        echo "✓ gcsfuse is installed"

        # Create mount point if it doesn't exist
        mkdir -p /mnt/gcs

        # Mount GCS bucket (with allow_other for container access)
        # --implicit-dirs: Treat folders as directories
        # --file-mode: Permissions for files
        # --dir-mode: Permissions for directories
        # -o allow_other: Allow non-root processes to access
        if gcsfuse --implicit-dirs --file-mode=777 --dir-mode=777 -o allow_other "$GCS_BUCKET_NAME" /mnt/gcs; then
            echo "✅ GCS bucket mounted at /mnt/gcs"
            echo "   FFmpeg will use GCS Fuse for zero-download video merging (Option 1)"
            ls -la /mnt/gcs | head -10
        else
            echo "⚠️  WARNING: gcsfuse mount failed"
            echo "   Video merging will use HTTP streaming fallback (Option 2)"
        fi
    else
        echo "⚠️  WARNING: gcsfuse not found"
        echo "   Video merging will use HTTP streaming (Option 2)"
    fi
fi

echo ""
echo "🚀 Starting FastAPI application..."
echo "========================================="

# Start the FastAPI application
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
