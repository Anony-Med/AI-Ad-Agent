"""Start a fresh ad job using swagger_request.json data."""
import requests
import json
import time
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Cloud Run endpoint
BASE_URL = "https://ai-ad-agent-994684344365.europe-west1.run.app"

print("=" * 80)
print("CREATING NEW AD JOB")
print("=" * 80)

# Load auth token
try:
    with open('auth_token.txt', 'r') as f:
        auth_token = f.read().strip()
    print(f"✅ Loaded auth token")
except:
    print(f"⚠️  No auth token found, will try without authentication")
    auth_token = None

# Load request data from swagger_request.json
try:
    with open('swagger_request.json', 'r') as f:
        request_body = json.load(f)

    print(f"\n✅ Loaded request from swagger_request.json")
    print(f"   - Script: {len(request_body['script'])} chars")
    print(f"   - Character: {request_body['character_name']}")
    print(f"   - Image: {len(request_body['character_image'])} chars")
    print(f"   - Voice: {request_body.get('voice_id', 'N/A')}")
    print(f"   - Aspect ratio: {request_body.get('aspect_ratio', 'N/A')}")
    print(f"   - Resolution: {request_body.get('resolution', 'N/A')}")
except Exception as e:
    print(f"\n❌ Error loading swagger_request.json: {e}")
    exit(1)

print("\n" + "=" * 80)
print(f"📤 Sending request to: {BASE_URL}/api/ad-agent/create-stream")
print("=" * 80)

# Send request with streaming
try:
    start_time = time.time()

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response = requests.post(
        f"{BASE_URL}/api/ad-agent/create-stream",
        json=request_body,
        headers=headers,
        stream=True,
        timeout=120
    )
    print(f"\n📊 Status Code: {response.status_code}")

    if response.status_code == 200:
        print(f"\n✅ STREAMING RESPONSE - Processing events...")
        print("=" * 80)

        job_id = None

        # Read streaming response
        for line in response.iter_lines(decode_unicode=True):
            if line:
                # Remove "data: " prefix from SSE
                if line.startswith("data: "):
                    line = line[6:]

                try:
                    data = json.loads(line)
                    event_type = data.get("type", "unknown")

                    if event_type == "job_created":
                        job_id = data.get("job_id")
                        print(f"\n🎯 JOB CREATED: {job_id}")

                        # Save job ID immediately
                        with open("latest_job_id.txt", "w") as f:
                            f.write(job_id)
                        print(f"💾 Saved job ID to: latest_job_id.txt")

                    elif event_type == "progress":
                        step = data.get("step", "")
                        message = data.get("message", "")
                        print(f"📍 [{step}] {message}")

                    elif event_type == "complete":
                        print(f"\n✅ JOB COMPLETED!")
                        video_url = data.get("video_url")
                        if video_url:
                            print(f"🎬 Video URL: {video_url}")

                    elif event_type == "error":
                        error = data.get("error", "Unknown error")
                        print(f"\n❌ ERROR: {error}")

                    else:
                        # Print other events
                        print(f"📨 {event_type}: {json.dumps(data, indent=2)}")

                except json.JSONDecodeError:
                    # Not JSON, just print the line
                    print(f"📄 {line}")

        elapsed = time.time() - start_time
        print(f"\n⏱️  Total time: {elapsed:.2f}s")

        if job_id:
            print(f"\n📍 Monitor logs:")
            print(f"   gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.message=~\"{job_id}\"' --limit 50 --project sound-invention-432122-m5")

        print("=" * 80)
    else:
        print(f"\n❌ ERROR Response:")
        print(response.text[:1000])

except requests.exceptions.ConnectionError as e:
    print(f"\n❌ Connection error: {e}")
    print("\n💡 Check if Cloud Run service is accessible")
except requests.exceptions.Timeout:
    print(f"\n⏱️  Request timed out after 60s")
    print("💡 The job may still be created - check Cloud Run logs")
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
