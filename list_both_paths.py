"""List files in both GCS paths for this job."""
from google.cloud import storage
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"
JOB_ID = "ad_1762980163.250578"

print(f"Listing all files for job: {JOB_ID}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # Path 1: jobs/ prefix
    print("\n1. FILES IN: jobs/{}/".format(JOB_ID))
    print("-" * 80)
    jobs_path = f"jobs/{JOB_ID}/"
    jobs_blobs = list(bucket.list_blobs(prefix=jobs_path))

    if jobs_blobs:
        for blob in jobs_blobs:
            size_mb = blob.size / (1024 * 1024)
            print(f"  {blob.name}")
            print(f"    Size: {size_mb:.3f} MB | Updated: {blob.updated}")
    else:
        print("  (No files found)")

    # Path 2: user_id based path - search for it
    print(f"\n2. FILES IN: <user_id>/{JOB_ID}/")
    print("-" * 80)

    # List all blobs and find ones with this job_id
    all_blobs = list(bucket.list_blobs())
    user_path_blobs = [b for b in all_blobs if JOB_ID in b.name and not b.name.startswith('jobs/')]

    if user_path_blobs:
        # Group by base path
        paths = {}
        for blob in user_path_blobs:
            # Extract base path (user_id/job_id)
            parts = blob.name.split('/')
            if len(parts) >= 2:
                base = '/'.join(parts[:2])
                if base not in paths:
                    paths[base] = []
                paths[base].append(blob)

        for path, blobs in paths.items():
            print(f"\n  Path: {path}/")
            for blob in blobs:
                size_mb = blob.size / (1024 * 1024)
                print(f"    {blob.name}")
                print(f"      Size: {size_mb:.3f} MB | Updated: {blob.updated}")
    else:
        print("  (No files found)")

    print("\n" + "=" * 80)
    print(f"Total files found: {len(jobs_blobs) + len(user_path_blobs)}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
