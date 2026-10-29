"""Manage the project's Windows-native OpenSearch Dashboards on localhost:5601."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import socket
import subprocess
import time
from urllib.request import Request
import zipfile
from opensearch_native import ROOT, VERSION, HTTP, health as search_health

INSTALL_DIR = ROOT / "var" / f"opensearch-dashboards-{VERSION}"
ARCHIVE = ROOT / "var/opensearch-downloads" / f"opensearch-dashboards-{VERSION}-windows-x64.zip"
SHA512 = "38d372744a0ad666381584fdde7aeb425c2a5744a4483c63adc6a738344d04e413a93f011eb38268347ed6f147a25c784f2b334c3c2e16e5577ce36e2fa05e7d"
RECORD = ROOT / "var/dashboards-process.json"


def health():
    with HTTP.open(Request("http://127.0.0.1:5601/api/status", headers={"osd-xsrf": "agentserve"}), timeout=5) as response:
        info = json.load(response)
    if info.get("name") != "agentserve-dashboards" or info.get("version", {}).get("number") != VERSION:
        raise RuntimeError("Port 5601 belongs to another Dashboards instance")
    overall = info.get("status", {}).get("overall", {})
    state = overall.get("state") or overall.get("level")
    if state not in ("green", "available"):
        raise RuntimeError(f"Dashboards is not ready: {state}")
    return {"version": VERSION, "status": state, "url": "http://127.0.0.1:5601"}


def install():
    if not ARCHIVE.is_file():
        raise RuntimeError(f"Download the official archive to {ARCHIVE} first")
    digest = hashlib.sha512()
    with ARCHIVE.open("rb") as archive:
        for block in iter(lambda: archive.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != SHA512:
        raise RuntimeError("Archive SHA-512 mismatch; extraction refused")
    print("Official Dashboards archive SHA-512 verified", flush=True)
    marker = INSTALL_DIR / ".agentserve-install.json"
    if marker.is_file():
        print(f"Already installed: {INSTALL_DIR}")
        return
    destination = (ROOT / "var").resolve()
    installation_root = INSTALL_DIR.resolve()
    with zipfile.ZipFile(ARCHIVE) as archive:
        entries = archive.infolist()
        for entry in entries:
            relative = PurePosixPath(entry.filename.replace("\\", "/"))
            if (relative.is_absolute() or any(part == ".." or ":" in part for part in relative.parts)
                    or not (destination / Path(*relative.parts)).is_relative_to(installation_root)):
                raise RuntimeError("Unexpected archive extraction path")
        # Namespaced Windows paths avoid changing the machine's long-path registry setting.
        extraction_path = "\\\\?\\" + str(destination) if os.name == "nt" else str(destination)
        for index, entry in enumerate(entries, 1):
            archive.extract(entry, extraction_path)
            if index % 10000 == 0:
                print(f"Extracted {index}/{len(entries)} entries", flush=True)
    if not (INSTALL_DIR / "bin/opensearch-dashboards.bat").is_file():
        raise RuntimeError("Expected Windows launcher is missing")
    config_path = INSTALL_DIR / "config/opensearch_dashboards.yml"
    backup = config_path.with_suffix(".yml.vendor.bak")
    if not backup.exists():
        backup.write_bytes(config_path.read_bytes())
    config_path.write_text("\n".join([
        "server.name: agentserve-dashboards", "server.host: 127.0.0.1", "server.port: 5601",
        'opensearch.hosts: ["http://127.0.0.1:9200"]', "",
    ]), encoding="utf-8")
    # Match the localhost development search cluster with Security disabled.
    plugin = (INSTALL_DIR / "plugins/securityDashboards").resolve()
    disabled = (INSTALL_DIR / "disabled-plugins/securityDashboards").resolve()
    if not plugin.is_relative_to(INSTALL_DIR.resolve()) or not disabled.is_relative_to(INSTALL_DIR.resolve()):
        raise RuntimeError("Plugin move is outside this installation")
    if plugin.exists():
        if disabled.exists():
            raise RuntimeError("Disabled plugin backup already exists; move refused")
        disabled.parent.mkdir(exist_ok=True)
        plugin.rename(disabled)
    marker.write_text(json.dumps({"version": VERSION, "sha512": SHA512}), encoding="utf-8")
    print(f"Installed localhost Dashboards: {INSTALL_DIR}", flush=True)


def start():
    if os.name != "nt":
        raise RuntimeError("This launcher is for Windows")
    if not (INSTALL_DIR / ".agentserve-install.json").is_file():
        raise RuntimeError("Run install first")
    search_health()
    with socket.socket() as connection:
        if connection.connect_ex(("127.0.0.1", 5601)) == 0:
            raise RuntimeError("Port 5601 is occupied; existing service was not stopped")
    env = dict(os.environ)
    env["OSD_NODE_HOME"] = str(INSTALL_DIR / "node")
    env["OSD_PATH_CONF"] = str(INSTALL_DIR / "config")
    env.pop("NODE_OPTIONS", None)
    env.pop("SSLKEYLOGFILE", None)
    with (ROOT / "var/dashboards.stdout.log").open("w") as stdout, \
            (ROOT / "var/dashboards.stderr.log").open("w") as stderr:
        process = subprocess.Popen(["cmd.exe", "/d", "/c", str(INSTALL_DIR / "bin/opensearch-dashboards.bat")],
                                   cwd=INSTALL_DIR, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    RECORD.write_text(json.dumps({"pid": process.pid, "directory": str(INSTALL_DIR), "version": VERSION}), encoding="utf-8")
    print(f"Dashboards launcher PID {process.pid}; waiting for readiness", flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Dashboards exited; inspect var/dashboards.stderr.log and stdout.log")
        try:
            result = health()
        except (OSError, ValueError, RuntimeError):
            time.sleep(1)
        else:
            print(json.dumps(result))
            return
    raise RuntimeError("Startup exceeded 180 seconds; process retained for diagnosis, inspect logs")


def stop():
    if not RECORD.is_file():
        raise RuntimeError("No project launcher record")
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if Path(record["directory"]).resolve() != INSTALL_DIR.resolve():
        raise RuntimeError("Launcher record does not match this installation")
    pid = int(record["pid"])
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        print("Project Dashboards launcher is already stopped")
        return
    info = json.loads(result.stdout)
    if str(INSTALL_DIR).lower() not in (info.get("CommandLine") or "").lower():
        raise RuntimeError("Process identity mismatch; stop refused")
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True, capture_output=True)
    print("Project Dashboards stopped; search data retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["install", "start", "stop", "status"])
    args = parser.parse_args()
    try:
        if args.command == "status":
            print(json.dumps(health()))
        else:
            globals()[args.command]()
    except Exception as exc:
        raise SystemExit(str(exc)) from None
