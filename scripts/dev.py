"""Local developer launcher. Standard library only: uv installs the app later."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


def ensure_env(root: Path) -> bool:
    """Create a private local config once, never overwrite a user's config."""
    path = root / ".env"
    if path.exists():
        return False
    text = (
        (root / ".env.example")
        .read_text(encoding="utf-8")
        .replace("dev-worker-token-change-me", secrets.token_hex(32))
    )
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
        file.write(text)
    return True


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise StartupError(f"Required tool not found: {name}. See START_WINDOWS.md.")
    return found


def run(args: list[str], *, cwd: Path = ROOT, capture: bool = False) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed local developer commands, no shell
        args, cwd=cwd, text=True, stdout=subprocess.PIPE if capture else None, check=False
    )
    if result.returncode:
        raise StartupError(f"Step failed ({result.returncode}): {Path(args[0]).name}")
    return result.stdout or ""


def require_free_port(port: int) -> None:
    # A listening service matters; bind-only probes misreport recent TIME_WAIT sockets.
    with socket.socket() as probe:
        probe.settimeout(0.5)
        try:
            in_use = probe.connect_ex(("127.0.0.1", port)) == 0
        except OSError as exc:
            raise StartupError(f"Could not check local port {port}.") from exc
        if in_use:
            raise StartupError(
                f"Port {port} is already in use. Stop the previous app instance; "
                "the launcher will not kill unrelated processes."
            )


def wait_ready(url: str, child: subprocess.Popen[bytes], timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise StartupError("A service exited during startup. See the printed log directory.")
        try:
            with urlopen(url, timeout=2) as response:  # noqa: S310 -- loopback URL only
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.3)
    raise StartupError("Service readiness timed out. See the printed log directory.")


def stop_children(children: list[subprocess.Popen[bytes]]) -> None:
    """Only processes started by this invocation; leave Docker/data/other apps alone."""
    for child in reversed(children):
        if child.poll() is not None:
            continue
        try:
            if os.name == "nt":
                child.send_signal(
                    getattr(signal, "CTRL_BREAK_EVENT")  # noqa: B009 -- Windows-only attribute
                )
            else:
                os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            if os.name == "nt":
                subprocess.run(  # noqa: S603 -- fixed command, numeric owned PID
                    [executable("taskkill"), "/PID", str(child.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup-only", action="store_true", help="Prepare, check, migrate; do not run UI"
    )
    parser.add_argument(
        "--no-infra", action="store_true", help="Use already running local PG/Redis"
    )
    parser.add_argument(
        "--skip-install", action="store_true", help="Reuse an existing frozen installation"
    )
    args = parser.parse_args(argv)
    children: list[subprocess.Popen[bytes]] = []
    logs = []
    try:
        uv, node, npm = executable("uv"), executable("node"), executable("npm")
        # Validate pins, lockfile and supported Node before any install/network/DB changes.
        run([node, "scripts/check-toolchain.mjs"], cwd=ROOT / "frontend")
        docker = executable("docker") if not args.no_infra else None
        if docker:
            run([docker, "compose", "version"])
        print(
            "Created .env with a random worker token."
            if ensure_env(ROOT)
            else "Keeping existing .env unchanged.",
            flush=True,
        )
        if not args.skip_install:
            run([uv, "sync", "--frozen"])
            run([npm, "ci", "--include=dev"], cwd=ROOT / "frontend")
        python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.exists():
            raise StartupError("Missing .venv; rerun without --skip-install.")
        config = json.loads(run([str(python), "scripts/dev_check.py", "--config"], capture=True))
        ports = [config["api_port"], config["worker_port"], 5173]
        if len(set(ports)) != len(ports):
            raise StartupError("API, worker and frontend ports must be different.")
        for port in ports:
            require_free_port(port)
        if docker:
            run(
                [
                    docker,
                    "compose",
                    "up",
                    "-d",
                    "--wait",
                    "--wait-timeout",
                    "90",
                    "postgres",
                    "redis",
                ]
            )
        # Real protocol/auth checks, not just a container label or an open TCP port.
        run([str(python), "scripts/dev_check.py"])
        run(
            [
                uv,
                "run",
                "--frozen",
                "--no-sync",
                "alembic",
                "-c",
                "backend/alembic.ini",
                "upgrade",
                "head",
            ]
        )
        run([str(python), "scripts/dev_check.py", "--seed-if-empty"])
        run([uv, "run", "--frozen", "--no-sync", "ai-detector-model"])
        if args.setup_only:
            print("Setup PASS. Local databases remain running; no app processes started.")
            return 0
        directory = ROOT / "data/dev-logs" / time.strftime("%Y%m%d-%H%M%S")
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Service logs: {directory}", flush=True)
        env = os.environ.copy()
        env.update(
            {
                "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{config['api_port']}",
                "VITE_WORKER_PROXY_TARGET": f"http://127.0.0.1:{config['worker_port']}",
            }
        )

        def start(name: str, command: list[str], cwd: Path) -> subprocess.Popen[bytes]:
            file = (directory / f"{name}.log").open("wb")
            logs.append(file)
            child = subprocess.Popen(  # noqa: S603 -- fixed commands, no shell
                command,
                cwd=cwd,
                env=env,
                stdout=file,
                stderr=subprocess.STDOUT,
                creationflags=int(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")  # noqa: B009 -- Windows-only
                )
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
            children.append(child)
            return child

        api = start("api", [str(python), "-c", "from app.main import run; run()"], ROOT)
        wait_ready(f"http://127.0.0.1:{config['api_port']}/health/ready", api)
        worker = start(
            "worker", [str(python), "-c", "from vision_worker.main import run; run()"], ROOT
        )
        wait_ready(f"http://127.0.0.1:{config['worker_port']}/health/ready", worker)
        # Start node directly: no npm.cmd wrapper to orphan Vite on Windows.
        frontend = start(
            "frontend",
            [
                node,
                "node_modules/vite/bin/vite.js",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
            ],
            ROOT / "frontend",
        )
        wait_ready("http://127.0.0.1:5173", frontend)
        print(
            "READY: http://localhost:5173  |  Ctrl+C stops this app; Docker data is preserved.",
            flush=True,
        )
        while True:
            if any(child.poll() is not None for child in children):
                raise StartupError(
                    "A service stopped. See the log directory; other app services will stop."
                )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping app services...")
        return 0
    except (StartupError, OSError, ValueError) as exc:
        print(f"STARTUP STOPPED: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_children(children)
        for file in logs:
            file.close()


if __name__ == "__main__":
    raise SystemExit(main())
