# AI Ad Agent - Example Usage

## Quick Start Example

### Step 1: Set Environment Variables

Create `.env` file in `backend/` directory:

```env
# Google Gemini
GOOGLE_AI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXX

# ElevenLabs
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Already configured
UNIFIED_API_BASE_URL=https://unified-api-interface-994684344365.europe-west1.run.app
GCP_PROJECT_ID=sound-invention-432122-m5
GCS_BUCKET_NAME=your-bucket-name
```

### Step 2: Login and Get Token

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your_password"
  }'

# Save the token
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Step 3: Create a Campaign

```bash
curl -X POST http://localhost:8000/api/campaigns \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Real Estate Ads Q1 2025",
    "platform": "instagram",
    "ad_type": "video",
    "aspect_ratio": "9:16",
    "description": "Short video ads for real estate listings"
  }'

# Save the campaign_id
export CAMPAIGN_ID="xyz123abc456"
```

### Step 4: Prepare Character Image

Convert your character image to base64:

```bash
# Linux/Mac
base64 heather.jpg | tr -d '\n' > heather_base64.txt

# Or use Python
python -c "import base64; print(base64.b64encode(open('heather.jpg', 'rb').read()).decode())" > heather_base64.txt

export CHARACTER_IMAGE=$(cat heather_base64.txt)
```

### Step 5: Create Ad

```bash
curl -X POST http://localhost:8000/api/ad-agent/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"campaign_id\": \"$CAMPAIGN_ID\",
    \"script\": \"Looking for your dream home? I can help you find it. With years of experience in real estate, I'll guide you every step of the way. Let's make your homeownership dreams a reality.\",
    \"character_image\": \"$CHARACTER_IMAGE\",
    \"character_name\": \"Heather\",
    \"background_music_prompt\": \"upbeat inspiring corporate music, subtle, professional\",
    \"add_sound_effects\": true,
    \"aspect_ratio\": \"16:9\",
    \"resolution\": \"1080p\"
  }"

# Response:
# {
#   "job_id": "ad_1699876543210",
#   "status": "pending",
#   "progress": 0,
#   ...
# }

export JOB_ID="ad_1699876543210"
```

### Step 6: Monitor Progress

```bash
# Check status every 30 seconds
watch -n 30 "curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H 'Authorization: Bearer $TOKEN' | jq"

# Or use a loop
while true; do
  STATUS=$(curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
    -H "Authorization: Bearer $TOKEN" | jq -r '.status')

  PROGRESS=$(curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
    -H "Authorization: Bearer $TOKEN" | jq -r '.progress')

  echo "Status: $STATUS | Progress: $PROGRESS%"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi

  sleep 30
done
```

### Step 7: Download Final Video

```bash
# Get the download URL
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID/download \
  -H "Authorization: Bearer $TOKEN" \
  -L -o my_ad_video.mp4

# Or get the URL from status
VIDEO_URL=$(curl -s http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq -r '.final_video_url')

echo "Download from: $VIDEO_URL"
```

## Python Example

