"""Check logs for a specific job ID in GCS."""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from google.cloud import storage
from app.config import settings

async def check_job_logs(job_id: str):
    """Check logs for a specific job ID."""

    # Initialize GCS client
    client = storage.Client(project=settings.GCP_PROJECT_ID)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)

    print(f"Searching for logs related to job: {job_id}")
    print(f"Bucket: {settings.GCS_BUCKET_NAME}")
    print("=" * 80)

    # List all blobs for this user/job ID
    # Try to find the user ID folder
    blobs = bucket.list_blobs(prefix=f"")

    found_files = []
    all_files = []
    for blob in blobs:
        if job_id in blob.name:
            found_files.append(blob.name)
            all_files.append({
                'name': blob.name,
                'size': blob.size,
                'created': blob.time_created
            })

    # Print summary first
    print(f"Total files found: {len(found_files)}\n")

    # Categorize files
    prompts = [f for f in all_files if '/prompts/' in f['name']]
    videos = [f for f in all_files if f['name'].endswith('.mp4')]
    audio = [f for f in all_files if f['name'].endswith(('.mp3', '.wav'))]
    images = [f for f in all_files if f['name'].endswith(('.png', '.jpg', '.jpeg'))]
    logs = [f for f in all_files if f['name'].endswith(('.log', '.txt', '.json'))]

    print(f"Prompts: {len(prompts)}")
    print(f"Videos: {len(videos)}")
    print(f"Audio: {len(audio)}")
    print(f"Images: {len(images)}")
    print(f"Logs/Text: {len(logs)}")
    print("\n" + "=" * 80 + "\n")

    # Now show details
    for file_info in all_files:
        blob_name = file_info['name']
        blob = bucket.blob(blob_name)

        print(f"\nFound: {blob_name}")
        print(f"Size: {file_info['size']} bytes")
        print(f"Created: {file_info['created']}")

        # If it's a log file or text file, show contents
        if blob.name.endswith(('.log', '.txt', '.json')):
            try:
                content = blob.download_as_text()
                print(f"\n--- Content of {blob.name} ---")
                print(content)
                print("--- End ---\n")
            except Exception as e:
                print(f"Could not read content: {e}")

    if not found_files:
        print("\nNo files found for this job ID.")
        print("\nSearching in common log locations:")

        # Try common patterns
        patterns = [
            f"logs/{job_id}",
            f"ad_agent/{job_id}",
            f"jobs/{job_id}",
            job_id.replace("ad_", ""),
        ]

        for pattern in patterns:
            print(f"\nChecking: {pattern}")
            blobs = bucket.list_blobs(prefix=pattern, max_results=10)
            for blob in blobs:
                print(f"  - {blob.name}")
    else:
        print(f"\n\nTotal files found: {len(found_files)}")

if __name__ == "__main__":
    job_id = "ad_1762931168.047527"
    asyncio.run(check_job_logs(job_id))
