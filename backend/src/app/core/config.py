"""API settings. Reading settings has no side effects (no directories, no output)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://ai_detector:ai_detector@localhost:5432/ai_detector"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Shared secret for /api/v1/internal/worker/*; internal endpoints answer 503 when unset.
    worker_api_token: SecretStr | None = None

    max_cameras: int = Field(default=8, ge=1)
    upload_path: Path = Path("data/uploads")
    upload_max_bytes: int = Field(default=2 * 1024**3, ge=1)
    upload_allowed_extensions: Annotated[list[str], NoDecode] = [".mp4", ".mov", ".mkv", ".avi"]

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator("cors_origins", "upload_allowed_extensions", mode="before")
    @classmethod
    def _split_lists(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("cors_origins")
    @classmethod
    def _forbid_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins, '*' is not allowed")
        return value

    @field_validator("upload_allowed_extensions")
    @classmethod
    def _normalize_extensions(cls, value: list[str]) -> list[str]:
        allowed = {".mp4", ".mov", ".mkv", ".avi"}
        normalized = [
            item.lower() if item.startswith(".") else f".{item.lower()}" for item in value
        ]
        unknown = set(normalized) - allowed
        if unknown:
            raise ValueError(f"unsupported upload extensions: {sorted(unknown)}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
