"""Monitor Cloud Run logs in real-time for a specific job."""
import subprocess
import json
import time
import sys
import io
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ID = "sound-invention-432122-m5"
JOB_ID = "ad_1762980163.250578"

print(f"Live monitoring for job: {JOB_ID}")
print("=" * 80)
print("Press Ctrl+C to stop\n")

last_timestamp = None
poll_interval = 5  # seconds

try:
    while True:
        # Calculate time range (last 10 minutes to capture everything)
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=10)
        start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Build gcloud command
        cmd = [
            'gcloud', 'logging', 'read',
            f'resource.type="cloud_run_revision" AND resource.labels.service_name="ai-ad-agent" AND textPayload:{JOB_ID.split("_")[1][:10]}',
            '--limit', '100',
            '--format', 'json',
            '--project', PROJECT_ID
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                logs = json.loads(result.stdout)

                # Filter to only new logs
                new_logs = []
                for log in logs:
                    timestamp = log.get('timestamp', '')
                    if last_timestamp is None or timestamp > last_timestamp:
                        new_logs.append(log)

                # Sort by timestamp (oldest first)
                new_logs.sort(key=lambda x: x.get('timestamp', ''))

                # Display new logs
                if new_logs:
                    for log in new_logs:
                        timestamp = log.get('timestamp', '')
                        text = log.get('textPayload', '')

                        # Parse timestamp for display
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            time_str = dt.strftime('%H:%M:%S')
                        except:
                            time_str = timestamp[:19] if len(timestamp) > 19 else timestamp

                        # Check for important keywords
                        if 'ERROR' in text or 'Failed' in text:
                            print(f"[ERROR] [{time_str}] {text}")
                        elif 'Generating clip' in text:
                            print(f"[CLIP] [{time_str}] {text}")
                        elif 'Saved clip' in text or 'Saved prompt' in text:
                            print(f"[SAVED] [{time_str}] {text}")
                        elif 'completed' in text.lower():
                            print(f"[DONE] [{time_str}] {text}")
                        elif 'Merging' in text or 'final' in text.lower():
                            print(f"[MERGE] [{time_str}] {text}")
                        else:
                            print(f"[INFO] [{time_str}] {text}")

                        last_timestamp = timestamp

                    print(f"\nLast update: {datetime.utcnow().strftime('%H:%M:%S')} UTC")
                    print("-" * 80)

        except subprocess.TimeoutExpired:
            print(f"[WARN] [{datetime.utcnow().strftime('%H:%M:%S')}] gcloud command timed out, retrying...")
        except Exception as e:
            print(f"[ERROR] Error: {e}")

        # Wait before next poll
        time.sleep(poll_interval)

except KeyboardInterrupt:
    print("\n\nMonitoring stopped by user")
