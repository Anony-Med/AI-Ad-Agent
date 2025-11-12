"""Kill all processes on port 8001."""
import subprocess
import sys

# Find all processes on port 8001
result = subprocess.run(
    ['netstat', '-ano'],
    capture_output=True,
    text=True
)

killed = []
for line in result.stdout.split('\n'):
    if ':8001' in line and 'LISTENING' in line:
        parts = line.split()
        pid = parts[-1]
        if pid not in killed:
            print(f"Found process {pid} on port 8001")
            # Kill it forcefully
            subprocess.run(['taskkill', '/F', '/PID', pid])
            print(f"Killed process {pid}")
            killed.append(pid)

if killed:
    print(f"\nKilled {len(killed)} process(es)")
else:
    print("No process found on port 8001")
