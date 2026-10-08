# Build context: repository root. CPU image; the GPU variant is added in Milestone 12.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY shared/pyproject.toml shared/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
COPY vision-worker/pyproject.toml vision-worker/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace --package ai-detector-vision-worker

COPY shared shared
COPY vision-worker vision-worker
RUN uv sync --frozen --no-dev --package ai-detector-vision-worker

RUN useradd --system --uid 10001 app && mkdir -p /data/uploads && chown app /data/uploads
USER app
ENV WORKER_HTTP_HOST=0.0.0.0
EXPOSE 8001
CMD ["ai-detector-worker"]
