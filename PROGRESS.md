# PROGRESS

Читать в начале каждой сессии.

## Текущий этап

**Milestone 2 — инфраструктура: выполнен.** Следующий — Milestone 3 (камеры).

## Сделано

### Milestone 1 — архитектура (подтверждено человеком)
* Документы `docs/architecture.md`, `data-flow.md`, `database.md`, `behavior.md`, ADR-001…021.

### Milestone 2 — инфраструктура
* uv workspace: `shared` (`ai_detector_core`), `backend` (`app`), `vision-worker` (`vision_worker`); `uv.lock`.
* `shared`: `Clock`, `WorkerHeartbeat`, имена Redis-ключей, JSON-логирование (stdlib).
* API: настройки (pydantic-settings, CORS без `*`, только `postgresql+asyncpg`), JSON-логи, lifespan с engine/Redis, `/health/live`, `/health/ready` (БД + Redis, 503 при отказе), `GET /api/v1/system/status` (зависимости + живые worker'ы), единый формат ошибок, Alembic (async, без миграций — таблицы с Milestone 3), экспорт OpenAPI.
* Worker: `Supervisor`, heartbeat в Redis раз в 1 с с TTL 5 с, HTTP `/health/live`, `/health/ready`, штатная остановка удаляет heartbeat.
* Frontend: Vite + Vue 3 + TS, Pinia, Vue Query, vue-i18n (ru), Tailwind 4, shadcn-vue (Button), Lucide; маршруты `/monitoring`, `/events`, `/analytics`, `/cameras`, `/settings`; светлая/тёмная (графит) темы; индикатор состояния системы и панель на «Настройках»; типы API из OpenAPI.
* Docker: Dockerfile api/worker/frontend, nginx (same-origin `/api`, `/health`, `/live`), `docker-compose.yml` (mediamtx — profile `media`).
* `Makefile` + эквиваленты PowerShell (`docs/development.md`), `.env.example`, CI (`.github/workflows/ci.yml`), `docs/api.md`.
* ADR-022 (TypeScript 5.9), ADR-023 (HTTP worker'а на FastAPI).

## Проверено (в песочнице агента: Linux x86_64, Python 3.12.15, Node 24.14.1, CPU, без Docker)

| Проверка | Результат |
|---|---|
| `uv run pytest` | 13 passed |
| `uv run pytest -m integration` (PostgreSQL 17 + Valkey 9 из пакетов ОС) | 4 passed |
| `ruff check`, `ruff format --check`, `mypy --strict` | без ошибок |
| `npm run lint` / `format:check` / `typecheck` / `test` / `build` | без ошибок, 7 тестов Vitest |
| Живой запуск API + worker | ready 200; system status показывает worker'а |
| Отключение Redis | API и worker ready → 503, статус `degraded`, ошибка в логе worker'а один раз; после возврата Redis — восстановление без перезапуска |
| SIGTERM worker'у | штатная остановка, heartbeat-ключ удалён |
| UI `/settings` через Vite proxy | скриншоты светлой и тёмной темы, данные с API |
| Шаги `uv sync` из Dockerfile api/worker | выполнены вне Docker; `alembic upgrade head` работает; образ worker'а не содержит `app` |

## Не проверено и почему

* `docker compose build/up` и CI на GitHub не запускались — в песочнице нет Docker и GitHub Actions. YAML compose и CI только распарсен.
* Интеграционные тесты шли на PostgreSQL 17 и Valkey 9 (совместим с Redis), а в compose/CI указаны `postgres:18-alpine` и `redis:8.8-alpine`.
* Сборка проверялась на Node 24.14.1; часть dev-зависимостей просит ≥ 24.15 (только предупреждения).
* Windows не проверялся (нет машины); команды в `docs/development.md` кроссплатформенные, кроме копирования `.env`.

## Версии

Проверены по PyPI/npm/Docker Hub на 2026-10-08 и зафиксированы в `uv.lock` и `frontend/package-lock.json`. Исключение — TypeScript 5.9 вместо 7.0 ([ADR-022](docs/decisions/ADR-022-typescript-version.md)).

## Ключевые решения

* Worker не ходит в PostgreSQL ([ADR-002](docs/decisions/ADR-002-vision-worker-separation.md), [ADR-004](docs/decisions/ADR-004-event-bus.md)); превью — из worker'а ([ADR-005](docs/decisions/ADR-005-video-streaming.md)); событие — в pub/sub и Stream одновременно ([ADR-017](docs/decisions/ADR-017-event-persistence.md)).
* Интеграционные тесты исключены из обычного `pytest` и при недоступном сервисе падают, а не пропускаются.

## Известные проблемы / риски

* `StarletteDeprecationWarning`: TestClient на `httpx` объявлен устаревшим в пользу `httpx2`; на работу не влияет, перейти при обновлении FastAPI.
* Риски из Milestone 1 актуальны: cooldown без zone_id ([ADR-008](docs/decisions/ADR-008-cooldown.md)), потеря активных треков при аварии worker'а ([ADR-019](docs/decisions/ADR-019-track-persistence.md)), рост `analytics_aggregates`.
* ECharts, Playwright, Prometheus-метрики ещё не подключены — появятся вместе с функциями (Milestone 10, Уровень 3).

## Следующий шаг

Milestone 3: таблицы `cameras`, `camera_configs` (первая миграция), CRUD камер, загрузка видео, `FrameSource` (file + mock), `CameraSession` с lifecycle и reconnect, команды start/stop/restart через Redis, статус камер в UI.
