# Streaming Ad Creation Endpoint

## Overview

New endpoint: `POST /api/ad-agent/create-stream`

This endpoint creates video ads with **real-time progress updates** using Server-Sent Events (SSE). The user receives live updates as each step completes.

## Features

✅ **Simple Input** - Just provide script and avatar image
✅ **Real-Time Progress** - Streaming updates for each step
✅ **Detailed Status** - Know exactly what's happening (Step 1/5, Generating clip 3/7, etc.)
✅ **Final URL** - Returns signed URL when complete
✅ **Error Handling** - Real-time error notifications

## Input Format

```json
{
  "script": "Your ad script here...",
  "character_image": "data:image/png;base64,iVBORw0KG...",
  "character_name": "Heather",
  "voice_id": null,
  "aspect_ratio": "16:9",
  "resolution": "720p"
}
```

**Required:**
- `script` - The dialogue script (what the character will say)
- `character_image` - Base64-encoded avatar image with data URI prefix

**Optional:**
- `character_name` - Name of the character (default: "character")
- `voice_id` - ElevenLabs voice ID (default: uses "Heather Bryant")
- `aspect_ratio` - Video aspect ratio (default: "16:9")
- `resolution` - Video resolution (default: "720p")

## Progress Events

The endpoint streams the following events:

### Event: `step1`
```json
{
  "step": 1,
  "message": "Generating video prompts...",
  "progress": 10
}
```

### Event: `step1_complete`
```json
{
  "step": 1,
  "message": "Generated 6 video prompts",
  "total_clips": 6,
  "progress": 20
}
```

### Event: `step2_clip`
```json
{
  "step": 2,
  "message": "Generating clip 3/6",
  "current_clip": 3,
  "total_clips": 6,
  "progress": 35
}
```

### Event: `step3`
```json
{
  "step": 3,
  "message": "Merging video clips...",
  "progress": 60
}
```

### Event: `step4`
```json
{
  "step": 4,
  "message": "Enhancing voice with ElevenLabs...",
  "progress": 80
}
```

### Event: `step5`
```json
{
  "step": 5,
  "message": "Finalizing...",
  "progress": 95
}
```

### Event: `complete`
```json
{
  "status": "completed",
  "final_video_url": "https://storage.googleapis.com/...",
  "job_id": "ad_1762929442606477"
}
```

### Event: `error`
```json
{
  "message": "Error description here"
}
```

## Usage Examples

### Python (using httpx)

```python
import httpx
import json
import base64

# Load avatar
with open("Avatar.png", "rb") as f:
    avatar_b64 = base64.b64encode(f.read()).decode()

# Prepare request
request_data = {
    "script": "Your ad script here...",
    "character_image": f"data:image/png;base64,{avatar_b64}",
    "character_name": "Heather"
}

# Stream the response
async with httpx.AsyncClient(timeout=None) as client:
    async with client.stream(
        "POST",
        "http://localhost:8001/api/ad-agent/create-stream",
        json=request_data,
        headers={"Authorization": f"Bearer {token}"}
    ) as response:
        current_event = None
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())

                if current_event == "step2_clip":
                    print(f"Generating clip {data['current_clip']}/{data['total_clips']}")
                elif current_event == "complete":
                    print(f"Done! Video URL: {data['final_video_url']}")
```

### cURL

```bash
curl -N -X POST http://localhost:8001/api/ad-agent/create-stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "script": "Your ad script here...",
    "character_image": "data:image/png;base64,..."
  }'
```

**Note:** The `-N` flag disables buffering to see real-time updates.

### JavaScript (EventSource)

```javascript
const response = await fetch('http://localhost:8001/api/ad-agent/create-stream', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    script: "Your ad script here...",
    character_image: "data:image/png;base64,...",
    character_name: "Heather"
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {value, done} = await reader.read();
  if (done) break;

  const chunk = decoder.decode(value);
  const lines = chunk.split('\n');

  lines.forEach(line => {
    if (line.startsWith('event:')) {
      const event = line.split(':')[1].trim();
      console.log('Event:', event);
    } else if (line.startsWith('data:')) {
      const data = JSON.parse(line.split(':')[1].trim());
      console.log('Data:', data);
    }
  });
}
```

## Testing

Use the included test script:

```bash
# Make sure server is running
cd backend
python main.py

# In another terminal, run test script
python test_stream_ad.py
```

