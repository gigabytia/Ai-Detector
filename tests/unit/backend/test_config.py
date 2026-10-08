import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_wildcard_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError, match="explicit origins"):
        Settings(_env_file=None)


def test_database_url_requires_asyncpg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    with pytest.raises(ValidationError, match="asyncpg"):
        Settings(_env_file=None)
