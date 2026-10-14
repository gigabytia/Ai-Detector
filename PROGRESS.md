# PROGRESS

Читать в начале каждой сессии.

## Текущий этап

**Milestone 4 — детекция людей и визуализация: выполнен.** Следующий — Milestone 5 (person tracking).

Реализация заново восстановлена на базе присланного архива Milestone 3 после утраты предыдущего рабочего окружения. Это не побайтовое восстановление незавершённой сессии: использованы сохранённые архитектурные документы, ADR и доступный контекст. Исходный `AI_DETECTOR_v2_MASTER_PROMPT.md` в архиве отсутствовал.

## Сделано

### Milestone 4 — детекция людей и визуализация
* `PersonDetector`/`PersonDetection`, Ultralytics adapter: YOLO26 nano, только COCO person, боксы в пикселях исходного изображения. Manifest (backend, веса, SHA-256, вход 640, класс, лицензия), явная атомарная загрузка `uv run ai-detector-model` / `make model`, проверка целостности и warmup до HTTP. При ошибке модели/устройства — CRITICAL и exit 1; скачивания и тихого scripted fallback на старте нет.
* Scripted adapter выбирается по `mock://` и использует тот же сценарий и source timestamp, что и renderer. Реальные и mock-камеры работают одновременно; mock явно помечен «ДЕМО».
* `InferenceScheduler`: отдельный одиночный executor, справедливая round-robin очередь, индивидуальный target_fps, батч до 4 с ожиданием до 20 мс, только последний кадр камеры. Индивидуальные confidence сохраняются при батчинге. Результаты остановленного run_id отбрасываются.
* Runtime: processed_fps, inference_ms, detections_count, dropped_frames, отдельная inference_error; DEGRADED при низком FPS более 5 с/ошибке inference, автоматическое восстановление. После 3 ошибочных реальных батчей readiness 503; успешные mock-камеры не скрывают отказ модели.
* `camera_configs`, миграция `b452b4c88e6b`, GET/PUT `/cameras/{id}/config`: только nullable переопределения FPS/порога, ответы overrides/defaults/effective, в worker-spec — effective. Горячее применение без переподключения; периодическая сверка каждые 30 с исправляет потерянные уведомления.
* `PreviewHub`: JPEG только для зрителей, пул из двух потоков, не более одного encode на камеру и одного ожидающего сообщения на зрителя. Binary WebSocket-пакет содержит JSON и JPEG одного frame_id/run_id; нет несогласованных рамок. Проверка Origin, таймаут медленного зрителя, очистка даже при отключении во время отсутствия кадров.
* Frontend: `CameraImageSource`/`WsPreviewSource`, bounded latest-only decode, backoff; отдельное shallow-состояние на камеру, явное освобождение bitmap. Canvas кадров и нормализованных боксов, подписка только для видимой работающей камеры, устаревший кадр помечается. Плитка открывает крупный просмотр `/monitoring/:cameraId`, редактор FPS/порога с наследованием, валидацией, сбросом и сохранением. Трекинг и уникальные посетители не имитируются.
* Обновлены OpenAPI/TS-типы, README, `.env.example`, Makefile, Docker mount моделей и `.dockerignore` (без host node_modules/venv в контексте), docs и ADR-029…031; ADR-016/028 уточнены. CPU PyTorch и единственная headless-сборка OpenCV; веса и лицензионные сведения включены в передаваемый архив.

## Проверено сейчас — Milestone 4

Окружение: Linux x86_64, Python 3.12.15 (uv), Node 24.14.1, PostgreSQL 17.10, Valkey 9.0.5, CPU. Node в песочнице ниже заявленного в package.json engine >=24.15.0; для своего запуска используйте поддерживаемую версию Node. Реальная модель: Ultralytics 8.4.177, torch 2.14.1+cpu, torchvision 0.29.1+cpu, numpy 2.5.3, OpenCV headless 5.0.0.93.

