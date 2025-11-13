"""Fetch Cloud Run logs directly using Google Cloud Logging API."""
from google.cloud import logging
from datetime import datetime, timedelta, timezone
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ID = "sound-invention-432122-m5"
SERVICE_NAME = "ai-ad-agent"
JOB_ID = "ad_1762980163.250578"

print(f"🔍 Fetching Cloud Run logs for job: {JOB_ID}")
print("=" * 80)

try:
    # Initialize logging client
    client = logging.Client(project=PROJECT_ID)

    # Calculate time range (last 2 hours)
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=2)

    # Build filter
    filter_str = f'''
        resource.type="cloud_run_revision"
        resource.labels.service_name="{SERVICE_NAME}"
        timestamp>="{start_time.isoformat()}"
    '''

    print(f"📅 Time range: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"🔍 Searching for job ID: {JOB_ID}\n")

    # Fetch logs
    entries = list(client.list_entries(
        filter_=filter_str,
        order_by=logging.DESCENDING,
        max_results=500
    ))

    if not entries:
        print("❌ No logs found in this time range")
        print("\n💡 Possible reasons:")
        print("   1. Job was created more than 2 hours ago")
        print("   2. Service didn't receive the request")
        print("   3. Authentication issue")
        sys.exit(0)

    print(f"✅ Found {len(entries)} total log entries\n")
    print("=" * 80)

    # Categorize logs
    job_logs = []
    error_logs = []
    warning_logs = []
    all_logs = []

    for entry in entries:
        timestamp = entry.timestamp.isoformat() if entry.timestamp else "unknown"
        severity = entry.severity or "INFO"

        # Get message text
        if hasattr(entry, 'payload') and isinstance(entry.payload, str):
            message = entry.payload
        elif hasattr(entry, 'payload') and isinstance(entry.payload, dict):
            message = entry.payload.get('message', str(entry.payload))
        else:
            message = str(entry.payload) if hasattr(entry, 'payload') else ""

        all_logs.append({
            'timestamp': timestamp,
            'severity': severity,
            'message': message
        })

        # Check for job ID
        if '1762980163' in str(message):
            job_logs.append({
                'timestamp': timestamp,
                'severity': severity,
                'message': message
            })

        # Check for errors
        if 'ERROR' in severity or 'CRITICAL' in severity:
            error_logs.append({
                'timestamp': timestamp,
                'severity': severity,
                'message': message
            })

        # Check for warnings
        if 'WARNING' in severity:
            warning_logs.append({
                'timestamp': timestamp,
                'severity': severity,
                'message': message
            })

    # Display job-specific logs
    if job_logs:
        print(f"\n✅ FOUND LOGS FOR JOB {JOB_ID}:")
        print("=" * 80)
        for log in job_logs:
            print(f"\n[{log['timestamp']}] [{log['severity']}]")
            print(log['message'][:1000])  # Show first 1000 chars
        print("\n" + "=" * 80)
    else:
        print(f"\n⚠️ NO LOGS FOUND FOR JOB {JOB_ID}")
        print("=" * 80)
        print("\nThis could mean:")
        print("   1. Job never started (failed before logging)")
        print("   2. Different job ID was used")
        print("   3. Request didn't reach the backend")

    # Display errors
    if error_logs:
        print(f"\n❌ ERROR LOGS ({len(error_logs)}):")
        print("=" * 80)
        for log in error_logs[:10]:  # Show first 10
            print(f"\n[{log['timestamp']}] [{log['severity']}]")
            print(log['message'][:800])
        print("\n" + "=" * 80)

    # Display warnings
    if warning_logs:
        print(f"\n⚠️ WARNING LOGS ({len(warning_logs)}):")
        print("=" * 80)
        for log in warning_logs[:5]:  # Show first 5
            print(f"\n[{log['timestamp']}] [{log['severity']}]")
            print(log['message'][:500])
        print("\n" + "=" * 80)

    # Show recent activity
    if not job_logs:
        print(f"\n📝 MOST RECENT LOGS (for context):")
        print("=" * 80)
        for log in all_logs[:10]:
            print(f"\n[{log['timestamp']}] [{log['severity']}]")
            print(log['message'][:300])
        print("\n" + "=" * 80)

    # Save to file
    with open('cloud_run_logs_full.json', 'w', encoding='utf-8') as f:
        json.dump(all_logs, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Full logs saved to: cloud_run_logs_full.json")

    # Save job-specific logs if found
    if job_logs:
        with open(f'job_{JOB_ID}_logs.json', 'w', encoding='utf-8') as f:
            json.dump(job_logs, f, indent=2, ensure_ascii=False)
        print(f"💾 Job-specific logs saved to: job_{JOB_ID}_logs.json")

except Exception as e:
    print(f"❌ Error fetching logs: {e}")
    import traceback
    traceback.print_exc()
