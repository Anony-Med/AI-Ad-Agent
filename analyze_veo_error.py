"""Analyze Veo 403 error from Cloud Run logs."""
import json

with open('cloud_logs.json', 'r') as f:
    logs = json.load(f)

print("Searching for Veo API errors...")
print("=" * 80)

# Find the Veo 403 error with full details
for log in logs:
    text = log.get('textPayload', '')
    if '403' in str(text) and ('Veo' in str(text) or 'veo' in str(text)):
        print(f"\nTimestamp: {log.get('timestamp')}")
        print(f"Severity: {log.get('severity')}")
        print("\nFull message:")
        print(text)
        print("\n" + "=" * 80)
