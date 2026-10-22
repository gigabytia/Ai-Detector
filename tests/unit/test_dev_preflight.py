"""Real settings, but no connection to any user service."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from app.core.config import Settings
from vision_worker.config import WorkerSettings


@pytest.fixture
def doctor() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/dev_check.py"
    spec = importlib.util.spec_from_file_location("dev_check_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings() -> tuple[Settings, WorkerSettings]:
    return Settings(_env_file=None, worker_api_token="test-local"), WorkerSettings(
        _env_file=None, worker_api_token="test-local"
    )


def test_local_defaults_use_ipv4_redis(doctor: ModuleType) -> None:
    api, worker = settings()
    assert api.redis_url.host == worker.redis_url.host == "127.0.0.1"
    assert doctor.local_config(api, worker) == {"api_port": 8000, "worker_port": 8001}


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_host", "0.0.0.0"),  # noqa: S104 -- verify public bind is rejected
        ("redis_url", "redis://remote.invalid/0"),
        ("worker_api_token", None),
    ],
)
def test_reject_unsafe_or_incomplete_local_configuration(
    doctor: ModuleType, field: str, value: str | None
) -> None:
    api, worker = settings()
    api = Settings.model_validate({**api.model_dump(), field: value})
    with pytest.raises(ValueError):
        doctor.local_config(api, worker)


def test_worker_api_port_mismatch_is_clear(doctor: ModuleType) -> None:
    api, worker = settings()
    worker.api_base_url = type(worker.api_base_url)("http://127.0.0.1:1234")
    with pytest.raises(ValueError, match="API_BASE_URL"):
        doctor.local_config(api, worker)


async def test_redis_failure_is_sanitized(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from types import SimpleNamespace

    async def ping() -> None:
        raise RuntimeError("redis://private-password@127.0.0.1")

    async def close() -> None:
        pass

    monkeypatch.setattr(
        doctor,
        "Redis",
        SimpleNamespace(from_url=lambda *a, **kw: SimpleNamespace(ping=ping, aclose=close)),
    )
    api, _ = settings()
    assert not await doctor.check(api, False)
    error = capsys.readouterr().err
    assert "Redis unavailable" in error and "private-password" not in error
