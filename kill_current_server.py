"""Kill server on port 8001."""
import subprocess
import psutil

# Get process on port 8001
result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
for line in result.stdout.split('\n'):
    if ':8001' in line and 'LISTENING' in line:
        parts = line.split()
        pid = int(parts[-1])
        try:
            p = psutil.Process(pid)
            print(f"Killing server PID {pid}: {p.name()}")
            p.kill()
            print("Server killed successfully")
        except Exception as e:
            print(f"Error: {e}")
        break
else:
    print("No server found on port 8001")
