# AI Ad Agent

**Automated AI-powered video ad creation system** that transforms scripts into professional video ads using Direct Veo API.

## 🎯 What Does It Do?

Submit a script and character image → Get a complete, polished video ad with natural lip-sync and voice.

**Simplified 5-step Veo-First workflow:**
1. ✅ Generates **DYNAMIC** Veo prompts with movement and actions (Gemini 2.0 Flash)
2. ✅ Creates video clips WITH built-in audio using Direct Veo API (Veo 3.1 image-to-video)
3. ✅ Merges clips with frame-to-frame continuity (ffmpeg)
4. ✅ Enhances voice quality with ElevenLabs Voice Changer (Speech-to-Speech API)
5. ✅ Exports and uploads final video with signed URLs (GCS)

**Key Features (Latest):**
- 🎬 **Dynamic Movement** - Characters move, gesture, and demonstrate (not static!)
- 🎯 **Exact Script Usage** - Uses your exact words without modification
- 🔄 **Frame-to-Frame Continuity** - Each clip starts from previous clip's last frame
- 🛡️ **Auto-Retry on Failure** - Falls back to original avatar if content policy fails
- 🔧 **Script Normalization** - Auto-converts special characters (—, "", '') to prevent gibberish
- 📊 **Real-Time Progress** - Step-by-step monitoring with detailed logs
- 💾 **GCS Checkpoint System** - All clips saved to cloud storage for resume/replay

## 📊 Tech Stack

- **Backend:** Python FastAPI
- **Authentication:** Unified API (JWT tokens)
- **Database:** Google Cloud Firestore
- **Storage:** Google Cloud Storage + Secret Manager
- **Video Generation:** Veo 3.1 **Direct API** (image-to-video with lip-sync) 🆕
- **Text Generation:** Google Gemini 2.0 Flash (direct API)
- **Voice Enhancement:** ElevenLabs Voice Changer (direct API) 🆕
- **Video Processing:** ffmpeg
- **Architecture:** Multi-agent pipeline with sequential clip processing

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

# Windows (Conda recommended)
conda install -c conda-forge ffmpeg

# OR Windows (Chocolatey)
choco install ffmpeg
```

### 2. Installation

```bash
cd backend

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

#### GCP Authentication (First Time Setup)

```bash
# Authenticate with GCP
gcloud auth application-default login
gcloud config set project sound-invention-432122-m5
```

#### Configure API Keys in Secret Manager

All API keys are stored in GCP Secret Manager (shared with Unified API infrastructure):

```bash
# 1. Gemini API Key (for prompts, suggestions, verification)
echo -n "YOUR_GEMINI_KEY" | gcloud secrets create unified_api_google_api_key \
  --project=sound-invention-432122-m5 --replication-policy="automatic" --data-file=-

# 2. ElevenLabs API Key (for voiceover, music, SFX)
echo -n "YOUR_ELEVENLABS_KEY" | gcloud secrets create eleven-labs-api-key \
  --project=sound-invention-432122-m5 --replication-policy="automatic" --data-file=-

# 3. GCS Service Account (for signed URLs)
# This should already exist from Unified API setup
# If not, see SETUP_COMPLETE.md

# 4. Unified API Credentials (for Veo video generation)
# Add your Unified API login credentials
echo -n "your-email@example.com" | gcloud secrets create ai_ad_agent_unified_api_email \
  --project=sound-invention-432122-m5 --replication-policy="automatic" --data-file=-

echo -n "your-password" | gcloud secrets create ai_ad_agent_unified_api_password \
  --project=sound-invention-432122-m5 --replication-policy="automatic" --data-file=-
```

**Get API Keys:**
- **Gemini:** https://aistudio.google.com/app/apikey
- **ElevenLabs:** https://elevenlabs.io/ → Profile → API Keys
- **Unified API:** Use your existing Unified API account credentials

**Alternative:** You can also use the quick setup script:
```bash
# See docs/QUICK_AUTH_SETUP.md for instructions
```

