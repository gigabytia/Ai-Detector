"""Integration tests use real PostgreSQL and Redis from DATABASE_URL / REDIS_URL.

They are excluded from the default run; start them with `pytest -m integration`.
A missing service fails the test instead of skipping it.
"""

import os

import pytest

from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://ai_detector:ai_detector@localhost:5432/ai_detector",
        ),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    )
