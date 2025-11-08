# AI Ad Agent

**Automated AI-powered video ad creation system** that transforms scripts into professional video ads with clip verification.

## 🎯 What Does It Do?

Submit a script and character image → Get a complete, polished video ad with voice, music, and effects.

**Fully automated 9-step workflow:**
1. ✅ Generates optimized Veo 3.1 prompts + script segments (Gemini)
2. ✅ Creates 7-second video clips with character consistency (Veo 3.1)
3. ✅ **Verifies clips match script content (Gemini Vision)** 🆕
4. ✅ Merges clips seamlessly (ffmpeg)
5. ✅ Provides creative enhancement suggestions (Gemini)
6. ✅ Generates voiceover for entire script (ElevenLabs - your chosen voice)
7. ✅ Replaces video audio with consistent voiceover (ffmpeg)
8. ✅ Adds background music and sound effects (ElevenLabs)
9. ✅ Exports and uploads final video (GCS)

## 📊 Tech Stack

- **Backend:** Python FastAPI
- **Authentication:** Unified API (JWT tokens)
- **Database:** Google Cloud Firestore
- **Storage:** Google Cloud Storage + Secret Manager
- **Video Generation:** Veo 3.1 via [Unified API](https://unified-api-interface-994684344365.europe-west1.run.app)
- **Text/Vision:** Google Gemini 2.0 Flash (direct API)
- **Audio Generation:** ElevenLabs (direct API)
- **Video Processing:** ffmpeg
- **Architecture:** ViMax-style multi-agent pipeline

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Python 3.11+
python --version

# ffmpeg (required for video merging)
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
choco install ffmpeg
```

### 2. Installation

```bash
cd backend

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

#### Option A: Local Development (Using .env file)

Create `backend/.env`:

```env
# GCP Configuration
GCP_PROJECT_ID=sound-invention-432122-m5
GCS_BUCKET_NAME=your-bucket-name

# Required API Keys (for local dev only)
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Unified API (already configured)
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app

# Optional
DEBUG=True
LOG_LEVEL=INFO
```

**Get API Keys:**
- **Gemini:** https://makersuite.google.com/app/apikey
- **ElevenLabs:** https://elevenlabs.io/ → Profile → API Keys

#### Option B: Production (Using Secret Manager)

For production deployment, use GCP Secret Manager:

```bash
# Set project
export PROJECT_ID="sound-invention-432122-m5"

# Create global secrets
echo -n "YOUR_GEMINI_KEY" | gcloud secrets create ai_ad_agent_gemini_api_key \
  --project=$PROJECT_ID --replication-policy="automatic" --data-file=-

echo -n "YOUR_ELEVENLABS_KEY" | gcloud secrets create ai_ad_agent_elevenlabs_api_key \
  --project=$PROJECT_ID --replication-policy="automatic" --data-file=-

# Grant service account access
export SA="994684344365-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding ai_ad_agent_gemini_api_key \
  --member="serviceAccount:${SA}" --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding ai_ad_agent_elevenlabs_api_key \
  --member="serviceAccount:${SA}" --role="roles/secretmanager.secretAccessor"
```

See [docs/SECRET_MANAGER_SETUP.md](./docs/SECRET_MANAGER_SETUP.md) for detailed setup instructions.

### 4. Run the Application

```bash
cd backend
python main.py

# Server starts at http://localhost:8000
# API Docs: http://localhost:8000/docs
# Health Check: http://localhost:8000/api/ad-agent/health
```

## 🧪 Testing Guide

### Step 1: Verify Installation

```bash
# Test health endpoint
curl http://localhost:8000/api/ad-agent/health

# Expected response:
# {
#   "status": "healthy",
#   "gemini_configured": true,
#   "elevenlabs_configured": true,
#   "unified_api_url": "https://unified-api-interface-994684344365.europe-west1.run.app"
# }
```

### Step 2: Register/Login

```bash
# Register a new user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123",
    "name": "Test User"
  }'

# Or login with existing user
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123"
  }'

# Save the access token from response
export TOKEN="your_access_token_here"
```

### Step 3: Create a Campaign

```bash
# Create a campaign
curl -X POST http://localhost:8000/api/campaigns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Campaign",
    "platform": "instagram",
    "ad_type": "video",
    "aspect_ratio": "16:9"
  }'

# Save the campaign_id from response
export CAMPAIGN_ID="campaign_id_from_response"
```

### Step 4: Prepare Character Image

```bash
# Encode your character image to base64
# macOS/Linux:
export CHARACTER_IMAGE=$(base64 -i your_character.jpg)

# Windows (PowerShell):
# $CHARACTER_IMAGE = [Convert]::ToBase64String([IO.File]::ReadAllBytes("your_character.jpg"))

# Or use a small test image URL
# You can download: https://i.imgur.com/example.jpg
```

### Step 5: Create Your First Ad

```bash
# Create ad with full workflow
curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"campaign_id\": \"$CAMPAIGN_ID\",
    \"script\": \"Looking for your dream home? I specialize in luxury properties. Let me help you find the perfect place.\",
    \"character_image\": \"$CHARACTER_IMAGE\",
    \"character_name\": \"Heather\",
    \"voice_id\": \"pNInz6obpgDQGcFmaJgB\",
    \"background_music_prompt\": \"upbeat inspiring corporate music\",
    \"add_sound_effects\": true,
    \"aspect_ratio\": \"16:9\",
    \"resolution\": \"1080p\",
    \"enable_verification\": true,
    \"verification_threshold\": 0.6
  }"

# Save the job_id from response
export JOB_ID="job_id_from_response"
```

### Step 6: Monitor Progress

```bash
# Check job status
curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq

# Watch progress in real-time (requires jq and watch)
watch -n 10 "curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID -H 'Authorization: Bearer $TOKEN' | jq '.status, .progress, .current_step'"

# Or manually check every 30 seconds
while true; do
  curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
    -H "Authorization: Bearer $TOKEN" | jq '.status, .progress, .current_step'
  sleep 30
done
```

**Status progression:**
- `pending` → `generating_prompts` → `generating_videos` → `verifying_clips` → `merging_videos` → `getting_suggestions` → `enhancing_voice` → `adding_audio` → `finalizing` → `completed`

### Step 7: Download Final Video

```bash
# Once status is "completed", download the video
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID/download \
  -H "Authorization: Bearer $TOKEN" \
  -L -o my_ad.mp4

# Play the video
# macOS:
open my_ad.mp4

# Linux:
xdg-open my_ad.mp4

# Windows:
start my_ad.mp4
```

### Step 8: Test Prompt Generation Only

```bash
# Test just the prompt generation (no video creation)
curl -X POST http://localhost:8000/api/ad-agent/test/prompts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "Looking for your dream home? I can help you find it.",
    "character_name": "Heather"
  }'

# Response shows generated Veo prompts and script segments
```

## 📖 Documentation

### Core Documentation

- **[docs/IMPLEMENTATION_SUMMARY.md](./docs/IMPLEMENTATION_SUMMARY.md)** - Complete feature overview
- **[docs/AI_AD_AGENT_README.md](./docs/AI_AD_AGENT_README.md)** - Technical documentation
- **[docs/EXAMPLE_USAGE.md](./docs/EXAMPLE_USAGE.md)** - Step-by-step examples (curl & Python)

### Setup & Configuration

- **[docs/SECRET_MANAGER_SETUP.md](./docs/SECRET_MANAGER_SETUP.md)** - Secret Manager setup guide
- **[docs/AUTH_AND_SECRETS_FLOW.md](./docs/AUTH_AND_SECRETS_FLOW.md)** - Authentication & secrets flow
- **[docs/UNIFIED_API_INTEGRATION.md](./docs/UNIFIED_API_INTEGRATION.md)** - Unified API integration details

### Feature Documentation

- **[docs/CLIP_VERIFICATION.md](./docs/CLIP_VERIFICATION.md)** - Clip verification system
- **[docs/VOICE_WORKFLOW_FIX.md](./docs/VOICE_WORKFLOW_FIX.md)** - Voice workflow details

### Reference

- **[docs/VIMAX_REFERENCE.md](./docs/VIMAX_REFERENCE.md)** - Architecture patterns reference
- **[docs/CLEANUP_SUMMARY.md](./docs/CLEANUP_SUMMARY.md)** - Codebase cleanup summary

### Interactive API Docs

- **OpenAPI:** http://localhost:8000/docs (when running)
- **ReDoc:** http://localhost:8000/redoc (when running)

## 🏗️ Project Structure

```
ai-ad-agent/
├── backend/                          # Main application
│   ├── app/
│   │   ├── ad_agent/                # AI Ad Agent module
│   │   │   ├── agents/              # Specialized agents
│   │   │   │   ├── prompt_generator.py    # Step 1: Generate prompts
│   │   │   │   ├── video_generator.py     # Step 2: Generate videos
│   │   │   │   ├── clip_verifier.py       # Step 3: Verify clips 🆕
│   │   │   │   ├── creative_advisor.py    # Step 5: Suggestions
│   │   │   │   ├── audio_compositor.py    # Step 6-8: Audio
│   │   │   │   └── video_compositor.py    # Step 4,7,9: Video
│   │   │   ├── clients/             # Direct API clients
│   │   │   │   ├── gemini_client.py       # Gemini text + vision
│   │   │   │   └── elevenlabs_client.py   # ElevenLabs audio
│   │   │   ├── pipelines/           # Orchestration
│   │   │   │   └── ad_creation_pipeline.py  # Main workflow
│   │   │   ├── interfaces/          # Schemas
│   │   │   │   └── ad_schemas.py
│   │   │   └── utils/               # Video processing
│   │   │       └── video_utils.py
│   │   ├── routes/                  # API endpoints
│   │   │   ├── ad_agent.py         # AI Ad Agent routes
│   │   │   ├── auth.py             # Authentication
│   │   │   ├── campaigns.py        # Campaign management
│   │   │   └── ...
│   │   ├── database/                # Firestore & GCS
│   │   ├── services/                # Unified API client
│   │   ├── middleware/              # Auth middleware
│   │   ├── models/                  # Schemas & enums
│   │   └── secrets.py               # Secret Manager 🆕
│   ├── main.py                      # FastAPI app
│   └── requirements.txt
├── docs/                            # Documentation 📁
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── SECRET_MANAGER_SETUP.md
│   ├── CLIP_VERIFICATION.md
│   └── ...
└── README.md                        # This file
```

## 🔑 API Endpoints

### AI Ad Agent

- `POST /api/ad-agent/create` - Create ad (starts 9-step workflow)
- `GET /api/ad-agent/jobs/{job_id}` - Check job status & verification results
- `GET /api/ad-agent/jobs/{job_id}/download` - Download final video
- `POST /api/ad-agent/test/prompts` - Test prompt generation
- `GET /api/ad-agent/health` - Health check

### Authentication (Unified API)

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login (get JWT token)
- `GET /api/auth/me` - Get current user info

### Campaign Management

- `POST /api/campaigns` - Create campaign
- `GET /api/campaigns` - List campaigns
- `GET /api/campaigns/{id}` - Get campaign details

### Other Endpoints

- `POST /api/generate/video` - Generate single video (Veo, Sora, Kling)
- `GET /api/assets` - List generated assets
- `GET /api/billing/usage` - Usage statistics

## 📈 Timeline

Typical ad creation takes **7-14 minutes**:

| Step | Duration | Description |
|------|----------|-------------|
| 1. Prompt Generation | 10-30s | Gemini analyzes script + creates segments |
| 2. Video Generation | 5-10 min | Veo 3.1 generates 3 clips |
| 3. Clip Verification | 30-60s | Gemini Vision verifies clips 🆕 |
| 4. Video Merging | 30-60s | ffmpeg concatenation |
| 5. Creative Suggestions | 10-20s | Gemini enhancement ideas |
| 6. Voiceover | 30-60s | ElevenLabs TTS |
| 7. Audio Replacement | 10-20s | ffmpeg audio swap |
| 8. Music & SFX | 1-2 min | ElevenLabs audio generation |
| 9. Final Upload | 30s | GCS upload |
| **Total** | **7-14 min** | Complete workflow |

## 💰 Cost Estimate

Approximate cost per ad:

| Service | Usage | Cost |
|---------|-------|------|
| Gemini (text) | Prompts + suggestions | ~$0.01 |
| Gemini (vision) | 3 clip verifications | ~$0.006 |
| Veo 3.1 | 3 clips × 7s | ~$0.30 |
| ElevenLabs | Voice + music + SFX | ~$0.05 |
| GCS | Storage + bandwidth | ~$0.01 |
| **Total** | Per ad | **~$0.38** |

## 🆕 New Features

### Clip-to-Script Verification

Ensures generated clips match the script content:

```json
{
  "enable_verification": true,
  "verification_threshold": 0.7
}
```

**What it does:**
- Uses Gemini Vision to analyze each generated clip
- Compares visual content against script segment
- Returns confidence score (0.0-1.0)
- Example: Script says "leaky roofs" → checks if roofs are visible

**Verification results:**
```json
{
  "verification": {
    "verified": true,
    "confidence_score": 0.85,
    "visual_description": "Shows professional woman at modern house entrance",
    "alignment_feedback": "Excellent match - visual aligns with script"
  }
}
```

See [docs/CLIP_VERIFICATION.md](./docs/CLIP_VERIFICATION.md) for details.

### User-Specific API Keys

Each user can have their own API keys via Secret Manager:

```
User Login → JWT with user_id → Load user's API keys → Use for generation
```

**Secret naming:**
- `ai_ad_agent_{user_id}_gemini_api_key`
- `ai_ad_agent_{user_id}_elevenlabs_api_key`

Falls back to global keys if user doesn't have custom keys.

See [docs/AUTH_AND_SECRETS_FLOW.md](./docs/AUTH_AND_SECRETS_FLOW.md) for details.

## 🐛 Troubleshooting

### ffmpeg Not Found

```bash
# Install ffmpeg first
sudo apt-get install ffmpeg  # Ubuntu/Debian
brew install ffmpeg          # macOS
choco install ffmpeg         # Windows
```

### API Key Errors

```bash
# Check if keys are configured
curl http://localhost:8000/api/ad-agent/health

# Should show:
# "gemini_configured": true
# "elevenlabs_configured": true
```

If `false`, either:
1. Add keys to `.env` file (local dev)
2. Create secrets in Secret Manager (production)

### Authentication Errors

```bash
# If you get 401 Unauthorized, your token may have expired
# Login again to get a new token
curl -X POST http://localhost:8000/api/auth/login \
  -d '{"email": "your@email.com", "password": "your_password"}'
```

### Job Stuck or Failed

```bash
# Check detailed job status
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq

# Check individual clip statuses
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.video_clips'

# Check verification results
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.video_clips[].verification'
```

### Verification Always Fails

If all clips fail verification:
- Lower threshold: `"verification_threshold": 0.5`
- Or disable: `"enable_verification": false`

## 🚀 Deployment

### Deploy to Google Cloud Run

```bash
# Build
gcloud builds submit --tag gcr.io/sound-invention-432122-m5/ai-ad-agent

# Deploy (secrets loaded from Secret Manager automatically)
gcloud run deploy ai-ad-agent \
  --image gcr.io/sound-invention-432122-m5/ai-ad-agent \
  --platform managed \
  --region europe-west1 \
  --service-account=994684344365-compute@developer.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=sound-invention-432122-m5
```

No need to set API keys in environment - they're loaded from Secret Manager!

See [docs/SECRET_MANAGER_SETUP.md](./docs/SECRET_MANAGER_SETUP.md) for production setup.

## 🎯 Use Cases

- **Real Estate Ads** - Property showcase videos with agent narration
- **Product Ads** - Product demonstrations with voiceover
- **Social Media Ads** - Instagram, TikTok, YouTube shorts
- **Corporate Videos** - Company introductions, team highlights
- **Promotional Videos** - Event promotions, announcements
- **Educational Content** - Tutorial videos, explainers

## 🔮 Roadmap

- [ ] **Automatic clip retry** - Re-generate failed clips with adjusted prompts
- [ ] **User secret management UI** - Let users input their own API keys
- [ ] **Text overlay engine** - Programmatic text animations
- [ ] **Multiple variations** - A/B testing with different styles
- [ ] **Video templates library** - Pre-designed templates
- [ ] **Batch processing** - Generate multiple ads at once
- [ ] **Analytics integration** - Track ad performance
- [ ] **Webhook notifications** - Real-time job completion alerts

## 📄 License

MIT License

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📞 Support

- **Documentation:** See [docs/](./docs/) directory
- **API Docs:** http://localhost:8000/docs
- **Issues:** GitHub Issues

---

**Built with:**
- ViMax-inspired multi-agent architecture
- Unified API for seamless video generation & authentication
- GCP Secret Manager for secure key storage
- Gemini Vision for clip verification
- FastAPI for modern, async API design
