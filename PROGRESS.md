# PROGRESS

Читать в начале каждой сессии.

## Текущий этап

**Milestone 3 — камеры: выполнен.** Следующий — Milestone 4 (детекция людей и визуализация).

## Сделано

### Milestone 1 — архитектура (подтверждено человеком)
* Документы `docs/architecture.md`, `data-flow.md`, `database.md`, `behavior.md`, ADR-001…021.

### Milestone 3 — камеры
* `shared`: типы источников и их проверка (`rtsp`, `upload://`, `mock://`), маскировка учётных данных, `CameraSpec`, `CameraStatus`/`CameraRuntimeStatus`, команды worker'у.
* API: таблица `cameras` (миграция, частичный уникальный индекс по имени, мягкое удаление), CRUD + `start`/`stop`/`restart`, загрузка видео `POST /uploads` (потоковая запись, лимиты, сгенерированные имена), внутренний API worker'а с токеном, объединение с runtime-статусом из Redis, коды ошибок домена, `ai-detector-seed` (2 демо-камеры).
* Worker: `FrameSource` (файл в реальном темпе по кругу, RTSP через OpenCV/FFmpeg, mock по сценарию), `CameraSession` (поток захвата на камеру, буфер последнего кадра, жизненный цикл по таблице переходов, reconnect с backoff, `ERROR` для неустранимых ошибок), `CameraManager` (сверка с желаемым состоянием), подписка на команды с полной сверкой после переподключения, публикация статусов в Redis раз в 1 с, `GET /status`.
* Frontend: «Мониторинг» — плитки камер со статусом, FPS захвата, разрешением, возрастом последнего кадра и сообщениями §120; «Камеры» — список, добавление (файл с загрузкой / RTSP / демо-сцена, «запустить сразу»), изменение, запуск/остановка/перезапуск, удаление с подтверждением; пустые состояния §122; уведомления (vue-sonner); опрос `GET /cameras` раз в 2 с до SSE.
* `.env.example`, compose (общий том `uploads`, токен, `API_BASE_URL`), CI (миграция перед интеграционными тестами), `make seed`.
* Документация: `docs/api.md` (камеры, загрузки, внутренний API, коды ошибок), правки `data-flow.md`, `architecture.md`, `behavior.md`, `database.md`, `development.md` (seed, пример видео §108, RTSP без камеры), ADR-024…028.