```python
import requests
import base64
import time

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "user@example.com"
PASSWORD = "your_password"

# 1. Login
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    json={"email": EMAIL, "password": PASSWORD}
)
token = login_response.json()["access_token"]

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 2. Create Campaign
campaign_response = requests.post(
    f"{BASE_URL}/api/campaigns",
    headers=headers,
    json={
        "name": "Real Estate Ads Q1 2025",
        "platform": "instagram",
        "ad_type": "video",
        "aspect_ratio": "9:16"
    }
)
campaign_id = campaign_response.json()["id"]

# 3. Encode Character Image
with open("heather.jpg", "rb") as f:
    character_image = base64.b64encode(f.read()).decode()

# 4. Create Ad
create_response = requests.post(
    f"{BASE_URL}/api/ad-agent/create",
    headers=headers,
    json={
        "campaign_id": campaign_id,
        "script": "Looking for your dream home? I can help you find it...",
        "character_image": character_image,
        "character_name": "Heather",
        "background_music_prompt": "upbeat inspiring corporate music",
        "add_sound_effects": True,
        "aspect_ratio": "16:9",
        "resolution": "1080p"
    }
)

job_id = create_response.json()["job_id"]
print(f"Job created: {job_id}")

# 5. Monitor Progress
while True:
    status_response = requests.get(
        f"{BASE_URL}/api/ad-agent/jobs/{job_id}",
        headers=headers
    )

    job_status = status_response.json()
    status = job_status["status"]
    progress = job_status["progress"]
    current_step = job_status.get("current_step", "")

    print(f"{status.upper()} - {progress}% - {current_step}")

    if status == "completed":
        video_url = job_status["final_video_url"]
        print(f"\n✅ Video ready: {video_url}")
        break
    elif status == "failed":
        error = job_status.get("error_message", "Unknown error")
        print(f"\n❌ Job failed: {error}")
        break

    time.sleep(30)

# 6. Download Video
download_response = requests.get(
    f"{BASE_URL}/api/ad-agent/jobs/{job_id}/download",
    headers=headers,
    allow_redirects=True
)

with open("final_ad.mp4", "wb") as f:
    f.write(download_response.content)

print("✅ Video downloaded: final_ad.mp4")
```

## Testing Prompts Only

Test prompt generation without creating videos:

```bash
curl -X POST http://localhost:8000/api/ad-agent/test/prompts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "Looking for your dream home? I can help you find it. With years of experience in real estate, I will guide you every step of the way.",
    "character_name": "Heather"
  }'
```

**Response:**

```json
{
  "script": "...",
  "character_name": "Heather",
  "prompts": [
    "Medium shot of Heather standing in front of a modern suburban house...",
    "Close-up of Heather inside a bright, spacious living room...",
    "Wide shot of Heather walking through a beautiful home..."
  ],
  "total_clips": 3,
  "estimated_duration": 21
}
```

## Expected Timeline

| Phase | Duration | Notes |
|-------|----------|-------|
| Prompt Generation | 10-30s | Gemini API |
| Video Generation | 5-10 min | 3 clips × Veo 3.1 |
| Video Merging | 30-60s | ffmpeg processing |
| Creative Suggestions | 10-20s | Gemini API |
| Audio Generation | 1-2 min | ElevenLabs |
| Final Upload | 30s | GCS upload |
| **Total** | **7-14 min** | Complete workflow |

## Sample Scripts

### Real Estate Ad (Short)

```
Looking for your dream home? I can help you find it.
With years of experience in real estate, I'll guide you every step of the way.
```

### Real Estate Ad (Medium)

```
Hi, I'm Heather, your local real estate expert.
Looking for your dream home? I specialize in finding the perfect property for families just like yours.
With personalized service and market expertise, I'll make your homeownership journey smooth and successful.
Let's find your dream home together.
```

### Product Ad

```
Introducing the all-new SmartHome Pro.
Transform your living space with cutting-edge automation.
Control lighting, temperature, and security from anywhere.
Experience the future of home living today.
```

## Troubleshooting

### Job Stuck at "generating_videos"

Check individual clip status:
```bash
curl http://localhost:8000/api/ad-agent/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.video_clips'
```

### Audio Missing

Ensure ElevenLabs API key is valid:
```bash
curl http://localhost:8000/api/ad-agent/health \
  -H "Authorization: Bearer $TOKEN"
```

### Video Quality Issues

Adjust resolution and aspect ratio:
- For Instagram Stories: `"aspect_ratio": "9:16"`
- For YouTube: `"aspect_ratio": "16:9"`
- For higher quality: `"resolution": "1080p"` (requires 8s duration)

## Tips for Best Results

1. **Keep scripts concise** - 3-4 sentences work best
2. **Use character image** - Clear, well-lit headshot
3. **Specify character actions** - "pointing", "smiling", "walking"
4. **Test prompts first** - Use `/test/prompts` endpoint
5. **Monitor progress** - Check status every 30 seconds
6. **Allow time** - Full workflow takes 7-14 minutes

## Next Steps

- Try different scripts and styles
- Experiment with voice settings
- Create multiple ads for A/B testing
- Integrate with your ad campaign workflow
