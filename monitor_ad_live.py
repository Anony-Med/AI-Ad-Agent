"""Live monitoring for a specific ad job."""
import subprocess
import time
import sys
import io
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

AD_ID = "ad_1762995185.213989"
PROJECT = "sound-invention-432122-m5"
CHECK_INTERVAL = 10  # seconds

def get_latest_logs():
    """Get latest logs for the ad."""
    cmd = [
        "gcloud", "logging", "read",
        f'resource.type=cloud_run_revision AND resource.labels.service_name=ai-ad-agent AND textPayload=~"{AD_ID}"',
        "--limit", "10",
        "--format=value(timestamp,textPayload)",
        f"--project={PROJECT}",
        "--freshness=2m"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except Exception as e:
        return f"Error fetching logs: {e}"

def parse_progress(log_text):
    """Extract progress, current step, and status from logs."""
    lines = log_text.split('\n')

    progress = None
    current_clip = None
    status = "running"
    script = None

    for line in lines:
        if "Saving job progress:" in line:
            progress = line.split("progress:")[-1].strip()
        if "========== STARTING CLIP" in line:
            current_clip = line.split("CLIP")[1].strip().replace("=", "").strip()
        if "Script:" in line and AD_ID in line:
            script = line.split("Script:")[-1].strip()
        if "completed" in line.lower() and "successfully" in line.lower():
            status = "completed"
        if "failed" in line.lower() or "error" in line.lower():
            status = "error"

    return {
        "progress": progress,
        "current_clip": current_clip,
        "status": status,
        "script": script
    }

def main():
    print(f"🔍 Monitoring ad: {AD_ID}")
    print(f"📊 Checking every {CHECK_INTERVAL} seconds (Ctrl+C to stop)\n")
    print("=" * 70)

    last_progress = None
    last_clip = None

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            logs = get_latest_logs()

            if logs and "Error" not in logs:
                info = parse_progress(logs)

                # Only print if something changed
                changed = (info["progress"] != last_progress or
                          info["current_clip"] != last_clip)

                if changed or last_progress is None:
                    print(f"\n[{now}]")
                    if info["progress"]:
                        print(f"  Progress: {info['progress']}")
                    if info["current_clip"]:
                        print(f"  Current: Clip {info['current_clip']}")
                    if info["script"]:
                        print(f"  Script: {info['script']}")
                    print(f"  Status: {info['status']}")

                    last_progress = info["progress"]
                    last_clip = info["current_clip"]

                    if info["status"] == "completed":
                        print("\n✅ Ad generation completed!")
                        break
                    elif info["status"] == "error":
                        print("\n❌ Error detected in ad generation!")
                        break
            else:
                print(f"[{now}] Waiting for logs...")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n⏹️ Monitoring stopped")

if __name__ == "__main__":
    main()