#### Backend Configuration

Create `backend/.env`:

```env
# GCP Configuration
GCP_PROJECT_ID=sound-invention-432122-m5
FIRESTORE_DATABASE=ai-ad-agent
GCS_BUCKET_NAME=ai-ad-agent-videos

# Unified API
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app

# Secret Manager (recommended for production)
USE_SECRET_MANAGER=true

# Optional - Local Development Only
DEBUG=true
LOG_LEVEL=INFO
```

See [docs/SETUP_COMPLETE.md](./docs/SETUP_COMPLETE.md) for detailed setup documentation.

### 4. Run the Application

```bash
cd backend
python main.py

# Server starts at http://localhost:8000
# API Docs: http://localhost:8000/docs
# Health Check: http://localhost:8000/api/ad-agent/health
```

## 🧪 Testing

For comprehensive testing instructions, see **[docs/TEST_README.md](./docs/TEST_README.md)**.

### Quick Health Check

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

For complete testing steps including authentication, campaign creation, and ad generation, see **[docs/TEST_README.md](./docs/TEST_README.md)**.

## 🎬 How to Create Your First Ad

### Step-by-Step Guide

#### 1. Prepare Your Assets

**Avatar Image:**
- Use a clear image of your character (PNG, JPG)
- Recommended: 512x512 or 1024x1024 resolution
- Place in project root or note the full path
- Example: `C:\Users\shrey\Desktop\projects\ai ad agent\Avatar.png`

**Script:**
- Write your ad script (what your character will say)
- Keep it natural and conversational
- Example length: 30-60 seconds of speech (~100-200 words)
- Avoid special characters (em dashes —, curly quotes "", etc.)

#### 2. Option A: Using the Test Script (Easiest)

**Step 1:** Edit `run_ad.py` in the project root:

```python
# 1. UPDATE SCRIPT - Replace with your own script
script = """
Your custom script here.
Write what you want the character to say.
Each paragraph will become a video segment.
"""

# 2. UPDATE AVATAR PATH - Point to your avatar image
avatar_path = r"C:\path\to\your\Avatar.png"

# 3. OPTIONAL: Customize voice
# Leave as None to use default "Heather Bryant" voice
# Or specify voice_id from ElevenLabs
voice_id = None  # or "voice_id_here"

# 4. OPTIONAL: Customize settings
aspect_ratio = "16:9"  # or "9:16" for vertical
resolution = "720p"    # or "1080p"
```

**Step 2:** Start the backend server:

```bash
cd backend
python main.py
# Server starts at http://localhost:8001
```

**Step 3:** Run the test script (in a new terminal):

```bash
python run_ad.py
```

**Step 4:** Monitor the progress:

The script will show:
- Job ID
- Step-by-step progress (1/5 → 2/5 → ... → 5/5)
- Status updates
- Final video URL when complete

**Step 5:** Get your video:

When complete, you'll see:
```
✅ Ad creation COMPLETED!
📹 Final Video: https://storage.googleapis.com/ai-ad-agent-videos/...
```

Click the URL to download your video!

#### 3. Option B: Using API Directly (Advanced)

**Step 1:** Convert your avatar to base64:

```python
import base64

# Read your avatar image
with open(r"C:\path\to\your\Avatar.png", "rb") as f:
    avatar_bytes = f.read()

# Convert to base64
avatar_b64 = base64.b64encode(avatar_bytes).decode('utf-8')

# Add data URI prefix
avatar_data_uri = f"data:image/png;base64,{avatar_b64}"

print(f"Avatar ready: {len(avatar_b64)} characters")
```

**Step 2:** Login to get authentication token:

```bash
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ad_agent","password":"agent1234"}'

# Save the "access_token" from response
```

**Step 3:** Create your ad:

```bash
curl -X POST http://localhost:8001/api/ad-agent/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "campaign_id": "my-campaign",
    "script": "Your ad script here. What your character will say.",
    "character_image": "data:image/png;base64,YOUR_BASE64_HERE",
    "character_name": "Your Character Name",
    "voice_id": null,
    "aspect_ratio": "16:9",
    "resolution": "720p"
  }'

# Save the "job_id" from response
```

