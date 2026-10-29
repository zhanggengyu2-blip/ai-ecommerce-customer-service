"""Manage the project's Windows-native, localhost-only OpenSearch installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.request import build_opener, ProxyHandler
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "3.8.0"
HOME = ROOT / "var" / f"opensearch-{VERSION}"
ARCHIVE = ROOT / "var/opensearch-downloads" / f"opensearch-{VERSION}-windows-x64.zip"
# SHA-512 published by artifacts.opensearch.org for this exact Windows release.
SHA512 = "1aeb41a2c478b5bc0fe4152300b00997450189551866cb46674891cb40611a250aa8f70f8d69417f273859a6079749930128303a7fedd5f8d9c778e226bbc4e0"
RECORD = ROOT / "var/opensearch-process.json"
HTTP = build_opener(ProxyHandler({}))


def health():
    with HTTP.open("http://127.0.0.1:9200", timeout=3) as response:
        info = json.load(response)
    if info.get("cluster_name") != "agentserve-local" or info.get("version", {}).get("number") != VERSION:
        raise RuntimeError("Port 9200 belongs to a different OpenSearch instance")
    with HTTP.open("http://127.0.0.1:9200/_cluster/health", timeout=3) as response:
        result = json.load(response)
    if result["status"] == "red":
        raise RuntimeError("OpenSearch cluster is red; inspect its logs")
    return {"version": VERSION, "cluster": info["cluster_name"], "health": result["status"]}


def install():
    if not ARCHIVE.is_file():
        raise RuntimeError(f"Download the official archive to {ARCHIVE} first")
    digest = hashlib.sha512()
    with ARCHIVE.open("rb") as archive:
        for block in iter(lambda: archive.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != SHA512:
        raise RuntimeError("Archive SHA-512 mismatch; extraction refused")
    print("Official archive SHA-512 verified", flush=True)
    marker = HOME / ".agentserve-install.json"
    if marker.is_file():
        print(f"Already installed: {HOME}")
        return
    destination = (ROOT / "var").resolve()
    with zipfile.ZipFile(ARCHIVE) as archive:
        for entry in archive.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(HOME.resolve()):
                raise RuntimeError("Unexpected archive extraction path")
        archive.extractall(destination)
    if not (HOME / "jdk/bin/java.exe").is_file() or not (HOME / "bin/opensearch.bat").is_file():
        raise RuntimeError("Archive does not contain the expected Windows installation")
    config_path = HOME / "config/opensearch.yml"
    backup = config_path.with_suffix(".yml.vendor.bak")
    if not backup.exists():
        backup.write_bytes(config_path.read_bytes())
    config_path.write_text("\n".join([
        "cluster.name: agentserve-local", "node.name: agentserve-windows",
        "network.host: 127.0.0.1", "http.port: 9200", "transport.port: 9300",
        "discovery.type: single-node", "plugins.security.disabled: true", "",
    ]), encoding="utf-8")
    jvm_path = HOME / "config/jvm.options"
    jvm_text = jvm_path.read_text(encoding="utf-8")
    jvm_text = re.sub(r"(?m)^-Xms\S+", "-Xms1g", jvm_text)
    jvm_text = re.sub(r"(?m)^-Xmx\S+", "-Xmx1g", jvm_text)
    jvm_path.write_text(jvm_text, encoding="utf-8")
    marker.write_text(json.dumps({"version": VERSION, "sha512": SHA512}), encoding="utf-8")
    print(f"Installed with bundled JDK and 1 GB heap: {HOME}", flush=True)


def start():
    if os.name != "nt":
        raise RuntimeError("This launcher is for Windows")
    if not (HOME / ".agentserve-install.json").is_file():
        raise RuntimeError("Run install first")
    for port in (9200, 9300):
        with socket.socket() as connection:
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is occupied; existing service was not stopped")
    env = dict(os.environ)
    env["OPENSEARCH_JAVA_HOME"] = str(HOME / "jdk")
    env.pop("OPENSEARCH_JAVA_OPTS", None)
    env.pop("SSLKEYLOGFILE", None)
    with (ROOT / "var/opensearch.stdout.log").open("w") as stdout, \
            (ROOT / "var/opensearch.stderr.log").open("w") as stderr:
        process = subprocess.Popen(["cmd.exe", "/d", "/c", str(HOME / "bin/opensearch.bat")], cwd=HOME,
                                   env=env, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    RECORD.write_text(json.dumps({"pid": process.pid, "home": str(HOME), "version": VERSION}), encoding="utf-8")
    print(f"OpenSearch launcher PID {process.pid}; waiting for readiness", flush=True)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("OpenSearch exited; inspect var/opensearch.stderr.log and installation logs/")
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
    if Path(record["home"]).resolve() != HOME.resolve():
        raise RuntimeError("Launcher record does not match project installation")
    pid = int(record["pid"])
    # Protect against a recycled PID before stopping this process tree.
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        print("Project OpenSearch launcher is already stopped")
        return
    info = json.loads(result.stdout)
    if str(HOME).lower() not in (info.get("CommandLine") or "").lower():
        raise RuntimeError("Process identity mismatch; stop refused")
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True, capture_output=True)
    print("Project OpenSearch stopped; data retained")


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
