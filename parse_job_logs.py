"""Parse and organize job logs into readable format."""
import json
import sys
import io
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

JOB_ID = "ad_1762980163.250578"

print(f"Parsing logs for job: {JOB_ID}")
print("=" * 80)

try:
    # Read the raw logs
    with open('job_ad_1762980163_all_logs.json', 'r', encoding='utf-8') as f:
        logs = json.load(f)

    print(f"Total log entries: {len(logs)}\n")

    # Extract and organize
    organized_logs = []

    for log in logs:
        timestamp = log.get('timestamp', '')
        text = log.get('textPayload', '')
        severity = log.get('severity', 'INFO')

        organized_logs.append({
            'timestamp': timestamp,
            'severity': severity,
            'message': text
        })

    # Sort by timestamp (oldest first)
    organized_logs.sort(key=lambda x: x['timestamp'])

    # Save organized version
    with open('job_ad_1762980163_organized_logs.json', 'w', encoding='utf-8') as f:
        json.dump(organized_logs, f, indent=2, ensure_ascii=False)

    print("Saved organized logs to: job_ad_1762980163_organized_logs.json")

    # Create a timeline summary
    timeline = []

    for log in organized_logs:
        msg = log['message']
        ts = log['timestamp']

        # Extract key events
        if any(keyword in msg for keyword in [
            'Generating clip',
            'Saved clip',
            'merged',
            'ERROR',
            'Failed',
            'Step',
            'completed',
            'final'
        ]):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = ts[:19] if len(ts) > 19 else ts

            timeline.append({
                'time': time_str,
                'severity': log['severity'],
                'event': msg
            })

    # Save timeline
    with open('job_ad_1762980163_timeline.json', 'w', encoding='utf-8') as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    print("Saved timeline to: job_ad_1762980163_timeline.json")

    # Print summary
    print("\n" + "=" * 80)
    print("KEY EVENTS TIMELINE:")
    print("=" * 80)

    for event in timeline:
        severity_marker = {
            'ERROR': '[ERROR]',
            'WARNING': '[WARN]',
            'INFO': '[INFO]'
        }.get(event['severity'], '[INFO]')

        print(f"{severity_marker} [{event['time']}] {event['event'][:100]}")

    # Count by type
    errors = [l for l in organized_logs if 'ERROR' in l['severity']]
    warnings = [l for l in organized_logs if 'WARNING' in l['severity']]

    print("\n" + "=" * 80)
    print(f"Summary:")
    print(f"  Total logs: {len(organized_logs)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Info: {len(organized_logs) - len(errors) - len(warnings)}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
