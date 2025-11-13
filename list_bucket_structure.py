"""List bucket structure to find where files are."""
from google.cloud import storage
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT = "sound-invention-432122-m5"
BUCKET = "ai-ad-agent-videos"

print(f"📂 Bucket structure: {BUCKET}")
print("=" * 80)

try:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    # List all blobs (limit to recent ones)
    blobs = list(bucket.list_blobs(max_results=100))

    if not blobs:
        print("❌ Bucket is empty")
    else:
        print(f"✅ Showing up to 100 most recent files\n")

        # Organize by top-level directory
        by_dir = {}
        for blob in blobs:
            parts = blob.name.split("/")
            top_dir = parts[0] if len(parts) > 1 else "(root)"

            if top_dir not in by_dir:
                by_dir[top_dir] = []

            by_dir[top_dir].append({
                'path': blob.name,
                'size_mb': blob.size / (1024 * 1024),
                'updated': blob.updated
            })

        # Display
        for dir_name in sorted(by_dir.keys()):
            files = by_dir[dir_name]
            print(f"\n📁 {dir_name}/ ({len(files)} files)")
            print("-" * 80)
            for f in sorted(files, key=lambda x: x['updated'], reverse=True)[:10]:
                print(f"  {f['path']}")
                print(f"    {f['size_mb']:.3f} MB - {f['updated']}")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
