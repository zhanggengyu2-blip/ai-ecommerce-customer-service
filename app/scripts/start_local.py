"""Launch the local demo in the background with logs under var (Windows)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (8001, 6173):
        with socket.socket() as connection:
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is already in use; stop its existing service first.")
    log_dir = ROOT / "var"
    log_dir.mkdir(exist_ok=True)
    commands = {
        "backend": ([str(ROOT / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app",
                     "--host", "127.0.0.1", "--port", "8001"], ROOT / "backend"),
        "frontend": (["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                      str(ROOT / "scripts/start_frontend.ps1")], ROOT),
    }
    processes = {}
    try:
        for name, (command, cwd) in commands.items():
            with (log_dir / f"{name}.stdout.log").open("w") as stdout, \
                    (log_dir / f"{name}.stderr.log").open("w") as stderr:
                processes[name] = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        for url in ("http://127.0.0.1:8001/health", "http://127.0.0.1:6173"):
            deadline = time.monotonic() + 25
            while True:
                if any(process.poll() is not None for process in processes.values()):
                    raise RuntimeError("A service exited; inspect var/*.stderr.log.")
                try:
                    with urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, TimeoutError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Service startup timed out: {url}; inspect var/*.log.")
                time.sleep(0.5)
    except Exception:
        for process in processes.values():
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                process.terminate()
        raise
    (log_dir / "local-processes.json").write_text(
        json.dumps({name: process.pid for name, process in processes.items()}), encoding="utf-8")
    print("Demo: http://127.0.0.1:6173")
    print("API: http://127.0.0.1:8001/docs")
    print("Logs and launcher PIDs: var/")


if __name__ == "__main__":
    main()
