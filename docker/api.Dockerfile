# Build context: repository root.
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY shared/pyproject.toml shared/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY vision-worker/pyproject.toml vision-worker/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package ai-detector-backend

COPY shared shared
COPY backend backend
RUN uv sync --frozen --no-dev --package ai-detector-backend

RUN useradd --system --uid 10001 app && mkdir -p /data/uploads && chown app /data/uploads
USER app
WORKDIR /app/backend
ENV API_HOST=0.0.0.0
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && ai-detector-api"]
