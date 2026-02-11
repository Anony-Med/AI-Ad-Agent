"""Create a fresh ad job via Cloud Run API endpoint."""
import requests
import json
import base64
import time

# Cloud Run endpoint
BASE_URL = "https://ai-ad-agent-994684344365.europe-west1.run.app"

# Test script
script = """Tired of hurricanes, repairs, or just ready for a change?

Hi, I'm Heather with She Buys Houses — a woman-owned company helping homeowners sell as-is.

No repairs. No waiting. No stress.

Whether you're downsizing, moving closer to family, or simply ready to let go — you deserve a fair cash offer and a seamless, easy process.

Call 1-888-SHE-BUYS or visit SheBuysHousesCash.com.

We'll take care of everything — so you can move forward with peace of mind."""

# Character image (1x1 white pixel as placeholder - replace with actual image)
character_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

# Create request body
request_body = {
    "script": script,
    "character_name": "Heather",
    "character_image_b64": character_image_b64,
    "voice_id": "default",
    "aspect_ratio": "16:9",
    "duration_per_clip": 7
}

print("=" * 80)
print("CREATING NEW AD JOB")
print("=" * 80)
print(f"Endpoint: {BASE_URL}/api/ad-agent/create-ad")
print(f"\nRequest body:")
print(f"  - Script: {len(script)} chars")
print(f"  - Character: {request_body['character_name']}")
print(f"  - Image: {len(character_image_b64)} chars (base64)")
print("=" * 80)

# Send request
try:
    response = requests.post(
        f"{BASE_URL}/api/ad-agent/create-ad",
        json=request_body,
        timeout=30
    )

    print(f"\n✅ Response Status: {response.status_code}")

    if response.status_code == 200 or response.status_code == 201:
        result = response.json()
        print(f"\n📝 Job Created!")
        print(json.dumps(result, indent=2))

        # Extract job ID
        job_id = result.get("job_id")
        if job_id:
            print(f"\n🎯 JOB ID: {job_id}")
            print(f"\n✅ Job started successfully!")
            print(f"\nMonitor at: {BASE_URL}/api/ad-agent/jobs/{job_id}")

            # Save job ID for monitoring
            with open("latest_job_id.txt", "w") as f:
                f.write(job_id)
            print(f"\n💾 Saved job ID to: latest_job_id.txt")
        else:
            print("\n⚠️  No job_id in response")
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text[:500])

except requests.exceptions.ConnectionError as e:
    print(f"\n❌ Connection error: {e}")
    print("\n💡 Tip: Make sure Cloud Run service is deployed and accessible")
except requests.exceptions.Timeout:
    print(f"\n⏱️  Request timed out after 30s")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
