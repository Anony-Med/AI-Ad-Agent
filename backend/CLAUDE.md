# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Ad Agent is an automated AI-powered video ad creation system that transforms scripts into professional video ads using Google's Veo 3.1 API. The system follows a multi-agent pipeline architecture that generates video clips with natural lip-sync, merges them, and enhances them with professional voiceovers.

**Tech Stack:**
- Backend: Python 3.11+ with FastAPI
- Video Generation: Veo 3.1 Direct API (image-to-video with lip-sync)
- Text Generation: Google Gemini 2.0 Flash
- Voice Enhancement: ElevenLabs Voice Changer (Speech-to-Speech)
- Database: Google Cloud Firestore
- Storage: Google Cloud Storage (GCS) + Secret Manager
- Video Processing: ffmpeg
- Authentication: JWT tokens (Unified API pattern)

## Core Development Commands

### Running the Application

```bash
# Start the backend server (from backend/ directory)
python main.py
# Server starts at http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Testing

```bash
# Health check
curl http://localhost:8000/api/ad-agent/health

# Run API tests
cd tests
python test_api.py
```

### GCP Authentication (First Time Setup)

```bash
# Authenticate with GCP
gcloud auth application-default login
gcloud config set project sound-invention-432122-m5
```

### Dependencies

```bash
# Install dependencies
pip install -r requirements.txt

# Verify ffmpeg is installed (required for video processing)
ffmpeg -version
```

## Architecture

### Multi-Agent Pipeline (5-Step Veo-First Workflow)

The system uses a **multi-agent architecture** where specialized agents handle different aspects of video generation:

1. **Prompt Generation** (`PromptGeneratorAgent`) - Gemini 2.0 Flash generates dynamic Veo prompts with movement and actions
2. **Video Generation** (`VideoGeneratorAgent`) - Veo 3.1 creates video clips WITH built-in audio using Direct API
3. **Video Merging** (`VideoCompositorAgent`) - ffmpeg merges clips with frame-to-frame continuity
4. **Voice Enhancement** (`AudioCompositorAgent`) - ElevenLabs enhances voice quality
5. **Final Upload** - GCS storage with signed URLs

**Key File:** `app/ad_agent/pipelines/ad_creation_pipeline.py` (844 lines) orchestrates all agents

### Directory Structure

```
backend/app/
├── ad_agent/                    # Core AI Ad Agent module
│   ├── agents/                  # Specialized agents (6 agents)
│   │   ├── prompt_generator.py  # Gemini prompt generation
│   │   ├── video_generator.py   # Veo video generation
│   │   ├── clip_verifier.py     # Gemini Vision verification
│   │   ├── audio_compositor.py  # ElevenLabs audio processing
│   │   ├── video_compositor.py  # ffmpeg video merging
│   │   └── creative_advisor.py  # Creative suggestions
│   ├── clients/                 # Direct API clients
│   │   ├── gemini_client.py     # Gemini API client
│   │   └── elevenlabs_client.py # ElevenLabs API client
│   ├── pipelines/               # Workflow orchestration
│   │   └── ad_creation_pipeline.py  # Main pipeline (844 lines)
│   ├── interfaces/              # Pydantic schemas
│   │   └── ad_schemas.py        # AdRequest, AdJob, VideoClip, etc.
│   └── utils/                   # Video/audio utilities
│       ├── video_utils.py       # Frame extraction, merging
│       └── audio_utils.py       # Audio analysis
├── services/                    # External service clients
│   ├── unified_api_client.py    # Unified API client
│   └── veo_client.py            # Direct Veo API client
├── database/                    # Data persistence
│   ├── firestore_db.py          # Firestore operations
│   └── gcs_storage.py           # GCS storage with checkpoint/resume
├── routes/                      # API endpoints
│   ├── ad_agent.py              # AI Ad Agent routes
│   ├── auth.py                  # Authentication
│   └── campaigns.py             # Campaign management
├── middleware/                  # Auth middleware
├── models/                      # Shared schemas
├── secrets.py                   # Secret Manager integration
└── config.py                    # Application configuration
```

### Key Architecture Patterns

**1. Multi-Agent Pipeline with Checkpoint/Resume:**
- Each agent is independent and handles one task
- GCS checkpoint system saves all intermediate clips to cloud storage
- Can resume from any failed step (important for timeout recovery)
- See `_save_checkpoint()`, `_load_checkpoint()`, `_recover_existing_clip()` in pipeline

**2. Unified API Pattern for Secret Management:**
- User-specific API keys stored in Secret Manager: `ai_ad_agent_{user_id}_gemini_api_key`
- Falls back to global keys if user doesn't have custom keys
- See `get_user_secret()` in `app/secrets.py` and `get_pipeline()` in `app/routes/ad_agent.py`

**3. Frame-to-Frame Continuity:**
- Each video clip starts from the previous clip's last frame
- Ensures smooth transitions between segments
- Implemented in `VideoGeneratorAgent._extract_last_frame()` and continuity logic

**4. Auto-Retry on Content Policy Failure:**
- If Veo rejects a frame due to content policy, system automatically retries with original avatar
- See retry logic in `ad_creation_pipeline.py` around line 400-500

**5. Background Job Processing:**
- All ad creation jobs run in FastAPI background tasks
- Job status stored in Firestore
- Poll `/api/ad-agent/jobs/{job_id}` for status updates

### Important Workflows

**Creating an Ad (main flow):**
1. Client calls `POST /api/ad-agent/create` with script + character image
2. Endpoint validates campaign and creates pipeline with user-specific API keys
3. Job starts in background task (`pipeline.create_ad()`)
4. Pipeline executes 5-step workflow, saving checkpoints to GCS
5. Each step updates job status in Firestore
6. Client polls `GET /api/ad-agent/jobs/{job_id}` for progress
7. Final video uploaded to GCS with signed URL (valid 7 days)

**Key Implementation Detail - Character Image Handling:**
- Character images stored in GCS (not Firestore) to avoid 1MB document limit
- Base64 images converted to GCS URLs: `{user_id}/{job_id}/character_image.png`
- See character image upload logic in `ad_creation_pipeline.py` lines 263-287

**Verification System (optional):**
- After generating each clip, Gemini Vision verifies it matches the script
- Returns confidence score (0.0-1.0) and visual description
- If score < threshold, can trigger retry (currently just logs warning)
- Enable with `enable_verification=true` and `verification_threshold=0.6` in request

## Configuration

### Environment Variables (.env)

Required variables in `backend/.env`:

```bash
# GCP Configuration
GCP_PROJECT_ID=sound-invention-432122-m5
FIRESTORE_DATABASE=ai-ad-agent
GCS_BUCKET_NAME=ai-ad-agent-videos