| Проверка | Результат |
|---|---|
| `uv run pytest` | 98 passed, интеграционные исключены; протокол/боксы, fairness, FPS, scripted, целостность модели, горячая конфигурация, деградация/восстановление, отбрасывание результатов старого run_id, готовность при отказе модели, периодическая сверка, WebSocket/очистка без кадров |
| `uv run pytest -m integration` | 11 passed на настоящих PostgreSQL + Valkey; прежние CRUD/uploads/internal/health и новая конфигурация: defaults, PUT/сброс, валидация, effective в worker-spec, 404 после удаления |
| `ruff check`, `ruff format --check`, `mypy --strict` | Без ошибок |
| Frontend lint / format:check / typecheck / test / build | Без ошибок; 46 Vitest-тестов, включая числовую форму, protocol, reconnect и освобождение bitmap |
| Миграции и `alembic check` | Обе миграции применены с пустой БД; расхождений моделей со схемой нет |
| `uv lock --check` | Lock согласован; CPU-источники зависимостей разрешаются |
| Настоящая модель | Warmup и батч 4 на официальном тестовом bus.jpg; person-боксы найдены на каждом кадре |
| Настоящий видеофайл | MP4 из тестового изображения загружен через API; real inference, JPEG/боксы через Vite WebSocket, 8 последовательных frame_id без дублей; при target_fps=3 наблюдалось около 3 FPS |
| Горячая конфигурация | Смена FPS/порога не меняет run_id; наследование и сброс проверены через API и UI |
| Нагрузка 8 камер | 6 file + 2 mock, CPU: все получают обработку (~1.56–1.57 FPS на этой машине), все корректно DEGRADED, readiness остаётся ready. Это smoke-проверка fairness, не обещание производительности |
| SIGTERM с открытым WebSocket | Обновлённый worker завершился примерно за 0.4 с, статусы и heartbeat `ad:*` удалены |
| Fail-fast | Несуществующий манифест → exit 1 до открытия HTTP; неправильный SHA-256 и отсутствующие веса дополнительно проверены unit-тестами |
| UI, локальный Chromium/Playwright | Реальные и mock-кадры с рамками; focus, числовая валидация, сохранение и сброс, stop/start, светлая/тёмная темы, 390px без горизонтального overflow, pageerror отсутствуют |
| `npm audit` | Production: 0 уязвимостей; полный audit: прежние 4 high в dev-цепочке eslint-config → fast-glob → micromatch → braces |

Скриншоты проверенного UI — `docs/qa/`. Видео для smoke-теста создано из статичного тестового изображения: это не проверка качества на реальном движущемся CCTV-потоке.

## История предыдущих этапов (из исходного архива)

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

## Проверено ранее по полученному архиву (Milestone 3; песочница агента: Linux x86_64, Python 3.12.15, Node 24.14.1, CPU, без Docker)

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

## Ограничения и что не проверено сейчас

* `docker compose build/up` и CI на GitHub — в песочнице нет Docker и GitHub Actions; YAML только распарсен. Общий том `uploads` и `API_BASE_URL=http://api:8000` в compose не проверены в контейнерах.
* В восстановленной сессии реальная IP-камера/RTSP не подключались. Ранее в Milestone 3 по архиву RTSP проверялся через MediaMTX; это не повторная проверка текущей версии.
* RTSP с потерями пакетов/высокой задержкой и камеры с H.265 не проверялись.
* Интеграционные тесты шли на PostgreSQL 17 и Valkey 9, а в compose/CI — `postgres:18-alpine` и `redis:8.8-alpine`.
* Windows, CUDA/GPU, ONNX и WebRTC не проверялись/не реализованы на этом этапе.
* Качество детекции на пользовательских CCTV-данных не оценивалось. Восемь камер на CPU не достигают целевых 10 FPS — нужна настройка FPS/железа; GPU-оптимизация — позднее.
* Авторизации оператора нет: нельзя открывать API/worker в публичный Интернет. AGPL-3.0 модели/Ultralytics нужно учитывать перед внедрением.

## Версии

Базовые зависимости были зафиксированы в исходном архиве на 2026-10-08. Восстановление Milestone 4 обновило `uv.lock` для inference; фактически проверенные версии перечислены выше. Frontend lock сохранён из исходного архива. Исключение — TypeScript 5.9 вместо 7.0 ([ADR-022](docs/decisions/ADR-022-typescript-version.md)).

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

Milestone 5 — person tracking: интерфейс `PersonTracker`, ByteTrack adapter, registry и track_id в пределах камеры/run_id, update на каждом обработанном кадре (включая пустые детекции), сброс при discontinuity, отрисовка track ID. Зоны/линии/события пока не добавлять раньше своих этапов.
