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
    upload_path: Path = Path("data/uploads")

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