# Unified API
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app

# Secret Manager (recommended for production)
USE_SECRET_MANAGER=true

# Development
DEBUG=true
LOG_LEVEL=INFO
```

### Secret Manager Setup

API keys stored in GCP Secret Manager (NOT in code or .env):

```bash
# Global keys (fallback)
unified_api_google_api_key         # Gemini API key
eleven-labs-api-key                # ElevenLabs API key

# User-specific keys (optional)
ai_ad_agent_{user_id}_gemini_api_key
ai_ad_agent_{user_id}_elevenlabs_api_key

# Unified API credentials
ai_ad_agent_unified_api_email
ai_ad_agent_unified_api_password
```

Secret Manager integration is in `app/secrets.py` - uses Google's Secret Manager client with Application Default Credentials (ADC).

### Firestore Database

Database name: `ai-ad-agent`

Collections:
- `users/{user_id}` - User profiles
- `users/{user_id}/campaigns/{campaign_id}` - Campaigns
- `users/{user_id}/jobs/{job_id}` - Ad creation jobs
- `users/{user_id}/assets/{asset_id}` - Generated assets

**Important:** Job documents exclude large fields (video_b64) to stay under Firestore's 1MB limit. Videos stored in GCS.

### GCS Storage

Bucket: `ai-ad-agent-videos`

Structure:
- `{user_id}/{job_id}/character_image.png` - Input character image
- `{user_id}/{job_id}/clips/clip_{i}.mp4` - Individual video clips (checkpoints)
- `{user_id}/{job_id}/merged_video.mp4` - Merged video
- `{user_id}/{job_id}/final_video.mp4` - Final output with audio

All URLs are signed URLs with 7-day expiration.

## Testing

### Manual Testing Scripts

Operational/debug scripts are in `../tools/manual/`:

```bash
# Check job status in Firestore
python ../tools/manual/check_firestore_job.py

# Analyze Veo errors
python ../tools/manual/analyze_veo_error.py

# Kill running servers
python ../tools/manual/kill_python_servers.py

# Check Cloud Run logs
python ../tools/manual/check_cloud_run_logs.py
```

### API Testing Flow

1. Start server: `python main.py`
2. Health check: `curl http://localhost:8000/api/ad-agent/health`
3. Login: `POST /api/auth/login` → get JWT token
4. Create ad: `POST /api/ad-agent/create` with token
5. Monitor: `GET /api/ad-agent/jobs/{job_id}` until status = "completed"
6. Download: Use `final_video_url` from job response

## Common Issues & Solutions

### ffmpeg Not Found

