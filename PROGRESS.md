# PROGRESS

Читать в начале каждой сессии.

## Текущий этап

**Milestone 1 — архитектура: выполнен, ждёт подтверждения человеком.** Дальше работа не продолжается без подтверждения (ТЗ §0.7).

## Сделано

* Структура каталогов (пустые каталоги с `.gitkeep`, кода нет).
* `docs/architecture.md`, `docs/data-flow.md`, `docs/database.md`, `docs/behavior.md`.
* `docs/decisions/` — ADR-001…006 (обязательные) и ADR-007…021 (решения там, где ТЗ молчит или противоречит себе).
* `.gitignore`, `README.md`.

## Проверено

* Ссылки между документами и на ADR существуют (скрипт-проверка).
* Код не запускался: его нет на этом этапе.

## Не проверено и почему

* Версии зависимостей не выбирались и не проверялись: в среде нет сети и `uv` ([ADR-020](docs/decisions/ADR-020-dependency-versions.md)).
* Соответствие параметров ByteTrack (`supervision`) требованиям ТЗ — проверяется тестами в Milestone 5 ([ADR-003](docs/decisions/ADR-003-person-tracking.md)).
* GPU и реальных камер нет; все оценки производительности — ориентиры, не измерения.

## Ключевые решения

* Worker не ходит в PostgreSQL: конфиг — через internal API, результаты — через Redis Streams, запись делает API ([ADR-002](docs/decisions/ADR-002-vision-worker-separation.md), [ADR-004](docs/decisions/ADR-004-event-bus.md)).
* Превью «JPEG + метаданные» отдаёт сам worker по WebSocket ([ADR-005](docs/decisions/ADR-005-video-streaming.md)).
* Событие идёт в pub/sub и в Stream одновременно ([ADR-017](docs/decisions/ADR-017-event-persistence.md)).
* Статусы событий без `RESOLVED` ([ADR-007](docs/decisions/ADR-007-event-statuses.md)); `PersonState` без `CROSSING_LINE` ([ADR-014](docs/decisions/ADR-014-person-states.md)).
* Mock-режим = mock-источник + scripted-детектор ([ADR-016](docs/decisions/ADR-016-mock-mode.md)).

## Известные проблемы / риски

* Cooldown по ключу «камера + track + тип» без zone_id при нескольких зонах может подавить вход во вторую зону в течение 3 с ([ADR-008](docs/decisions/ADR-008-cooldown.md)).
* Треки, активные при аварийном падении worker'а, не сохраняются ([ADR-019](docs/decisions/ADR-019-track-persistence.md)).
* `analytics_aggregates` с шагом 1 с растёт на ~0,7 млн строк/сутки при 8 камерах; роллап и retention — Milestone 10.

## Следующий шаг (после подтверждения)

Milestone 2: uv workspace (`pyproject.toml` в корне, `backend`, `vision-worker`, `shared`), каркас frontend (Vite + Vue 3 + TS), `docker-compose.yml` (postgres, redis; api/worker/frontend; mediamtx — profile), health-эндпоинты API и worker'а, проверки подключения к БД и Redis, Makefile с эквивалентами для PowerShell.
