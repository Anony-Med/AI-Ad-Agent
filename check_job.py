"""Quick check for specific job."""
from google.cloud import storage
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"
JOB_ID = "ad_1762980163.250578"

print(f"Checking job: {JOB_ID}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # Check checkpoint
    checkpoint_path = f"jobs/{JOB_ID}/checkpoint.json"
    checkpoint_blob = bucket.blob(checkpoint_path)

    if checkpoint_blob.exists():
        print(f"\n✅ Checkpoint found: {checkpoint_path}")
        checkpoint = json.loads(checkpoint_blob.download_as_text())

        print(f"\nStatus: {checkpoint.get('status', 'unknown')}")
        print(f"Progress: {checkpoint.get('progress', 0)}%")
        print(f"Current Step: {checkpoint.get('current_step', 'unknown')}")

        if 'error_message' in checkpoint and checkpoint['error_message']:
            print(f"\n❌ Error: {checkpoint['error_message']}")

        if 'prompts' in checkpoint:
            print(f"\nTotal Clips Expected: {len(checkpoint['prompts'])}")

        if 'generated_clips' in checkpoint:
            print(f"Clips Generated: {len(checkpoint['generated_clips'])}")

        if 'final_video_url' in checkpoint and checkpoint['final_video_url']:
            print(f"\n🎬 Final Video URL: {checkpoint['final_video_url']}")

        print("\n" + "=" * 80)
        print("Full Checkpoint Data:")
        print(json.dumps(checkpoint, indent=2))
    else:
        print(f"❌ No checkpoint found at: {checkpoint_path}")

    # List all files for this job
    print(f"\n\n📁 Files in job folder:")
    print("=" * 80)
    blobs = list(bucket.list_blobs(prefix=f"jobs/{JOB_ID}/"))

    if blobs:
        for blob in blobs:
            size_mb = blob.size / (1024 * 1024)
            print(f"{blob.name} ({size_mb:.2f} MB) - Updated: {blob.updated}")
    else:
        print("No files found")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