The pipeline requires ffmpeg for video processing. Verify with:

```bash
ffmpeg -version
```

Install if missing:
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows (Conda): `conda install -c conda-forge ffmpeg`

Error appears in logs: "FFmpeg not found - video processing will fail!"

### Firestore 1MB Document Limit

**Problem:** Firestore documents are limited to 1MB, but base64-encoded videos can be 5-10MB+

**Solution (implemented):**
- Character images uploaded to GCS, not stored in Firestore
- Video clips saved to GCS with checkpoint system
- Job documents only store metadata + GCS URLs
- See `_save_job()` in pipeline - excludes `video_b64` field

### Content Policy Failures

Veo's safety filters may reject certain prompts/images. The system automatically retries with the original avatar image if a frame is rejected.

Look for logs: "Content policy failure, retrying with original avatar..."

### Secret Manager Permissions

If you see "Failed to load secrets from Secret Manager", ensure the service account has these roles:
- `roles/secretmanager.secretAccessor`
- `roles/iam.serviceAccountUser`

### Authentication Issues

The system uses JWT tokens from Unified API. If you get 401 errors:
1. Check token is valid: `GET /api/auth/me` with Bearer token
2. Verify token hasn't expired (default: 1440 minutes)
3. Re-authenticate: `POST /api/auth/login`

## Development Patterns

### Adding a New Agent

1. Create file in `app/ad_agent/agents/`
2. Inherit from base pattern (see existing agents)
3. Implement main processing method (e.g., `generate()`, `process()`)
4. Add to pipeline in `ad_creation_pipeline.py`
5. Update status enum in `ad_schemas.py` if needed

### Adding a New Pipeline Step

1. Add status to `AdJobStatus` enum in `ad_schemas.py`
2. Implement step in `AdCreationPipeline.create_ad()`
3. Update progress tracking (0-100%)
4. Save checkpoint to GCS if generating large artifacts
5. Update job in Firestore: `await self._save_job(job)`
6. Add error handling with try/except

### Working with Video Files

Use `VideoProcessor` utility class (in `app/ad_agent/utils/video_utils.py`):

```python
from app.ad_agent.utils.video_utils import VideoProcessor

# Extract last frame for continuity
last_frame = VideoProcessor.extract_last_frame(video_path)

# Merge multiple clips
merged_path = VideoProcessor.merge_clips(clip_paths, output_path)

# Check video duration
duration = VideoProcessor.get_duration(video_path)
```

Always cleanup temp files after processing.

### Logging Best Practices

The app uses rotating file logs (10MB max, 5 backups) in `logs/ai_ad_agent.log`.

Include job_id in all logs for debugging:
```python
logger.info(f"[{job.job_id}] Starting step 2: Video generation")
logger.error(f"[{job.job_id}] Video generation failed: {error}")
```

## Deployment

### Cloud Run Deployment

```bash
# Build and submit
gcloud builds submit --tag gcr.io/sound-invention-432122-m5/ai-ad-agent

# Deploy
gcloud run deploy ai-ad-agent \
  --image gcr.io/sound-invention-432122-m5/ai-ad-agent \
  --platform managed \
  --region europe-west1 \
  --service-account=994684344365-compute@developer.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=sound-invention-432122-m5
```

No need to pass API keys - they're loaded from Secret Manager automatically via ADC.

### Important Notes for Production

- Ensure ffmpeg is in Docker image (see Dockerfile)
- Set USE_SECRET_MANAGER=true
- Configure service account with Secret Manager access
- Set appropriate timeouts (video generation can take 3-5 minutes per clip)
- Consider using Cloud Tasks for long-running jobs instead of background tasks

## Additional Resources

- **Main Documentation:** `../README.md` - comprehensive setup and usage guide
- **Setup Guide:** `../docs/SETUP_COMPLETE.md` - detailed setup instructions
- **API Documentation:** `http://localhost:8000/docs` (when running) - interactive OpenAPI docs
- **Architecture Reference:** `../docs/VIMAX_REFERENCE.md` - multi-agent architecture patterns
- **Feature Docs:** `../docs/` directory has feature-specific documentation

## Key Takeaways for Development

1. **All video artifacts go through GCS** - never store large files in Firestore
2. **Always use user-specific API keys** when available, fall back to global
3. **Pipeline is designed for resume** - any step can be recovered from GCS checkpoints
4. **Background jobs need polling** - client must poll job status, no webhooks yet
5. **ffmpeg is required** - pipeline will fail immediately if ffmpeg not found
6. **Frame-to-frame continuity is critical** - each clip must start from previous clip's last frame
7. **Logs are your friend** - comprehensive logging in `logs/ai_ad_agent.log` with job IDs
