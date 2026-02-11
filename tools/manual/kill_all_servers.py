"""Kill ALL server processes."""
import subprocess
import psutil

killed = 0

# Method 1: Kill by port
result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
pids = set()
for line in result.stdout.split('\n'):
    if ':8000' in line and 'LISTENING' in line:
        parts = line.split()
        pid = int(parts[-1])
        pids.add(pid)

print(f"Found {len(pids)} processes on port 8000")

for pid in pids:
    try:
        p = psutil.Process(pid)
        print(f"Killing PID {pid}: {p.name()}")
        p.kill()
        p.wait(timeout=3)
        killed += 1
    except Exception as e:
        print(f"Could not kill PID {pid}: {e}")

print(f"\nKilled {killed} process(es)")
