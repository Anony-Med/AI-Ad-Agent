# Streaming Endpoints Comparison

## Two Options Available

### Option 1: `/create-stream` (Base64)
**Input:** JSON with base64-encoded image

```bash
curl -N -X POST http://localhost:8001/api/ad-agent/create-stream \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "Your ad script...",
    "character_image": "data:image/png;base64,iVBORw0KG...",
    "character_name": "Heather"
  }'
```

**Python:**
```python
import base64

# Must convert to base64 first
with open("Avatar.png", "rb") as f:
    avatar_b64 = base64.b64encode(f.read()).decode()

request_data = {
    "script": "Your script...",
    "character_image": f"data:image/png;base64,{avatar_b64}"
}

# Then send as JSON
async with client.stream("POST", url, json=request_data) as response:
    ...
```

**Pros:**
- Works with any HTTP client
- Can send image as string in JSON

**Cons:**
- Must manually convert to base64 (~33% larger payload)
- Extra step in code

---

### Option 2: `/create-stream-upload` (File Upload) ⭐ **RECOMMENDED**
**Input:** Multipart form data with file upload

```bash
curl -N -X POST http://localhost:8001/api/ad-agent/create-stream-upload \
  -H "Authorization: Bearer TOKEN" \
  -F "script=Your ad script..." \
  -F "avatar=@Avatar.png" \
  -F "character_name=Heather"
```

**Python:**
```python
# No base64 conversion needed!
files = {"avatar": open("Avatar.png", "rb")}
data = {
    "script": "Your script...",
    "character_name": "Heather"
}

# Send as multipart/form-data
async with client.stream("POST", url, files=files, data=data) as response:
    ...
```

**Pros:**
- ✅ **No base64 conversion** - just upload the file!
- ✅ **Smaller payload** - binary vs base64 text (~33% smaller)
- ✅ **Standard HTTP** - multipart/form-data is universal
- ✅ **Easier to use** - less code, more intuitive

**Cons:**
- Requires multipart form support (but all HTTP clients have this)

---

## Comparison Table

| Feature | `/create-stream` | `/create-stream-upload` |
|---------|------------------|------------------------|
| **Input Format** | JSON | Multipart form |
| **Image Format** | Base64 string | File upload |
| **Payload Size** | Larger (+33%) | Smaller (binary) |
| **Ease of Use** | Medium (need base64) | ⭐ Easy (direct upload) |
| **Code Required** | More (convert to base64) | Less (just open file) |
| **HTTP Client** | Any | Any (multipart support) |
| **Progress Events** | ✅ Real-time SSE | ✅ Real-time SSE |
| **Response** | Same | Same |

---

## Which One to Use?

### Use `/create-stream-upload` if:
- ✅ You're uploading from local files
- ✅ You want simpler code
- ✅ You want smaller payloads
- ✅ **RECOMMENDED for most users**

### Use `/create-stream` if:
- You already have base64 data
- You're sending from a web app (image already in memory)
- You prefer pure JSON APIs

---

## Test Scripts

**Base64 version:**
```bash
python test_stream_ad.py
```

**File upload version (easier):**
```bash
python test_upload_ad.py
```

---

## Both Return Same Events

Both endpoints stream identical progress events:
- `step1` - Generating prompts
- `step2_clip` - Generating clip X/Y
- `step3` - Merging videos
- `step4` - Enhancing voice
- `step5` - Finalizing
- `complete` - Final video URL

---

## Example: Full Request/Response

### Request (File Upload - Recommended)
```bash
curl -N -X POST http://localhost:8001/api/ad-agent/create-stream-upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "script=Tired of hurricanes? Hi, I'm Heather..." \
  -F "avatar=@Avatar.png" \
  -F "character_name=Heather" \
  -F "aspect_ratio=16:9" \
  -F "resolution=720p"
```

### Response (Same for Both)
```
event: step1
data: {"step": 1, "message": "Generating video prompts...", "progress": 10}

event: step1_complete
data: {"step": 1, "message": "Generated 6 video prompts", "total_clips": 6, "progress": 20}

event: step2_clip
data: {"step": 2, "message": "Generating clip 1/6", "current_clip": 1, "total_clips": 6, "progress": 30}

event: step2_clip
data: {"step": 2, "message": "Generating clip 2/6", "current_clip": 2, "total_clips": 6, "progress": 33}

...

event: step3
data: {"step": 3, "message": "Merging video clips...", "progress": 60}

event: step4
data: {"step": 4, "message": "Enhancing voice with ElevenLabs...", "progress": 80}

event: step5
data: {"step": 5, "message": "Finalizing...", "progress": 95}

event: complete
data: {"status": "completed", "final_video_url": "https://storage.googleapis.com/...", "job_id": "ad_..."}
```

---

## Summary

**Recommended:** Use `/create-stream-upload` for the best developer experience!

- No base64 encoding
- Smaller payloads
- Simpler code
- Standard multipart/form-data
- Real-time progress updates
- Returns final video URL