**Step 4:** Check job status:

```bash
curl http://localhost:8001/api/ad-agent/jobs/YOUR_JOB_ID \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Step 5:** Download your video:

When status is "completed", use the `final_video_url` from the response.

### 📝 Tips for Best Results

**Script Writing:**
- ✅ **Use plain text only** - Avoid fancy quotes, em dashes, special characters
- ✅ **Natural flow** - Write like you're speaking, not reading
- ✅ **Break into segments** - Each paragraph becomes a video segment
- ✅ **Action hints** - Mention what to show ("at the house", "pointing to features")
- ❌ **Avoid** - Technical jargon, overly complex sentences, special symbols

**Avatar Image:**
- ✅ **Clear subject** - Character should be clearly visible and centered
- ✅ **Good lighting** - Well-lit image without harsh shadows
- ✅ **Neutral background** - Less distraction, better compositing
- ✅ **Professional quality** - Higher resolution = better results
- ❌ **Avoid** - Blurry images, busy backgrounds, multiple people

**Example Good Script:**
```
Tired of dealing with property repairs after every storm?

Hi, I'm Sarah with Quick Home Solutions - helping homeowners sell as-is.

No repairs needed. No waiting months. No stress.

Whether you're relocating, downsizing, or just ready for a change - you deserve a simple process.

Call us today and get a fair cash offer in 24 hours.
```

### 🎯 What Happens During Execution

When you run `python run_ad.py`, the system goes through 5 steps:

**Step 1: Generating Prompts (10-30 seconds)**
- Gemini AI analyzes your script
- Creates dynamic video prompts with movement and actions
- Segments script into clips (~7 seconds each)
- Example: "walking toward camera", "gesturing at house"

**Step 2: Generating Videos (3-5 minutes)**
- Veo 3.1 generates video clips with lip-sync
- Uses your avatar image as starting point
- Each clip continues from the previous one (frame-to-frame continuity)
- Character speaks your script with natural movements

**Step 3: Merging Videos (10-30 seconds)**
- All clips are combined into one seamless video
- Smooth transitions between segments
- No gaps or cuts

**Step 4: Voice Enhancement (30-60 seconds)**
- ElevenLabs enhances the voice quality
- Applies professional voice (default: "Heather Bryant")
- Replaces audio track in merged video

**Step 5: Finalize (10-20 seconds)**
- Uploads final video to Google Cloud Storage
- Generates signed URL (valid for 7 days)
- Creates asset record in database

**Total Time: ~4-6 minutes**

### ⚠️ Common Issues & Solutions

**Issue:** "Unknown encoder 'libmp3lame'"
```bash
# Solution: Install ffmpeg
# Windows (Conda):
conda install -c conda-forge ffmpeg

# Windows (Chocolatey):
choco install ffmpeg

# Mac:
brew install ffmpeg

# Linux:
sudo apt-get install ffmpeg
```

**Issue:** "Clip generation failed due to content policy"
- **Why:** Veo's safety filter rejected the frame
- **Solution:** System automatically retries with original avatar
- **If persists:** Try a different avatar image with neutral background

**Issue:** "Voice 'Heather Bryant' not found"
- **Why:** Voice not available in your ElevenLabs account
- **Solution:**
  1. Use `voice_id=None` to use default voice
  2. Or get voice ID from ElevenLabs and use `voice_id="your_voice_id"`

**Issue:** "Script has gibberish speech"
- **Why:** Special characters (—, "", '') causing encoding issues
- **Solution:** Use plain text only (-, ", ')
- **Auto-fixed:** System now normalizes scripts automatically

**Issue:** "Character doesn't move/stays still"
- **Why:** Prompts not emphasizing movement
- **Fixed:** System now generates dynamic prompts with action words

### Test Scripts

The `tests/` folder contains helper scripts for testing:

```bash
# Create a test ad
python tests/create_test_ad.py

