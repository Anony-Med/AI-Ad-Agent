"""Kill all Python processes that might be servers."""
import psutil

killed = 0

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] and 'python' in proc.info['name'].lower():
            cmdline = proc.info['cmdline']
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                # Check if it's a uvicorn/fastapi server
                if any(keyword in cmdline_str.lower() for keyword in ['uvicorn', 'main:app', 'fastapi', ':8000']):
                    print(f"Killing PID {proc.info['pid']}: {cmdline_str[:100]}")
                    proc.kill()
                    proc.wait(timeout=3)
                    killed += 1
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

if killed == 0:
    print("No Python server processes found")
else:
    print(f"\nKilled {killed} Python server process(es)")
