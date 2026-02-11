"""Monitor GCS bucket for recent jobs and their logs."""
import asyncio
from google.cloud import storage
from datetime import datetime, timedelta
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

GCP_PROJECT = "sound-invention-432122-m5"
GCS_BUCKET = "ai-ad-agent-videos"


def list_recent_jobs(hours=1):
    """List all job folders created in the last N hours."""
    print(f"🔍 Checking GCS bucket: {GCS_BUCKET}")
    print(f"📅 Looking for jobs from last {hours} hour(s)...\n")

    try:
        client = storage.Client(project=GCP_PROJECT)
        bucket = client.bucket(GCS_BUCKET)

        # Get all blobs with prefix "jobs/"
        blobs = list(bucket.list_blobs(prefix="jobs/"))

        if not blobs:
            print("❌ No job files found in bucket")
            return []

        # Group by job_id
        jobs = {}
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        for blob in blobs:
            # Extract job_id from path: jobs/{job_id}/...
            parts = blob.name.split('/')
            if len(parts) >= 2:
                job_id = parts[1]

                # Check if recent
                if blob.updated > cutoff_time:
                    if job_id not in jobs:
                        jobs[job_id] = {
                            'job_id': job_id,
                            'created': blob.updated,
                            'files': []
                        }
                    jobs[job_id]['files'].append({
                        'path': blob.name,
                        'size': blob.size,
                        'updated': blob.updated
                    })

        # Sort by creation time (most recent first)
        sorted_jobs = sorted(jobs.values(), key=lambda x: x['created'], reverse=True)

        print(f"✅ Found {len(sorted_jobs)} recent job(s):\n")

        for idx, job in enumerate(sorted_jobs, 1):
            print(f"{idx}. Job ID: {job['job_id']}")
            print(f"   Created: {job['created']}")
            print(f"   Files: {len(job['files'])}")

            # Show file types
            file_types = {}
            for f in job['files']:
                if 'checkpoint.json' in f['path']:
                    file_types['checkpoint'] = file_types.get('checkpoint', 0) + 1
                elif 'clip_' in f['path'] and '.mp4' in f['path']:
                    file_types['video_clips'] = file_types.get('video_clips', 0) + 1
                elif 'merged' in f['path']:
                    file_types['merged_video'] = file_types.get('merged_video', 0) + 1
                elif 'final' in f['path']:
                    file_types['final_video'] = file_types.get('final_video', 0) + 1
                elif 'avatar' in f['path']:
                    file_types['avatar'] = file_types.get('avatar', 0) + 1
                elif '.wav' in f['path'] or '.mp3' in f['path']:
                    file_types['audio'] = file_types.get('audio', 0) + 1

            for ftype, count in file_types.items():
                print(f"   - {ftype}: {count}")
            print()

        return sorted_jobs

    except Exception as e:
        print(f"❌ Error accessing GCS: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_job_checkpoint(job_id):
    """Get checkpoint data for a job."""
    try:
        client = storage.Client(project=GCP_PROJECT)
        bucket = client.bucket(GCS_BUCKET)

        checkpoint_path = f"jobs/{job_id}/checkpoint.json"
        blob = bucket.blob(checkpoint_path)

        if blob.exists():
            checkpoint_data = json.loads(blob.download_as_text())
            return checkpoint_data
        else:
            print(f"⚠️ No checkpoint file found for job {job_id}")
            return None

    except Exception as e:
        print(f"❌ Error reading checkpoint: {e}")
        return None


def show_job_details(job_id):
    """Show detailed information about a specific job."""
    print(f"\n📊 Job Details: {job_id}")
    print("=" * 60)

    checkpoint = get_job_checkpoint(job_id)

    if checkpoint:
        print(f"Status: {checkpoint.get('status', 'unknown')}")
        print(f"Progress: {checkpoint.get('progress', 0)}%")
        print(f"Current Step: {checkpoint.get('current_step', 'unknown')}")

        if 'error_message' in checkpoint and checkpoint['error_message']:
            print(f"\n❌ Error: {checkpoint['error_message']}")

        if 'prompts' in checkpoint:
            print(f"\n📝 Total Clips: {len(checkpoint['prompts'])}")

        if 'generated_clips' in checkpoint:
            print(f"✅ Generated Clips: {len(checkpoint['generated_clips'])}")
            for idx, clip in enumerate(checkpoint['generated_clips'], 1):
                print(f"   Clip {idx}: {clip.get('gcs_path', 'unknown')}")

        if 'merged_video_path' in checkpoint:
            print(f"\n🎬 Merged Video: {checkpoint['merged_video_path']}")

        if 'final_video_url' in checkpoint:
            print(f"\n🎉 Final Video URL: {checkpoint['final_video_url']}")

    # List all files for this job
    try:
        client = storage.Client(project=GCP_PROJECT)
        bucket = client.bucket(GCS_BUCKET)
        blobs = list(bucket.list_blobs(prefix=f"jobs/{job_id}/"))

        print(f"\n📁 All Files ({len(blobs)}):")
        for blob in blobs:
            size_mb = blob.size / (1024 * 1024)
            print(f"   - {blob.name} ({size_mb:.2f} MB)")
    except Exception as e:
        print(f"❌ Error listing files: {e}")


def monitor_job_progress(job_id, interval=5):
    """Monitor job progress by polling checkpoint."""
    print(f"\n🔄 Monitoring job: {job_id}")
    print(f"Polling every {interval} seconds (Ctrl+C to stop)...\n")

    try:
        last_progress = -1
        last_step = ""

        while True:
            checkpoint = get_job_checkpoint(job_id)

            if checkpoint:
                progress = checkpoint.get('progress', 0)
                step = checkpoint.get('current_step', 'unknown')
                status = checkpoint.get('status', 'unknown')

                # Only print if changed
                if progress != last_progress or step != last_step:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {progress}% - {step} (Status: {status})")
                    last_progress = progress
                    last_step = step

                    # Check for completion or error
                    if status == 'completed':
                        print("\n✅ Job completed!")
                        if 'final_video_url' in checkpoint:
                            print(f"🎬 Video URL: {checkpoint['final_video_url']}")
                        break
                    elif status == 'failed':
                        print("\n❌ Job failed!")
                        if 'error_message' in checkpoint:
                            print(f"Error: {checkpoint['error_message']}")
                        break

            import time
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n⏹️ Monitoring stopped by user")


def main():
    """Main CLI."""
    print("🤖 AI Ad Agent - GCS Job Monitor")
    print("=" * 60)

    # List recent jobs
    jobs = list_recent_jobs(hours=2)

    if not jobs:
        print("\n💡 No recent jobs found. Job might be:")
        print("   1. Still initializing (not yet written to GCS)")
        print("   2. Failed before creating checkpoint")
        print("   3. Check Cloud Run logs for errors")
        print("\n📝 To view Cloud Run logs:")
        print("   gcloud logging read 'resource.type=cloud_run_revision' --limit 50 --project sound-invention-432122-m5")
        return

    # Show most recent job details
    most_recent = jobs[0]
    show_job_details(most_recent['job_id'])

    # Ask if user wants to monitor
    print("\n" + "=" * 60)
    response = input("\n🔄 Monitor this job in real-time? (y/n): ").strip().lower()

    if response == 'y':
        monitor_job_progress(most_recent['job_id'])
    else:
        print("\n💡 You can monitor manually using:")
        print(f"   python monitor_gcs_logs.py --job {most_recent['job_id']}")


if __name__ == "__main__":
    import sys

    # Check for --job argument
    if len(sys.argv) > 2 and sys.argv[1] == "--job":
        job_id = sys.argv[2]
        monitor_job_progress(job_id)
    else:
        main()
