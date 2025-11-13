"""List all recent job folders in GCS."""
from google.cloud import storage
from datetime import datetime, timedelta, timezone
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"

print(f"📂 Listing recent job folders in bucket: {BUCKET}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # List all blobs under jobs/
    blobs = list(bucket.list_blobs(prefix="jobs/"))

    # Extract unique job IDs and their latest update time
    jobs = {}
    for blob in blobs:
        # Extract job ID from path like "jobs/ad_12345/..."
        parts = blob.name.split("/")
        if len(parts) >= 2 and parts[0] == "jobs":
            job_id = parts[1]
            if job_id not in jobs:
                jobs[job_id] = {
                    'first_seen': blob.updated,
                    'last_updated': blob.updated,
                    'file_count': 0,
                    'total_size_mb': 0
                }
            jobs[job_id]['file_count'] += 1
            jobs[job_id]['total_size_mb'] += blob.size / (1024 * 1024)
            if blob.updated > jobs[job_id]['last_updated']:
                jobs[job_id]['last_updated'] = blob.updated
            if blob.updated < jobs[job_id]['first_seen']:
                jobs[job_id]['first_seen'] = blob.updated

    if not jobs:
        print("❌ No job folders found")
    else:
        print(f"✅ Found {len(jobs)} job folder(s)\n")

        # Sort by last updated (most recent first)
        sorted_jobs = sorted(jobs.items(), key=lambda x: x[1]['last_updated'], reverse=True)

        for job_id, info in sorted_jobs[:10]:  # Show last 10 jobs
            print(f"\n📁 {job_id}")
            print(f"   Files: {info['file_count']}")
            print(f"   Total Size: {info['total_size_mb']:.2f} MB")
            print(f"   Created: {info['first_seen']}")
            print(f"   Last Updated: {info['last_updated']}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
