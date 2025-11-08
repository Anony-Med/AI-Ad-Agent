# AI Ad Agent - Automated Video Ad Creation Pipeline

Complete implementation of an AI-powered video ad creation system that automates the entire workflow from script to final video.

## 🎯 Overview

The AI Ad Agent executes an **8-step automated workflow** to create professional video ads:

1. **Generate Veo Prompts** - Analyze script and create optimal Veo 3.1 prompts (Gemini)
2. **Generate Video Clips** - Create 7-second video clips with character (Veo 3.1 via Unified API)
3. **Merge Videos** - Combine all clips into one seamless video (ffmpeg)
4. **Creative Suggestions** - Get enhancement ideas for animations/overlays (Gemini)
5. **Generate Voiceover** - Create complete script voiceover with your chosen voice (ElevenLabs)
6. **Replace Audio** - Replace video audio with consistent ElevenLabs voiceover (ffmpeg)
7. **Add Music & SFX** - Layer background music and sound effects (ElevenLabs + ffmpeg)
8. **Final Export** - Upload to GCS and create asset record

## 📁 Project Structure

```
backend/
├── app/
│   ├── ad_agent/                    # AI Ad Agent module
│   │   ├── agents/                  # ViMax-style agents
│   │   │   ├── prompt_generator.py      # Step 1: Generate Veo prompts
│   │   │   ├── video_generator.py       # Step 2: Generate videos
│   │   │   ├── creative_advisor.py      # Step 4: Creative suggestions
│   │   │   ├── audio_compositor.py      # Step 7: Audio generation
│   │   │   └── video_compositor.py      # Steps 3, 6, 8: Video assembly
│   │   ├── clients/                 # Direct API clients
│   │   │   ├── gemini_client.py         # Google Gemini text generation
│   │   │   └── elevenlabs_client.py     # ElevenLabs audio (TTS, SFX, Music)
│   │   ├── pipelines/               # Orchestration
│   │   │   └── ad_creation_pipeline.py  # Main 8-step pipeline
│   │   ├── interfaces/              # Schemas
│   │   │   └── ad_schemas.py            # Pydantic models
│   │   └── utils/                   # Utilities
│   │       └── video_utils.py           # ffmpeg video processing
│   ├── routes/
│   │   └── ad_agent.py              # API endpoints
│   └── database/
│       └── firestore_db.py          # Database methods (updated)
```

## 🚀 Setup

### 1. Prerequisites

- **Python 3.11+**
- **ffmpeg** - Required for video merging
  ```bash
  # Ubuntu/Debian
  sudo apt-get install ffmpeg

  # macOS
  brew install ffmpeg

  # Windows
  choco install ffmpeg
  ```

### 2. API Keys Required

Set these environment variables in your `.env` file:

```env
# Google Gemini API Key (for text generation)
GOOGLE_AI_API_KEY=your_google_ai_api_key_here
# OR
GEMINI_API_KEY=your_gemini_api_key_here

# ElevenLabs API Key (for audio generation)
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Unified API (already configured)
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app
```

### 3. Install Dependencies

Add these to your `requirements.txt` or install directly:

```bash
pip install google-generativeai httpx tenacity
```

### 4. Verify Installation

Check that the ad agent is healthy:

```bash
curl http://localhost:8000/api/ad-agent/health
```

Expected response:
```json
{
  "status": "healthy",
  "gemini_configured": true,
  "elevenlabs_configured": true,
  "unified_api_url": "https://unified-api-interface-994684344365.europe-west1.run.app"
}
```

## 📖 API Usage

### 1. Create an Ad

**Endpoint:** `POST /api/ad-agent/create`

**Authentication:** Required (Bearer token)

**Request Body:**

```json
{
  "campaign_id": "campaign_123",
  "script": "Looking for your dream home? I can help you find it. With years of experience in real estate, I'll guide you every step of the way.",
  "character_image": "BASE64_ENCODED_IMAGE_HERE",
  "character_name": "Heather",
  "voice_id": "optional_elevenlabs_voice_id",
  "background_music_prompt": "upbeat inspiring corporate music, subtle",
  "add_sound_effects": true,
  "aspect_ratio": "16:9",
  "resolution": "1080p"
}
```

**Response:**