### Milestone 2 — инфраструктура
* uv workspace: `shared` (`ai_detector_core`), `backend` (`app`), `vision-worker` (`vision_worker`); `uv.lock`.
* `shared`: `Clock`, `WorkerHeartbeat`, имена Redis-ключей, JSON-логирование (stdlib).
* API: настройки (pydantic-settings, CORS без `*`, только `postgresql+asyncpg`), JSON-логи, lifespan с engine/Redis, `/health/live`, `/health/ready` (БД + Redis, 503 при отказе), `GET /api/v1/system/status` (зависимости + живые worker'ы), единый формат ошибок, Alembic (async, без миграций — таблицы с Milestone 3), экспорт OpenAPI.
* Worker: `Supervisor`, heartbeat в Redis раз в 1 с с TTL 5 с, HTTP `/health/live`, `/health/ready`, штатная остановка удаляет heartbeat.
* Frontend: Vite + Vue 3 + TS, Pinia, Vue Query, vue-i18n (ru), Tailwind 4, shadcn-vue (Button), Lucide; маршруты `/monitoring`, `/events`, `/analytics`, `/cameras`, `/settings`; светлая/тёмная (графит) темы; индикатор состояния системы и панель на «Настройках»; типы API из OpenAPI.
* Docker: Dockerfile api/worker/frontend, nginx (same-origin `/api`, `/health`, `/live`), `docker-compose.yml` (mediamtx — profile `media`).
* `Makefile` + эквиваленты PowerShell (`docs/development.md`), `.env.example`, CI (`.github/workflows/ci.yml`), `docs/api.md`.
* ADR-022 (TypeScript 5.9), ADR-023 (HTTP worker'а на FastAPI).

## Проверено (Milestone 3; песочница агента: Linux x86_64, Python 3.12.15, Node 24.14.1, CPU, без Docker)

| Проверка | Результат |
|---|---|
| `uv run pytest` | 72 passed (источники, backoff, буфер, жизненный цикл, сессия с fake-источником: reconnect/ERROR/stop, файл на сгенерированном видео: цикл, монотонное время, discontinuity, mock и сценарии, CameraManager, обработка команд, публикация статусов, схемы) |
| `uv run pytest -m integration` (PostgreSQL 17 + Valkey 9) | 10 passed: CRUD, 409, мягкое удаление и повторное имя, маскировка, лимит камер, публикация команд в Redis, загрузка (413/422, без остатков), токен внутреннего API |
| Тесты сессии 15 прогонов подряд | стабильны |
| `ruff check`, `ruff format --check`, `mypy --strict` | без ошибок |
| `npm run lint` / `format:check` / `typecheck` / `test` / `build` | без ошибок, 18 тестов Vitest |
| Живой запуск API + worker, `ai-detector-seed` (дважды) | 2 mock-камеры → RUNNING, 15 к/с, 1280×720; повторный seed ничего не дублирует |
| stop / start / restart / delete через API | статус пропадает при остановке, restart меняет `run_id`, удалённая камера уходит из worker'а |
| Файл-камера: загрузка mp4 (ffmpeg testsrc2) | RUNNING 25 к/с, 16 с работы при длине ролика 6 с (цикл) |
| Файл удалён с диска | камера `ERROR` «video file not found» без повторов |
| RTSP через MediaMTX 1.21.1 + ffmpeg | RUNNING 25 к/с; MediaMTX остановлен → RECONNECTING с растущим числом попыток; после возврата потока — RUNNING через ~10 с без перезапуска |
| SIGTERM worker'у с 5 камерами | остановка ~1 с, все сессии закрыты, ключи статуса и heartbeat удалены |
| UI в Chromium (Playwright) | добавление файл-камеры через диалог с загрузкой → «В работе» → остановка → запуск → переименование → удаление; ошибка 409 показана в форме по-русски; скриншоты светлой/тёмной темы и пустого состояния |

Milestone 2 проверки (health, отключение Redis, шаги Dockerfile) не повторялись целиком; health-тесты входят в `pytest`.

## Не проверено и почему

* `docker compose build/up` и CI на GitHub — в песочнице нет Docker и GitHub Actions; YAML только распарсен. Общий том `uploads` и `API_BASE_URL=http://api:8000` в compose не проверены в контейнерах.
* Настоящая IP-камера не подключалась (нет оборудования); RTSP проверен только через MediaMTX локально.
* RTSP с потерями пакетов/высокой задержкой и камеры с H.265 не проверялись.
* Интеграционные тесты шли на PostgreSQL 17 и Valkey 9, а в compose/CI — `postgres:18-alpine` и `redis:8.8-alpine`.
* Windows не проверялся (нет машины).

## Версии

Проверены по PyPI/npm/Docker Hub на 2026-10-08 и зафиксированы в `uv.lock` и `frontend/package-lock.json`. Исключение — TypeScript 5.9 вместо 7.0 ([ADR-022](docs/decisions/ADR-022-typescript-version.md)).

## Ключевые решения

* Worker не ходит в PostgreSQL ([ADR-002](docs/decisions/ADR-002-vision-worker-separation.md), [ADR-004](docs/decisions/ADR-004-event-bus.md)); превью — из worker'а ([ADR-005](docs/decisions/ADR-005-video-streaming.md)); событие — в pub/sub и Stream одновременно ([ADR-017](docs/decisions/ADR-017-event-persistence.md)).
* Milestone 3: сценарии mock — в пакете worker'а ([ADR-024](docs/decisions/ADR-024-mock-scenarios-location.md)); временные и неустранимые ошибки источника ([ADR-025](docs/decisions/ADR-025-frame-source-contract.md)); `camera_configs` — с Milestone 4 ([ADR-026](docs/decisions/ADR-026-camera-configs-deferred.md)); RTSP проверяется при запуске, без кнопки «Проверить» ([ADR-027](docs/decisions/ADR-027-source-validation.md)); команды worker'у — уведомление + полная сверка ([ADR-028](docs/decisions/ADR-028-worker-commands-best-effort.md)).
* Интеграционные тесты исключены из обычного `pytest` и при недоступном сервисе падают, а не пропускаются.

## Известные проблемы / риски

* Лимит `MAX_CAMERAS` проверяется без блокировки: два одновременных запроса могут создать камеру сверх лимита. Для 1–8 камер и одного оператора допустимо.
* `npm audit`: 4 high в dev-зависимостях (`braces` через eslint-config → fast-glob → micromatch); в production-сборку не попадают. Исправить обновлением, когда выйдет совместимая версия.
* Публикация файла в RTSP через `ffmpeg -re -stream_loop -1` после первого круга идёт быстрее реального времени — это особенность ffmpeg, не worker'а (см. `docs/development.md`).
* Сообщение `last_error` от worker'а — английский технический текст; UI показывает его мелко под русским описанием.
* Seed (§109) создаёт только камеры: зон и событий ещё нет — добавятся в seed на этапах 6–7.
* `StarletteDeprecationWarning` для TestClient (httpx → httpx2) — на работу не влияет.
* Риски из Milestone 1 актуальны: cooldown без zone_id ([ADR-008](docs/decisions/ADR-008-cooldown.md)), потеря активных треков при аварии worker'а ([ADR-019](docs/decisions/ADR-019-track-persistence.md)).

## Следующий шаг

Milestone 4 — детекция людей: `PersonDetector` (Ultralytics, класс person), scheduler с `target_fps` и батчингом, таблица `camera_configs` ([ADR-026](docs/decisions/ADR-026-camera-configs-deferred.md)), `scripted`-детектор для mock-сцен, превью JPEG + боксы по WebSocket, `/health/ready` worker'а с признаком загруженной модели.
