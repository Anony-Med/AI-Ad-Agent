"""Fetch Cloud Run logs for a specific time period."""
import subprocess
import json
from datetime import datetime, timedelta

def fetch_cloud_run_logs(hours_ago=2):
    """Fetch Cloud Run logs from the last N hours."""

    # Calculate timestamp
    now = datetime.utcnow()
    start_time = now - timedelta(hours=hours_ago)

    # Format timestamp for gcloud (RFC3339)
    start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f"Fetching Cloud Run logs from {start_time_str} to now...")
    print("=" * 80)

    # gcloud command to fetch logs
    cmd = [
        'gcloud', 'logging', 'read',
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="ai-ad-agent" AND timestamp>="{start_time_str}"',
        '--limit', '500',
        '--format', 'json',
        '--project', 'sound-invention-432122-m5'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            print(f"Error fetching logs: {result.stderr}")
            return

        if not result.stdout.strip():
            print("No logs found for this time period.")
            return

        logs = json.loads(result.stdout)

        print(f"\nFound {len(logs)} log entries\n")

        # Filter and display relevant logs
        job_logs = []
        error_logs = []

        for log in logs:
            text = log.get('textPayload', '') or log.get('jsonPayload', {}).get('message', '')
            timestamp = log.get('timestamp', '')
            severity = log.get('severity', 'INFO')

            # Look for job ID
            if '1762931168' in str(text):
                job_logs.append((timestamp, severity, text))

            # Collect errors
            if severity in ['ERROR', 'CRITICAL']:
                error_logs.append((timestamp, severity, text))

        # Display job-specific logs
        if job_logs:
            print("\n" + "=" * 80)
            print("LOGS FOR JOB ad_1762931168.047527:")
            print("=" * 80)
            for ts, sev, msg in job_logs:
                print(f"\n[{ts}] [{sev}]")
                print(msg[:500])  # Truncate long messages

        # Display errors
        if error_logs:
            print("\n" + "=" * 80)
            print("ERROR LOGS:")
            print("=" * 80)
            for ts, sev, msg in error_logs[:10]:  # Show first 10 errors
                print(f"\n[{ts}] [{sev}]")
                print(str(msg)[:500])

        # Save full logs to file
        with open('cloud_run_logs.json', 'w') as f:
            json.dump(logs, f, indent=2)
        print(f"\n\nFull logs saved to: cloud_run_logs.json")

    except subprocess.TimeoutExpired:
        print("Timeout while fetching logs")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Fetch logs from last 6 hours (job ran at 07:06 UTC on Nov 12)
    fetch_cloud_run_logs(hours_ago=6)
