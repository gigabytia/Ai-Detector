# QA — Milestone 7

Linux x86_64, Python 3.12.15/uv, PostgreSQL 17.10, Valkey 9.0.5, CPU; Node 24.14.1 ниже package.json engine (использовать поддерживаемую версию). Исходный M6 из полного архива с историей Git восстановлен и проверен по SHA-256.

## Автоматические проверки

* `make-check.log`: ruff check/format, mypy strict (144 файла), ESLint/Prettier/vue-tsc, **163 unit Python / 97 Vitest**, production build.
* `integration.log`: **23 passed** на настоящих PostgreSQL/Valkey. UUID duplicate и сохранность note/status при retry; потерянный ACK после commit; ошибка БД оставляет PEL; настоящий run() автоматически забирает abandoned entry с idle >30 с (тест задаёт idle через XCLAIM); poison/unknown-camera → dead letter без блокировки валидных событий; pub/sub alarm до записи; history/keyset/filter/audit/soft delete; конкурирующие операторы дают 200+409.
* `migration-roundtrip.log`: upgrade с M6/пустой схемы, downgrade на отдельной тестовой БД и upgrade; alembic check — без diff. `alembic-check.log` — текущая схема. `lock-check.log`; повторный OpenAPI export совпал с frontend/openapi.json, TS regenerated.
* `npm-audit-production.json`: **0 production vulnerabilities**. Полный dev-audit не повторялся; прежний риск dev-зависимостей из PROGRESS остаётся.

## Живые проверки

* `postgres-outage.log`: PostgreSQL полностью остановлена, SSE получила `fd6a3d56-…`, PATCH → 409 EVENT_NOT_PERSISTED_YET, Stream/Pending =1; после запуска БД тот же UUID сохранился, backlog=0. Pub/sub path не читал БД.
* `redis-outage.log`: Valkey остановлен на 21 с с AOF и восстановлен. Worker readiness=503, run IDs камер не сменились. Три UUID из окна отказа после retry находятся в истории, Stream backlog=0. Это не тест потери диска/аварии хоста и не доказательство zero-loss.
* `real-model.log`: YOLO + готовый ByteTrack на MP4 из статичного официального bus.jpg, плюс две mock-камеры. Сохранено 4 события от реальной модели; отдельная telemetry дала persons=4/in-zone=4. Это smoke, не оценка качества на движущемся CCTV и не 4/8-camera benchmark.
* `browser.log`: локальный Chromium/Playwright, реальные API/worker/Vite. ACK и FALSE_POSITIVE сохраняют audit, заметка после API-read совпала, статусный фильтр, отдельные preview/telemetry sockets, no pageerror, 390px без horizontal overflow. PNG light/mobile/dark сохранены рядом. Image viewer среды не смог открыть PNG: визуальная оценка через него не заявляется; проверены DOM/состояния/API/layout metrics.
* `shutdown.log`: финальный worker с открытым telemetry WS завершился/удалил runtime и heartbeat за **0.62 с**, Stream=0. Финальный API с открытым SSE завершился за **3.22 с**. Uvicorn ограничен timeout_graceful_shutdown=3: long-lived SSE принудительно закрывается после bounded drain, generator освобождает очередь, затем lifespan закрывает фоновые задачи/клиентов. При потерянном ACK возможен безопасный replay.
* Финальная версия перезапущена, readiness API содержит здоровую `event_delivery`, worker выполнял модель и новые записи; браузерный smoke и shutdown повторены после перезапуска.

## Воспроизведение

`make check`; на **выделенной тестовой** PostgreSQL/Redis: `make migrate`, `uv run pytest -m integration`. Тесты очищают таблицы; test_events также FLUSHDB Redis DB 13. Никогда не запускать на рабочей инфраструктуре.

В `scripts/` сохранены фактически использованные smoke-скрипты (Python-снимки как `.py.txt`, запускаются явной командой `python путь-к-файлу`). Это sandbox-specific сценарии: перед повтором адаптировать /data пути, порты, PG/Valkey binaries и PID в shutdown.py.txt к своему окружению. Fault/shutdown скрипты реально останавливают сервисы; применять только в тестовом окружении. `browser.cjs` требует Playwright и Chromium. Общие команды запуска и безопасный порядок — docs/development.md и UPDATE_MILESTONE_7.md.

## Границы

Windows, Docker compose/CI, GPU/CUDA, настоящая RTSP-камера и движущееся CCTV не проверены. Нет snapshots/event detail с картинкой, CSV, сохранённых track sessions/аналитики/retention, линий/loitering и авторизации. RAM-outbox и Redis AOF everysec имеют границы сохранности; входной Stream не trim-ится, нужен мониторинг диска/backlog. Точные гарантии — ADR-034. Полная `.git`, git fsck, чистота рабочего дерева, ZIP и checksum проверяются перед передачей; checksum самого архива размещён на странице передачи, не внутри собственного Git-коммита.