```json
{
  "job_id": "ad_1699876543210",
  "status": "pending",
  "progress": 0,
  "current_step": "Job queued...",
  "final_video_url": null,
  "error_message": null,
  "created_at": "2025-01-15T12:00:00Z",
  "updated_at": "2025-01-15T12:00:00Z"
}
```

### 2. Check Job Status

**Endpoint:** `GET /api/ad-agent/jobs/{job_id}`

**Response:**

```json
{
  "job_id": "ad_1699876543210",
  "status": "generating_videos",
  "progress": 40,
  "current_step": "Generating 3 video clips with Veo 3.1...",
  "final_video_url": null,
  "error_message": null,
  "created_at": "2025-01-15T12:00:00Z",
  "updated_at": "2025-01-15T12:05:23Z"
}
```

**Status Values:**
- `pending` - Job queued
- `analyzing_script` - Analyzing script
- `generating_prompts` - Creating Veo prompts
- `generating_videos` - Generating video clips
- `merging_videos` - Merging clips
- `getting_suggestions` - Getting creative suggestions
- `adding_audio` - Adding music/SFX
- `finalizing` - Final upload
- `completed` - Job complete
- `failed` - Job failed

### 3. Download Final Video

**Endpoint:** `GET /api/ad-agent/jobs/{job_id}/download`

Returns a redirect to the signed GCS URL for download.

### 4. Test Prompt Generation

**Endpoint:** `POST /api/ad-agent/test/prompts`

Test prompt generation without creating videos:

```json
{
  "script": "Your ad script here",
  "character_name": "Heather"
}
```

**Response:**

```json
{
  "script": "...",
  "character_name": "Heather",
  "prompts": [
    "Medium shot of Heather standing in front of a modern house...",
    "Close-up of Heather inside a bright living room..."
  ],
  "total_clips": 2,
  "estimated_duration": 14
}
```

## 🔧 How It Works

### Step-by-Step Workflow

#### Step 1: Generate Veo Prompts
- Uses **Gemini 2.0 Flash** to analyze the script
- Breaks script into optimal 7-second segments
- Creates cinematic prompts with dialogue, camera angles, lighting
- Each prompt includes character reference and lip-sync instructions

#### Step 2: Generate Video Clips
- Calls **Veo 3.1** via Unified API for each prompt
- Uses character image as reference for consistency
- Generates up to 3 clips concurrently
- Polls jobs until completion (max 10 minutes per clip)

#### Step 3: Merge Videos
- Downloads all completed clips
- Uses **ffmpeg** to concatenate videos seamlessly
- Preserves audio from Veo (character voice)
- Uploads merged video to GCS

#### Step 4: Creative Suggestions
- Sends merged video description to **Gemini**
- Gets suggestions for:
  - Text overlays (e.g., "Dream Home Experts")
  - Animations (fade-ins, zooms)
  - GIFs/emojis
  - Video effects

#### Step 5: Generate Voiceover
- **Entire script** converted to speech using ElevenLabs
- Uses your chosen voice (e.g., "Heather Bryant")
- Or specify custom voice_id
- Ensures consistent voice quality throughout