**Expected output:**
```
================================================================================
🎬 AI Ad Agent - Streaming Endpoint Test
================================================================================

🔐 Logging in...
✅ Logged in successfully

🖼️  Loading avatar from: C:\Users\shrey\Desktop\projects\ai ad agent\Avatar.png
✅ Avatar loaded (56580 chars base64)

📡 Starting streaming ad creation...
================================================================================

📝 Step 1/5: Generating video prompts...
✅ Step 1 Complete - Generated 6 prompts

🎬 Step 2/5: Generating clip 1/6... (30%)
🎬 Step 2/5: Generating clip 2/6... (33%)
🎬 Step 2/5: Generating clip 3/6... (36%)
🎬 Step 2/5: Generating clip 4/6... (40%)
🎬 Step 2/5: Generating clip 5/6... (43%)
🎬 Step 2/5: Generating clip 6/6... (46%)

🔗 Step 3/5: Merging video clips...
🎤 Step 4/5: Enhancing voice with ElevenLabs...
🎯 Step 5/5: Finalizing...

================================================================================
✅ AD CREATION COMPLETED!
================================================================================

Status: completed
Job ID: ad_1762929442606477

📹 Final Video URL:
https://storage.googleapis.com/ai-ad-agent-videos/...
```

## Architecture

```
Client Request
    ↓
POST /create-stream
    ↓
[Endpoint creates AsyncQueue]
    ↓
[Pipeline runs in background]
    ↓
[Progress callbacks → Queue]
    ↓
[Queue → Server-Sent Events]
    ↓
Client receives real-time updates
```

**Key Components:**

1. **StreamAdRequest** - Simple Pydantic schema for input
2. **Progress Callback** - Async function that emits events
3. **AsyncQueue** - Thread-safe queue for progress events
4. **StreamingResponse** - FastAPI SSE response
5. **Pipeline Integration** - All 5 steps emit progress events

## Comparison: Old vs New Endpoint

| Feature | `/create` (Old) | `/create-stream` (New) |
|---------|----------------|------------------------|
| Response Type | JSON (202 Accepted) | Server-Sent Events (streaming) |
| Progress Updates | Polling required | Real-time streaming |
| Input Complexity | Full AdRequest schema | Simplified StreamAdRequest |
| User Experience | Must poll /jobs/{id} | Live updates automatically |
| Final Result | Poll for completion | Streamed in final event |
| Background Job | Yes | No (runs in request context) |
| Job Tracking | Job ID returned | Job ID in final event |

## Benefits

1. **Better UX** - Users see exactly what's happening in real-time
2. **No Polling** - Server pushes updates automatically
3. **Simpler** - Just provide script and avatar, get video URL
4. **Transparent** - Know immediately if something fails
5. **Progress Visibility** - See "Generating clip 3/7" instead of "pending"

## Error Handling

If any step fails, an `error` event is sent immediately:

```json
{
  "event": "error",
  "data": {
    "message": "Failed to generate video: Invalid character image"
  }
}
```

The stream then closes, and the error is logged server-side.

## Performance

- **Total Time**: ~4-6 minutes (same as original endpoint)
- **Step 1**: 10-30 seconds (Gemini prompt generation)
- **Step 2**: 3-5 minutes (Veo video generation, per-clip updates)
- **Step 3**: 10-30 seconds (ffmpeg merge)
- **Step 4**: 30-60 seconds (ElevenLabs voice enhancement)
- **Step 5**: 10-20 seconds (GCS upload & finalization)

## Files Modified

1. **`backend/app/routes/ad_agent.py`**
   - Added `StreamAdRequest` schema
   - Added `/create-stream` endpoint with SSE

2. **`backend/app/ad_agent/pipelines/ad_creation_pipeline.py`**
   - Added `progress_callback` attribute
   - Added `_emit_progress()` method
   - Added progress events to all 5 steps

3. **`test_stream_ad.py`** (NEW)
   - Test script demonstrating streaming endpoint usage

## Next Steps

Potential enhancements:

- [ ] WebSocket support for bidirectional communication
- [ ] Resume/cancel functionality
- [ ] Multiple concurrent jobs
- [ ] Job queue with priority
- [ ] Webhook notifications for long-running jobs
- [ ] Frontend integration with progress bar

## Documentation

- API Docs: http://localhost:8001/docs#/AI%20Ad%20Agent/create_ad_stream_api_ad_agent_create_stream_post
- This file: `STREAMING_ENDPOINT_README.md`
