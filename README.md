# AI Detector v2

Система видеонаблюдения: детекция и трекинг **людей**, события входа в опасную зону, пересечения линии и долгого нахождения в зоне, интерфейс оператора.

**Статус:** Milestone 2 — инфраструктура: API, vision worker, frontend, PostgreSQL, Redis, health-проверки. Камер, детекции и событий пока нет. Подробности — [PROGRESS.md](PROGRESS.md).

## Архитектура

Frontend (Vue 3) ↔ API (FastAPI) ↔ PostgreSQL / Redis ↔ Vision worker. Inference — только в worker'е. Подробно: [architecture.md](docs/architecture.md), [data-flow.md](docs/data-flow.md), [database.md](docs/database.md), [behavior.md](docs/behavior.md), [решения](docs/decisions/README.md).

## Быстрый старт

```powershell
Copy-Item .env.example .env        # bash: cp .env.example .env
uv sync; npm --prefix frontend ci
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
uv run ai-detector-api             # терминал 1
uv run ai-detector-worker          # терминал 2
npm --prefix frontend run dev      # терминал 3 → http://localhost:5173
```
Или всё в Docker: `docker compose up --build` → http://localhost:8080.

## Окружение и команды

Переменные — [.env.example](.env.example). Все команды (make и PowerShell), тесты и миграции — [docs/development.md](docs/development.md). API — [docs/api.md](docs/api.md).

## Камеры и модели

Появятся в Milestone 3–4.

Техническое задание: [AI_DETECTOR_v2_MASTER_PROMPT.md](AI_DETECTOR_v2_MASTER_PROMPT.md).