# Monitor ad creation progress
python tests/monitor_progress.py

# Setup Unified API authentication
python tests/setup_unified_api_auth.py

# Install ffmpeg (Windows)
python tests/install_ffmpeg.py

# Create service account for GCS
python tests/create_service_account.py
```

## 📖 Documentation

### Getting Started

- **[docs/TEST_README.md](./docs/TEST_README.md)** - Step-by-step testing guide 🆕
- **[docs/SETUP_COMPLETE.md](./docs/SETUP_COMPLETE.md)** - Setup status and configuration
- **[docs/QUICK_AUTH_SETUP.md](./docs/QUICK_AUTH_SETUP.md)** - Quick authentication setup
- **[docs/setup_local_dev.md](./docs/setup_local_dev.md)** - Local development setup

### Core Documentation

- **[docs/IMPLEMENTATION_SUMMARY.md](./docs/IMPLEMENTATION_SUMMARY.md)** - Complete feature overview
- **[docs/AI_AD_AGENT_README.md](./docs/AI_AD_AGENT_README.md)** - Technical documentation
- **[docs/EXAMPLE_USAGE.md](./docs/EXAMPLE_USAGE.md)** - Step-by-step examples (curl & Python)

### Setup & Configuration

- **[docs/SECRET_MANAGER_SETUP.md](./docs/SECRET_MANAGER_SETUP.md)** - Secret Manager setup guide
- **[docs/AUTH_AND_SECRETS_FLOW.md](./docs/AUTH_AND_SECRETS_FLOW.md)** - Authentication & secrets flow
- **[docs/UNIFIED_API_INTEGRATION.md](./docs/UNIFIED_API_INTEGRATION.md)** - Unified API integration details

### Feature Documentation

- **[docs/AUDIO_FIRST_WORKFLOW.md](./docs/AUDIO_FIRST_WORKFLOW.md)** - Audio-first workflow details 🆕
- **[docs/LOGO_OVERLAY_FEATURE.md](./docs/LOGO_OVERLAY_FEATURE.md)** - Logo overlay guide 🆕
- **[docs/CLIP_VERIFICATION.md](./docs/CLIP_VERIFICATION.md)** - Clip verification system
- **[docs/VOICE_WORKFLOW_FIX.md](./docs/VOICE_WORKFLOW_FIX.md)** - Voice workflow details
- **[docs/CHECKPOINT_RESUME_IMPLEMENTATION.md](./docs/CHECKPOINT_RESUME_IMPLEMENTATION.md)** - Checkpoint/resume system 🆕

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
│   │   │   │   ├── prompt_generator.py    # Gemini prompt generation (dynamic prompts) 🆕
│   │   │   │   ├── video_generator.py     # Veo video generation (Direct API) 🆕
│   │   │   │   ├── clip_verifier.py       # Gemini Vision verification
│   │   │   │   ├── creative_advisor.py    # Creative suggestions
│   │   │   │   ├── audio_compositor.py    # ElevenLabs audio (Voice Changer) 🆕
│   │   │   │   └── video_compositor.py    # ffmpeg video processing
│   │   │   ├── clients/             # Direct API clients
│   │   │   │   ├── gemini_client.py       # Gemini text + vision (dynamic prompts) 🆕
│   │   │   │   └── elevenlabs_client.py   # ElevenLabs audio (Speech-to-Speech) 🆕
│   │   │   ├── pipelines/           # Orchestration
│   │   │   │   └── ad_creation_pipeline.py  # 5-step workflow with retry logic 🆕
│   │   │   ├── interfaces/          # Schemas
│   │   │   │   └── ad_schemas.py          # Updated with GCS URLs
│   │   │   └── utils/               # Video processing
│   │   │       ├── video_utils.py         # Frame extraction, merging
│   │   │       ├── audio_utils.py         # Audio analysis 🆕
│   │   │       └── image_utils.py         # Image optimization 🆕
│   │   ├── routes/                  # API endpoints
│   │   │   ├── ad_agent.py         # AI Ad Agent routes
│   │   │   ├── auth.py             # Authentication
│   │   │   ├── campaigns.py        # Campaign management
│   │   │   └── ...
│   │   ├── database/                # Firestore & GCS
│   │   │   ├── firestore_db.py     # Uses ADC (no explicit keys)
│   │   │   └── gcs_storage.py      # GCS checkpoint/resume 🆕
│   │   ├── services/                # External services
│   │   │   ├── unified_api_client.py      # Unified API client
│   │   │   └── veo_client.py              # Direct Veo API client 🆕
│   │   ├── middleware/              # Auth middleware
│   │   ├── models/                  # Schemas & enums
│   │   ├── secrets.py               # Secret Manager
│   │   └── config.py                # App configuration
│   ├── main.py                      # FastAPI app
│   └── requirements.txt
├── docs/                            # Documentation 📁
│   ├── TEST_README.md              # Comprehensive testing guide
│   ├── SETUP_COMPLETE.md           # Setup status
│   ├── QUICK_AUTH_SETUP.md         # Quick auth setup
│   ├── VEO_FIRST_WORKFLOW.md       # Veo-first workflow details 🆕
│   ├── DIRECT_VEO_MIGRATION.md     # Direct Veo API migration 🆕
│   ├── CHECKPOINT_RESUME_IMPLEMENTATION.md  # Checkpoint system
│   ├── LOGO_OVERLAY_FEATURE.md     # Logo overlay guide
│   ├── OLD_CODE_ARCHIVE.md         # Archived workflows
│   └── ...
├── tests/                           # Testing scripts 📁
│   ├── create_test_ad.py           # Create test ad
│   ├── monitor_progress.py         # Monitor job progress
│   ├── setup_unified_api_auth.py   # Setup Unified API auth
│   ├── install_ffmpeg.py           # Install ffmpeg (Windows)
│   ├── create_service_account.py   # Create GCS service account
│   └── test_setup.py               # Backend setup tests
├── run_ad.py                        # ⭐ Quick test script (easiest way to start) 🆕
├── create_ad_test.py                # Alternative test script
├── Avatar.png                       # Example character image
├── logo.png                         # Example logo image
└── README.md                        # This file
```

