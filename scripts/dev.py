"""Run the complete local CIL workspace with supervised child services."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
children: list[subprocess.Popen] = []


def newest(path: Path) -> float:
    return max((item.stat().st_mtime for item in path.rglob("*") if item.is_file()), default=0)


def build_workbench() -> None:
    source = ROOT / "data-formulator-main" / "src"
    output = ROOT / "data-formulator-main" / "py-src" / "data_formulator" / "dist" / "index.html"
    if output.is_file() and output.stat().st_mtime >= newest(source):
        return
    env = {**os.environ, "CIL_EMBEDDED": "true"}
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "data-formulator-main", env=env, check=True)


def start(name: str, command: list[str], cwd: Path = ROOT) -> subprocess.Popen:
    print(f"Starting {name}…", flush=True)
    process = subprocess.Popen(command, cwd=cwd, start_new_session=True)
    children.append(process)
    return process


def wait_for(url: str, name: str, headers: dict[str, str] | None = None) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in children):
            raise RuntimeError(f"{name} could not start because a workspace process exited.")
        try:
            with urlopen(Request(url, headers=headers or {}), timeout=2) as response:
                if response.status == 200:
                    print(f"{name} ready", flush=True)
                    return
        except Exception:
            time.sleep(.25)
    raise RuntimeError(f"{name} did not become ready within 30 seconds.")


def stop(*_args) -> None:
    for process in reversed(children):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 5
    for process in reversed(children):
        if process.poll() is None:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    raise SystemExit(0)


def main() -> None:
    if not PYTHON.is_file():
        raise SystemExit("Create .venv and install the locked backend/integration requirements first.")
    config = dotenv_values(ROOT / ".env")
    secret = config.get("DF_BRIDGE_SECRET") or ""
    if len(secret) < 32:
        raise SystemExit("Set DF_BRIDGE_SECRET to at least 32 random characters in .env.")
    build_workbench()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        start("analytics engine", [str(PYTHON), "integration/run_data_formulator.py"])
        wait_for("http://127.0.0.1:5567/cil/health", "Analytics engine", {
            "X-CIL-Bridge": secret,
            "X-CIL-User": "startup_check",
            "X-Workspace-Id": "startup",
        })
        start("CIL API", [str(PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000"])
        wait_for("http://127.0.0.1:8000/health", "CIL API")
        start("web app", ["npm", "run", "dev", "--prefix", "frontend", "--", "--host", "127.0.0.1"])
        wait_for("http://127.0.0.1:5173/", "Web app")
        print("\nCIL workspace ready: http://127.0.0.1:5173/\nPress Ctrl+C to stop every service.", flush=True)
        while True:
            for process in children:
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"A workspace process exited with status {code}.")
            time.sleep(.5)
    except (KeyboardInterrupt, RuntimeError) as exc:
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
        stop()


if __name__ == "__main__":
    main()
