"""Monitor Cloud Run logs in real-time."""
import subprocess
import sys
import time
from datetime import datetime, timedelta

def monitor_logs():
    """Monitor Cloud Run logs in real-time."""

    print("=" * 80)
    print("MONITORING CLOUD RUN LOGS")
    print("=" * 80)
    print(f"Service: ai-ad-agent")
    print(f"Region: europe-west1")
    print(f"Starting from: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 80)
    print()

    # Start time
    start_time = datetime.utcnow() - timedelta(minutes=1)
    start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Build gcloud command for streaming logs
    cmd = [
        'gcloud', 'logging', 'tail',
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="ai-ad-agent"',
        '--project', 'sound-invention-432122-m5',
        '--format', 'value(timestamp,severity,textPayload,jsonPayload.message)'
    ]

    try:
        # Stream logs
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        print("Streaming logs (press Ctrl+C to stop)...\n")

        for line in process.stdout:
            if line.strip():
                # Parse the line
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    timestamp = parts[0] if len(parts) > 0 else ''
                    severity = parts[1] if len(parts) > 1 else ''
                    message = '\t'.join(parts[2:]) if len(parts) > 2 else ''

                    # Color code by severity
                    prefix = f"[{severity}]"
                    if severity == "ERROR":
                        prefix = f"[ERROR]"
                    elif severity == "WARNING":
                        prefix = f"[WARN]"
                    elif severity == "INFO":
                        prefix = f"[INFO]"

                    # Print formatted log
                    time_only = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else timestamp
                    print(f"{time_only} {prefix} {message}")
                else:
                    print(line.strip())

    except KeyboardInterrupt:
        print("\n\nLog monitoring stopped by user.")
        process.terminate()
    except Exception as e:
        print(f"\nError monitoring logs: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    monitor_logs()
