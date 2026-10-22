"""Launcher orchestration without Docker, a real Windows OS, or user data."""

import importlib.util
import json
import socket
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def dev() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/dev.py"
    spec = importlib.util.spec_from_file_location("dev_launcher_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_env_created_once_with_private_random_token(dev: ModuleType, tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("WORKER_API_TOKEN=dev-worker-token-change-me\n")
    assert dev.ensure_env(tmp_path)
    first = (tmp_path / ".env").read_bytes()
    assert b"dev-worker-token-change-me" not in first
    assert len(first.split(b"=")[1].strip()) == 64
    assert not dev.ensure_env(tmp_path)
    assert (tmp_path / ".env").read_bytes() == first


def test_existing_env_not_modified(dev: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_bytes(b"REDIS_URL=redis://localhost:1234/5\r\n# custom\r\n")
    before = path.read_bytes()
    assert not dev.ensure_env(tmp_path)
    assert path.read_bytes() == before


def configure_fake_setup(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "executable", lambda name: name)
    monkeypatch.setattr(dev, "require_free_port", lambda port: None)
    (tmp_path / ".env.example").write_text("WORKER_API_TOKEN=dev-worker-token-change-me\n")
    python = tmp_path / ".venv" / ("Scripts/python.exe" if dev.os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> str:
        calls.append(args)
        if kwargs.get("capture"):
            return json.dumps({"api_port": 8000, "worker_port": 8001})
        return ""

    monkeypatch.setattr(dev, "run", run)
    return calls


def test_setup_orders_infra_protocol_checks_migration_seed_model(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = configure_fake_setup(dev, tmp_path, monkeypatch)
    assert dev.main(["--setup-only"]) == 0
    commands = [" ".join(c) for c in calls]
    assert any(c == "npm ci --include=dev" for c in commands)
    infra = next(i for i, c in enumerate(commands) if "compose up" in c)
    protocol = next(i for i, c in enumerate(commands) if c.endswith("scripts/dev_check.py"))
    migration = next(i for i, c in enumerate(commands) if "alembic" in c)
    seed = next(i for i, c in enumerate(commands) if c.endswith("--seed-if-empty"))
    model = next(i for i, c in enumerate(commands) if "ai-detector-model" in c)
    assert infra < protocol < migration < seed < model


def test_no_infra_does_not_run_docker(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = configure_fake_setup(dev, tmp_path, monkeypatch)
    assert dev.main(["--setup-only", "--no-infra", "--skip-install"]) == 0
    assert not any(c[0] in {"docker", "npm"} for c in calls)


def test_failed_redis_preflight_prevents_migration_and_app_start(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = configure_fake_setup(dev, tmp_path, monkeypatch)
    original = dev.run

    def run(args: list[str], **kwargs: Any) -> str:
        if args[-1] == "scripts/dev_check.py":
            raise dev.StartupError("Redis unavailable")
        return str(original(args, **kwargs))

    monkeypatch.setattr(dev, "run", run)
    assert dev.main(["--setup-only"]) == 1
    assert not any("alembic" in c for c in calls)


def test_toolchain_failure_does_not_create_env_or_touch_infra(
    dev: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(dev, "executable", lambda name: name)

    def fail(*args: object, **kwargs: object) -> str:
        raise dev.StartupError("Unsupported Node")

    monkeypatch.setattr(dev, "run", fail)
    assert dev.main([]) == 1
    assert not (tmp_path / ".env").exists()


def test_busy_port_is_reported_without_killing_processes(dev: ModuleType) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        with pytest.raises(dev.StartupError, match="already in use"):
            dev.require_free_port(sock.getsockname()[1])


def test_readiness_detects_child_exit(dev: ModuleType) -> None:
    child = SimpleNamespace(poll=lambda: 1)
    with pytest.raises(dev.StartupError, match="exited"):
        dev.wait_ready("http://127.0.0.1:1", child)


def test_windows_cleanup_targets_only_owned_process_tree(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[int] = []
    commands: list[list[str]] = []
    waits = 0

    def wait(timeout: int) -> None:
        nonlocal waits
        waits += 1
        if waits == 1:
            raise subprocess.TimeoutExpired("owned", timeout)

    child = SimpleNamespace(pid=12345, poll=lambda: None, send_signal=sent.append, wait=wait)
    monkeypatch.setattr(dev, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(dev, "signal", SimpleNamespace(CTRL_BREAK_EVENT=1))
    monkeypatch.setattr(dev, "executable", lambda name: name)
    monkeypatch.setattr(dev.subprocess, "run", lambda args, **kwargs: commands.append(args))
    dev.stop_children([child])
    assert sent == [1]
    assert commands == [["taskkill", "/PID", "12345", "/T", "/F"]]


def test_recently_closed_listener_does_not_block_restart(dev: ModuleType) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        with socket.create_connection(("127.0.0.1", port)):
            connection, _ = listener.accept()
            connection.close()
    dev.require_free_port(port)
