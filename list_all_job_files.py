"""List ALL files in the job folder including subdirectories."""
from google.cloud import storage
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"
JOB_ID = "ad_1762980163.250578"

print(f"📂 Listing ALL files for job: {JOB_ID}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # List ALL blobs with this job prefix
    prefix = f"jobs/{JOB_ID}/"
    blobs = list(bucket.list_blobs(prefix=prefix))

    if not blobs:
        print(f"❌ No files found with prefix: {prefix}")
    else:
        print(f"✅ Found {len(blobs)} file(s):\n")

        # Group by directory
        files_by_dir = {}
        for blob in blobs:
            # Get relative path
            rel_path = blob.name.replace(prefix, "")

            # Determine directory
            if "/" in rel_path:
                dir_name = rel_path.split("/")[0]
            else:
                dir_name = "(root)"

            if dir_name not in files_by_dir:
                files_by_dir[dir_name] = []

            files_by_dir[dir_name].append({
                'name': blob.name,
                'size_mb': blob.size / (1024 * 1024),
                'updated': blob.updated
            })

        # Display organized by directory
        for dir_name in sorted(files_by_dir.keys()):
            print(f"\n📁 {dir_name}/")
            print("-" * 80)
            for file_info in files_by_dir[dir_name]:
                print(f"  {file_info['name']}")
                print(f"    Size: {file_info['size_mb']:.3f} MB")
                print(f"    Updated: {file_info['updated']}")
                print()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
