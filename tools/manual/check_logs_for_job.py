"""Check Cloud Run logs for specific job ID."""
from google.cloud import logging_v2
from google.cloud.logging_v2 import entries
from datetime import datetime, timedelta
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ID = "sound-invention-432122-m5"
JOB_ID = "ad_1762980163.250578"

print(f"📋 Checking Cloud Run logs for job: {JOB_ID}")
print("=" * 80)

try:
    # Initialize logging client
    client = logging_v2.Client(project=PROJECT_ID)

    # Look for logs from last 2 hours
    now = datetime.utcnow()
    start_time = now - timedelta(hours=2)

    # Build filter for Cloud Run logs mentioning this job
    filter_str = f'''
        resource.type="cloud_run_revision"
        resource.labels.service_name="ai-ad-agent"
        timestamp>="{start_time.isoformat()}Z"
        "{JOB_ID}"
    '''

    print(f"⏰ Searching logs from: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"🔍 Filter: Looking for job ID {JOB_ID}\n")
    print("=" * 80)

    # Fetch logs
    entries_list = list(client.list_entries(
        filter_=filter_str,
        order_by=logging_v2.DESCENDING,
        page_size=100
    ))

    if not entries_list:
        print(f"\n❌ No logs found for job {JOB_ID}")
        print("\nPossible reasons:")
        print("  1. Job was created >2 hours ago")
        print("  2. Job never reached Cloud Run backend")
        print("  3. Job ID is incorrect")
        print("\n💡 Try checking all recent logs without job filter...")
    else:
        print(f"\n✅ Found {len(entries_list)} log entries for this job:\n")

        for idx, entry in enumerate(entries_list, 1):
            timestamp = entry.timestamp.isoformat() if entry.timestamp else "N/A"
            severity = entry.severity if hasattr(entry, 'severity') else "INFO"

            # Extract message
            if hasattr(entry, 'text_payload'):
                message = entry.text_payload
            elif hasattr(entry, 'json_payload'):
                message = str(entry.json_payload)
            else:
                message = str(entry)

            print(f"\n[{idx}] [{timestamp}] [{severity}]")
            print("-" * 80)
            print(message[:1000])  # Show first 1000 chars

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