#### Step 6: Replace Audio
- Downloads merged video (with Veo's original audio)
- **Replaces audio track** with ElevenLabs voiceover
- Uses ffmpeg to sync voice with video
- Maintains video quality, improves audio consistency

#### Step 7: Audio Composition
- **Background Music**: Generate with ElevenLabs Music API
- **Sound Effects**: Create ambient SFX with ElevenLabs
- Mix all audio layers with **ffmpeg**:
  - Voice (from ElevenLabs): 100% volume (primary)
  - Music: 20% volume (subtle background)
  - SFX: 50% volume (supporting)

#### Step 8: Final Export
- Upload final video to GCS
- Create asset record in Firestore
- Link to campaign
- Return signed URL

## 📊 Job Progress Tracking

The pipeline updates job status in real-time:

| Progress | Step | Description |
|----------|------|-------------|
| 0-10% | Pending | Job queued |
| 10-20% | Analyzing | Generating prompts |
| 20-50% | Generating | Creating videos |
| 50-60% | Merging | Combining clips |
| 60-75% | Suggestions | Getting creative ideas |
| 75-90% | Audio | Adding music/SFX |
| 90-100% | Finalizing | Uploading |

## 🧪 Testing

### Test Individual Components

```python
# Test Gemini prompt generation
from app.ad_agent.clients.gemini_client import GeminiClient

client = GeminiClient()
prompts = await client.generate_veo_prompts(
    script="Your script here",
    character_name="Heather"
)
print(prompts)
```

```python
# Test ElevenLabs audio
from app.ad_agent.clients.elevenlabs_client import ElevenLabsClient

client = ElevenLabsClient()
audio_bytes = await client.generate_music("upbeat corporate music")
```

### Test Full Pipeline

```bash
# 1. Create ad
curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d @test_ad_request.json

# 2. Check status (repeat until completed)
curl http://localhost:8000/api/ad-agent/jobs/ad_123 \
  -H "Authorization: Bearer YOUR_TOKEN"

# 3. Download video
curl http://localhost:8000/api/ad-agent/jobs/ad_123/download \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🔌 Integration with Unified API

The ad agent uses your **live Unified API** for:
- ✅ Video generation (Veo 3.1)
- ✅ Authentication (JWT tokens)
- ✅ Job status polling

**Direct API calls** (not in Unified API yet):
- Google Gemini (text generation)
- ElevenLabs (audio generation)

When you add `/v1/text` and `/v1/audio` endpoints to Unified API:
- Update `gemini_client.py` to use `unified_api_client`
- Update `elevenlabs_client.py` to use `unified_api_client`

## ⚙️ Configuration

### Environment Variables

```env
# Gemini (text generation)
GOOGLE_AI_API_KEY=your_key
GEMINI_API_KEY=your_key  # Alternative name

# ElevenLabs (audio)
ELEVENLABS_API_KEY=your_key

# Unified API (already configured)
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app

# Optional: Adjust timeouts
GEMINI_TIMEOUT=120
ELEVENLABS_TIMEOUT=300
```

### Pipeline Settings

Customize in `ad_creation_pipeline.py`:

```python
# Video generation
max_concurrent_videos = 3  # Parallel Veo jobs
video_timeout = 600  # 10 minutes per clip

# Audio mixing
music_volume = 0.25  # Background music level
sfx_volume = 0.6     # Sound effects level
```

## 🐛 Troubleshooting

### ffmpeg Not Found

```bash
RuntimeError: ffmpeg not installed
```

**Solution:** Install ffmpeg (see Setup section)

### Gemini API Errors

```bash
ValueError: GOOGLE_AI_API_KEY environment variable required
```

**Solution:** Set the API key in `.env`

### ElevenLabs Voice Not Found

```bash
WARNING: Voice 'Heather Bryant' not found, using default
```

**Solution:**
1. Get your voice ID from ElevenLabs dashboard
2. Pass `voice_id` directly in request
3. Or ensure voice name matches exactly

### Video Merge Fails

```bash
RuntimeError: Video merge failed
```

**Solution:**
- Check ffmpeg is installed
- Verify all video URLs are accessible
- Check disk space

### Veo Jobs Timeout

```bash
TimeoutError: Video job job_123 timed out after 600s
```

**Solution:**
- Increase timeout in pipeline
- Check Unified API status
- Retry failed clips

## 📈 Cost Estimation

Approximate costs per ad (subject to change):

| Service | Usage | Cost |
|---------|-------|------|
| **Gemini** | Prompt generation + suggestions | ~$0.01 |
| **Veo 3.1** | 3 clips × 7s each | ~$0.30 |
| **ElevenLabs** | Music + SFX | ~$0.05 |
| **GCS** | Storage + bandwidth | ~$0.01 |
| **Total** | Per ad | **~$0.37** |

## 🚀 Future Enhancements

- [ ] **Voice Changer Integration** - ElevenLabs speech-to-speech
- [ ] **Text Overlay Engine** - Programmatic text animation
- [ ] **GIF/Animation Support** - Giphy API integration
- [ ] **Video Templates** - Pre-designed templates
- [ ] **Batch Processing** - Generate multiple ads at once
- [ ] **A/B Testing** - Generate variations automatically
- [ ] **Analytics Integration** - Track ad performance
- [ ] **Mobile Preview** - Preview for different devices
- [ ] **Webhook Notifications** - Job completion alerts

## 📄 License

MIT License

## 🤝 Support

For issues:
- Check logs in `logs/` directory
- Enable debug mode: `DEBUG=True` in `.env`
- Check `/api/ad-agent/health` endpoint

---

**Built with:**
- ViMax-style multi-agent architecture
- Unified API for seamless model access
- Direct integrations for Gemini & ElevenLabs
- ffmpeg for professional video editing