**Key Features:**
- ✅ **Dynamic Movement Prompts** - Characters move, gesture, demonstrate (GPT-style prompts) 🆕
- ✅ **Exact Script Adherence** - Uses your exact words without paraphrasing 🆕
- ✅ **Frame-to-Frame Continuity** - Smooth transitions between clips 🆕
- ✅ **Auto-Retry on Content Policy Fails** - Falls back to original avatar automatically 🆕
- ✅ **Script Normalization** - Converts special chars (—, "", '') to prevent gibberish 🆕
- ✅ **Direct Veo API Integration** - Perfect lip-sync from character image
- ✅ **ElevenLabs Voice Changer** - Professional voice enhancement (Speech-to-Speech) 🆕
- ✅ **GCS Checkpoint System** - All clips saved to cloud storage for resume/replay
- ✅ **Character Image Optimization** - Auto-resized to 768px for Veo API compatibility
- ✅ **Comprehensive Logging** - Rotating file logs with detailed debugging

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

Typical ad creation takes **4-6 minutes** (simplified workflow):

| Step | Duration | Description |
|------|----------|-------------|
| 1. Prompt Generation | 10-30s | Gemini generates GPT-style Veo prompts with lip-sync emphasis |
| 2. Video Generation | 3-5 min | Veo 3.1 generates clips with built-in audio (sequential) |
| 3. Video Merging | 10-30s | ffmpeg concatenation |
| 4. Voice Enhancement | 30-60s | ElevenLabs Voice Changer (optional) |
| 5. Final Upload | 10-20s | GCS upload with signed URL |
| **Total** | **4-6 min** | Complete workflow |

**Previous 10-step audio-first workflow** is still available but commented out in code for reference.

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
