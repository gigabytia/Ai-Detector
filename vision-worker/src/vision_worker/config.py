"""Worker settings. Reading settings has no side effects."""

import socket
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    # Stable id across restarts of the same deployment; hostname is unique per container.
    worker_id: str = Field(default_factory=socket.gethostname, min_length=1, max_length=128)
    worker_http_host: str = "127.0.0.1"
    worker_http_port: int = Field(default=8001, ge=1, le=65535)

    api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    worker_api_token: SecretStr | None = None
    snapshot_path: Path = Path("data/snapshots")
    upload_path: Path = Path("data/uploads")
    model_manifest_path: Path = Path("models/person-detector/manifest.yaml")
    inference_device: Literal["auto", "cpu", "cuda"] = "auto"
    inference_batch_size: int = Field(default=4, ge=1, le=32)
    inference_max_wait_ms: float = Field(default=20, ge=0, le=1000)
    inference_threads: int = Field(default=2, ge=1, le=64)
    detection_iou: float = Field(default=0.45, gt=0, le=1)
    line_hysteresis: float = Field(default=0.01, gt=0, le=0.1)
    severity_line_cross: Literal["critical", "warning", "info"] = "warning"
    severity_loitering: Literal["critical", "warning", "info"] = "warning"
    severity_zone_enter: Literal["critical", "warning", "info"] = "critical"
    event_min_track_hits: int = Field(default=3, ge=1, le=1000)
    person_track_max_age: int = Field(default=25, ge=1, le=1000)
    track_match_iou: float = Field(default=0.5, gt=0, le=1)
    track_activation_confidence: float = Field(default=0.25, gt=0, le=1)
    preview_fps: float = Field(default=5, gt=0, le=30)
    preview_max_width: int = Field(default=640, ge=64, le=1920)
    preview_allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ]

    reconcile_interval_seconds: float = Field(default=30, ge=1, le=300)

    reconnect_initial_delay_seconds: float = Field(default=1.0, gt=0)
    reconnect_max_delay_seconds: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _check_backoff(self) -> "WorkerSettings":
        if self.reconnect_max_delay_seconds < self.reconnect_initial_delay_seconds:
            raise ValueError("RECONNECT_MAX_DELAY_SECONDS must be >= the initial delay")
        return self


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
