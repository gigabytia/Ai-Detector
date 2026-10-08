# Разработка

## Что нужно

| Инструмент | Версия | Зачем |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.12+ | Python 3.12 и зависимости (ставит Python сам) |
| Node.js | 22.22+ или 24.15+ | frontend |
| Docker Desktop | любой актуальный | PostgreSQL и Redis (минимум) |

`make` не обязателен: у каждой команды есть эквивалент для PowerShell. Команды одинаковые в PowerShell, bash и cmd, кроме копирования файла.

## Первый запуск без Docker для приложений (Windows и Linux)

```powershell
Copy-Item .env.example .env          # bash: cp .env.example .env
uv sync
npm --prefix frontend ci
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
```

Затем в трёх терминалах:

```powershell
uv run ai-detector-api               # http://localhost:8000/docs
uv run ai-detector-worker            # http://localhost:8001/health/ready
npm --prefix frontend run dev        # http://localhost:5173
```

Откройте http://localhost:5173/settings: база данных и Redis — «Доступно», в «Обработчики видео» — ваш `WORKER_ID`.

## Полностью в Docker

```powershell
docker compose up --build            # frontend: http://localhost:8080
docker compose --profile media up    # + MediaMTX (Уровень 3)
```

## Команды

| make | PowerShell / любой shell |
|---|---|
| `make install` | `uv sync; npm --prefix frontend ci` |
| `make infra` | `docker compose up -d postgres redis` |
| `make up` / `make down` | `docker compose up --build` / `docker compose down` |
| `make migrate` | `uv run alembic -c backend/alembic.ini upgrade head` |
| `make api` | `uv run ai-detector-api` |
| `make worker` | `uv run ai-detector-worker` |
| `make frontend` | `npm --prefix frontend run dev` |
| `make test` | `uv run pytest; npm --prefix frontend test` |
| `make test-integration` | `uv run pytest -m integration` (нужны запущенные PostgreSQL и Redis) |
| `make lint` | `uv run ruff check .; uv run ruff format --check .; uv run mypy shared/src backend/src vision-worker/src tests; npm --prefix frontend run lint; npm --prefix frontend run format:check; npm --prefix frontend run typecheck` |
| `make fmt` | `uv run ruff check --fix .; uv run ruff format .; npm --prefix frontend run format` |
| `make api-types` | `uv run ai-detector-openapi frontend/openapi.json; npm --prefix frontend run api:types` |
| `make build` | `npm --prefix frontend run build` |

## Контракт API

После изменения схем backend выполните `make api-types` и закоммитьте `frontend/openapi.json` и `frontend/src/api/generated.ts`. CI падает, если они устарели ([ADR-018](decisions/ADR-018-frontend-api-types.md)).

## Тесты

* `tests/unit` — без внешних сервисов, запускаются по умолчанию.
* `tests/integration` — реальные PostgreSQL и Redis по `DATABASE_URL` / `REDIS_URL`. Если сервис недоступен, тест **падает**, а не пропускается.
* `frontend/src/**/*.test.ts` — Vitest.

## Миграции

```powershell
uv run alembic -c backend/alembic.ini revision --autogenerate -m "create cameras"
uv run alembic -c backend/alembic.ini upgrade head
```
Имена миграций — на английском.
