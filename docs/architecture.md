# Архитектура AI Detector v2

> Реализован M12 в CPU-среде: M11 pipeline сохранён, добавлены local Prometheus metrics/benchmark, исправлен predictor thread reset и лишний batch wait. Границы — PROGRESS.md, ADR-039, docs/qa/m12/REPORT.md. GPU/RTSP/full storage нагрузка не проверены.

Система видеонаблюдения: находит **людей** на видеопотоках, отслеживает их (track ID внутри камеры) и сообщает оператору о входе в опасную зону, пересечении линии и долгом нахождении в зоне. Объекты, перенос груза и pose estimation в эту версию не входят (ТЗ §2, §27).

## 1. Процессы

```text
                 Browser (Vue 3 + TS)
        REST + SSE │                │ WebSocket (preview JPEG + metadata)
                   ▼                ▼
            ┌────────────┐    ┌──────────────────┐
            │ API        │    │ Vision Worker    │── FrameSource: file / rtsp / mock
            │ FastAPI    │◄───│ (HTTP: health,   │
            │ ×N         │HTTP│  metrics, WS)    │── PersonDetector (модель 1 раз на worker)
            └──┬─────┬───┘conf└───────┬──────────┘── PersonTracker, EventEngine
               │     │                │
               │     └────► Redis ◄───┘  pub/sub (live), Streams (ingest), status keys
               ▼
           PostgreSQL         Snapshot storage (общий том: worker пишет, API читает)

           MediaMTX — Уровень 3, optional profile (RTSP → WebRTC/HLS)
```

| Процесс | Отвечает за | Не делает |
|---|---|---|
| **frontend** | UI оператора, отрисовка рамок/зон на canvas | бизнес-правила |
| **api** (FastAPI, масштабируется ×N) | REST `/api/v1`, SSE, конфигурация камер/зон/линий, команды worker'у, запись событий/треков/аналитики в PostgreSQL (ingest из Redis Stream), выдача snapshot-файлов, health, OpenAPI | inference, чтение кадров, tracking, хранение runtime-состояния в памяти |
| **vision-worker** | захват кадров, inference, tracking, правила событий, snapshot-файлы, превью для открытых камер, runtime-статус камер, метрики | доступ к PostgreSQL, раздача видео «всем подряд» |
| **postgres** | persistent state | runtime state, покадровые данные |
| **redis** | шина событий, команды, короткоживущий статус | persistent data |
| **mediamtx** | (Уровень 3) раздача RTSP в браузер | аналитика |

Ключевые решения: worker не ходит в PostgreSQL ([ADR-002](decisions/ADR-002-vision-worker-separation.md)); события и аналитика доставляются через Redis ([ADR-004](decisions/ADR-004-event-bus.md)); превью идёт из worker'а ([ADR-005](decisions/ADR-005-video-streaming.md)).

## 2. Python-пакеты (uv workspace)

```text
shared (ai_detector_core)      домен + порты + контракты сообщений; только stdlib + pydantic
   ▲                ▲
backend (app)    vision-worker (vision_worker)     друг от друга не зависят
```

* `shared/` — `Camera`, `CameraStatus`, `EffectiveCameraConfig`, `Detection`, `PersonTrack`, `PersonState`, `Zone`, `Line`, `NormalizedPoint`, `DomainEvent`, `EventType`, `EventStatus`, `Severity`, DTO телеметрии/ingest-сообщений, имена Redis-каналов, Protocol-порты (`EventBus`, `SnapshotStorage`, `Clock`) и `LocalSnapshotStorage` (stdlib, нужен обоим сервисам). Нет FastAPI, SQLAlchemy, Redis, OpenCV, Ultralytics, numpy.
* `backend/` — слои `api → application → infrastructure`, см. §4.
* `vision-worker/` — см. §5.

## 3. Runtime и persistent state

| Persistent (PostgreSQL) | Runtime (память worker'а / Redis с TTL) |
|---|---|
| cameras, camera_configs, zones, lines | `CameraSession`: источник, поток захвата, буфер кадра, tracker, метрики, состояние |
| events, snapshots (метаданные) | активные треки и состояния зон по трекам |
| track_sessions, track_segments | очереди, outbox, состояние модели |
| analytics_aggregates (1 строка / камера / секунда) | статус камеры в Redis `ad:camera:{id}:status` (TTL 5 с) |

Желаемое состояние камеры («должна работать») — `cameras.enabled` в PostgreSQL. Фактическое — только в worker и Redis. API не держит критичного состояния в памяти, поэтому `uvicorn --workers N` безопасен.

## 4. Backend (FastAPI)

```text
backend/src/app/
├── main.py                 # create_app(), lifespan
├── api/                    # health.py (/health/live, /health/ready), errors.py, deps.py
├── api/v1/                 # system, cameras, zones, events, analytics, uploads, snapshots, realtime (SSE), worker (internal)
├── core/                   # config (pydantic-settings), logging (JSON), lifecycle
├── application/            # camera_service, zone_service, event_service, analytics_service, upload_service
├── infrastructure/
│   ├── database/           # SQLAlchemy models, async session, repositories
│   ├── redis/              # клиент, publisher, SSE subscriber
│   ├── storage/            # snapshot + upload storage wiring
│   └── ingest/             # consumer Redis Stream → репозитории (batch insert)
└── schemas/                # CameraCreate/Update/Read, CameraConfigRead/Update, Zone*, Line*, EventRead/Update ...
```

* Поток вызова: `endpoint → service → repository → AsyncSession`. Endpoint не трогает SQLAlchemy.
* DI FastAPI: session на запрос, сервисы и репозитории через `Depends`. Ingest-задача создаёт свою session на каждый пакет.
* Ошибки: доменные исключения (`CameraNotFound`, `CameraNameConflict`, `InvalidZone`, `EventNotPersistedYet`…) → единый обработчик → JSON `{"error": {"code", "message"}}` с 404/409/422/503.
* `infrastructure/streaming` из §78 не создаётся до Уровня 3 (API видео не раздаёт); каталог `ingest/` добавлен ([ADR-004](decisions/ADR-004-event-bus.md)).
* Auth: нет; все роутеры подключаются через одну точку, куда позже встанет auth-dependency. Internal-эндпоинт для worker'а защищён токеном `WORKER_API_TOKEN`.

## 5. Vision worker

```text
vision-worker/src/vision_worker/
├── main.py              # сборка зависимостей явно, без глобальных синглтонов
├── config.py
├── supervisor.py        # жизненный цикл компонентов, без бизнес-логики
├── cameras/             # session.py (CameraSession + state machine), source.py (FrameSource + file/rtsp/mock), reconnect.py (backoff), manager.py (reconcile желаемого состояния)
├── pipeline/            # frame_buffer.py, scheduler.py (fair inference batching), results.py, preview.py; pipeline.py — с трекингом/правилами
├── inference/           # detector.py, manifest.py, fetch.py, adapters/ (ultralytics, scripted); ONNX — позднее
├── tracking/            # tracker.py (PersonTracker Protocol + TrackRegistry), bytetrack_adapter.py
├── analytics/           # zone_engine.py, line_engine.py, state_machine.py, event_engine.py, rules/, cooldown.py, stats.py
├── messaging/           # event_bus.py (Redis), outbox.py (bounded), commands.py
├── storage/             # snapshot_writer.py
└── http/                # health, status, /metrics, WS превью
```

### Потоки исполнения

| Где | Что | Почему |
|---|---|---|
| Поток захвата на камеру | `FrameSource.read()` (блокирующий) → `LatestFrameBuffer` (размер 1, старый кадр вытесняется) | блокирующий I/O не должен держать остальных |
| Один поток inference | scheduler собирает свежие кадры камер, у которых наступило время по `TARGET_FPS`, батч до `INFERENCE_BATCH_SIZE` или `INFERENCE_MAX_WAIT_MS` → `PersonDetector.detect(batch, confidence)` → для каждой камеры `tracker.update` → `EventEngine.process` | модель одна, GPU-вызовы последовательны; состояние трекеров и правил трогает только этот поток — без блокировок |
| Пул из 2 потоков | JPEG превью (snapshot — на следующем этапе) | кодирование не тормозит inference; без зрителей не выполняется |
| asyncio loop | HTTP/WS, Redis (publish, команды, heartbeat), outbox | I/O — async (§194) |

Передача из потока inference в asyncio — `loop.call_soon_threadsafe` в ограниченные очереди. Телеметрия: «последнее значение на камеру» (перезаписывается). События/треки/аналитика: bounded outbox (`WORKER_OUTBOX_MAX_ITEMS`); при переполнении отбрасывается самое старое, растёт метрика, статус worker'а → degraded.

Изоляция ошибок: обработка каждой камеры внутри батча в своём `try/except` с `logger.exception`; упавшая камера → `ERROR`, остальные продолжают (§37). Ошибка самого `predict` → камеры батча `DEGRADED`, повтор; после трёх подряд ошибочных реальных батчей `/health/ready` = false; успешный реальный батч восстанавливает готовность. Успех scripted-камер не скрывает отказ модели.

### Жизненный цикл камеры

```text
CREATED → STARTING → RUNNING ⇄ DEGRADED
             ▲          │ ошибка чтения
             │          ▼
             └──── RECONNECTING (backoff 1→2→4…≤30 с)
любое → STOPPING → STOPPED;   неустранимая ошибка (нет файла, неверный URL) → ERROR
```
Переходы задаются таблицей разрешённых переходов в `vision_worker/cameras/lifecycle.py`; недопустимый переход — исключение. UI (`frontend/src/lib/cameraStatus.ts`): камера выключена → «Остановлена»; включена, но статуса в Redis нет → «Нет обработчика»; RUNNING → «В работе»; CREATED/STARTING → «Подключение…»; RECONNECTING → «Недоступна» (с временем последней попытки, §120); DEGRADED → «Работа ограничена»; ERROR → «Ошибка». Ошибки источника: [ADR-025](decisions/ADR-025-frame-source-contract.md).

## 6. Границы замены (§189, §203)

| Что заменить | Где граница | Что не меняется |
|---|---|---|
| Источник видео (GStreamer, MediaMTX) | `FrameSource` | pipeline, tracker, правила |
| Модель / runtime (ONNX, TensorRT) | `PersonDetector` + adapter | tracking, EventEngine |
| Трекер | `PersonTracker` | правила зон/линий |
| Новое правило | `EventRule` в `EventEngine` + значение `EventType` + перевод в i18n | capture, inference, storage |
| БД | репозитории backend | worker, домен |
| Хранилище snapshot (S3/MinIO) | `SnapshotStorage` | события |
| Доставка видео в браузер | frontend `CameraImageSource` | `CameraCard`, редактор зоны |

Интерфейсы (минимальные, реальные — без пустых классов «на будущее»):

```python
class FrameSource(Protocol):
    def start(self) -> None: ...
    def read(self) -> Frame | None: ...        # блокирующий; None — нет кадра/конец
    def stop(self) -> None: ...

class PersonDetector(Protocol):
    def warmup(self) -> None: ...
    def predict(self, frames: Sequence[Frame]) -> list[list[Detection]]: ...

class PersonTracker(Protocol):                   # один экземпляр на CameraSession
    def update(self, detections: Sequence[Detection], frame: FrameInfo) -> list[PersonTrack]: ...
    def reset(self) -> None: ...

class EventRule(Protocol):
    def evaluate(self, tracks: Sequence[PersonTrack], scene: SceneContext) -> list[DomainEvent]: ...
```

## 7. Frontend

* Vue 3 + `<script setup lang="ts">`, Vite, Tailwind, shadcn-vue, Lucide, ECharts, vue-i18n (только `ru`).
* Server state — TanStack Vue Query (камеры, события, аналитика, конфиг, статус системы). UI state — Pinia (выбранная камера, фильтры, тема, модалки). Телеметрия — composable `useCameraTelemetry(cameraId)` с `shallowRef` на камеру; не попадает ни в Query, ни в Pinia.
* SSE `useEventStream()` один на приложение: вставляет новые события в кэш Query, обновляет статусы камер.
* `CameraImageSource` — интерфейс источника изображения: сейчас `WsPreviewSource`, позже `WebRtcSource`. Canvas-оверлей рисует по `requestAnimationFrame`.
* Типы API генерируются из OpenAPI ([ADR-018](decisions/ADR-018-frontend-api-types.md)).
* Маршруты: `/monitoring` (главный), `/events`, `/analytics`, `/cameras`, `/cameras/:cameraId`, `/settings`. `App.vue` — только композиция layout + `RouterView`.

## 8. Масштабирование

* API ×N: состояния в памяти нет; ingest через consumer group Redis Streams — каждое сообщение обрабатывает один процесс.
* Worker ×N (на GPU по одному): колонка `cameras.assigned_worker` заложена; в MVP `NULL` = камеру берёт единственный worker. Распределение — после MVP.
* `MAX_CAMERAS` — проверка при создании камеры, не архитектурный предел. Цель MVP — 1–8 камер на одной машине.

## 9. Отказы

| Отказ | Поведение |
|---|---|
| RTSP-камера недоступна | `RECONNECTING` с backoff, остальные камеры работают |
| Файл не найден / не декодируется | эта камера `ERROR` до перезапуска или смены источника ([ADR-025](decisions/ADR-025-frame-source-contract.md)) |
| Ошибка обработки одной камеры | эта камера `ERROR`, исключение в логе |
| Redis недоступен | worker продолжает inference, копит outbox (bounded), статус degraded; API `/health/ready` = 503, SSE переподключается |
| PostgreSQL недоступен | API отвечает 503; worker продолжает, сообщения ждут в Redis Stream и записываются позже |
| API недоступен | worker работает на последней полученной конфигурации |
| Падение worker'а | API работает; статусы камер истекают по TTL → OFFLINE |

## 10. Вне объёма

Детекция объектов, перенос груза, pose, re-ID, распознавание лиц, межкамерная идентичность, RBAC, Kafka, Kubernetes, микросервисы под каждый модуль (§158–159). Заглушки под них не создаются.


## Milestone 4: реализованные компоненты

* `inference/detector.py`: `PersonDetector`, `PersonDetection` — без зависимости от Ultralytics.
* `inference/manifest.py`, `fetch.py`: манифест и SHA-256, явная загрузка весов; `adapters/ultralytics.py` и `adapters/scripted.py`: реальная и сценарная детекция.
* `pipeline/scheduler.py`: `InferenceScheduler`, один inference executor, latest-frame + round-robin + батчинг; `results.py`: immutable `DetectionResult`; `preview.py`: `PreviewHub`, два потока JPEG и ограниченные очереди зрителей.
* `CameraSession`: метрики обработки и деградация; захват остаётся в своём потоке. `Supervisor`: запускает inference loop и при остановке дожидается текущего батча, закрывает камеры, preview, Redis/HTTP-клиенты.
* `CameraConfigService`, `CameraConfigModel`: сохраняемые переопределения и effective конфигурация в `CameraSpec`.
* Frontend `lib/live/`: протокол и `CameraImageSource`/`WsPreviewSource`; `useCameraLive`: отдельное `shallowRef`-состояние и явное освобождение bitmap на камеру; `CameraLiveView`: canvas кадра и боксов в одном requestAnimationFrame, подписка только при видимой работающей камере; `CameraFocusView`: крупный просмотр и `CameraConfigPanel`.

## Milestone 5: трекинг людей

* `shared/people/track.py`: immutable `PersonTrack`, `PersonState` (`NORMAL`/`LOST`), center и anchor. Нет зависимости от CV-библиотек.
* `tracking/tracker.py`: `PersonTracker.update(frame, detections)` / `reset`; `bytetrack.py`: adapter к готовому ByteTrack; `registry.py`: отдельный экземпляр на `(camera_id, run_id)`, сброс сцены по epoch/разрешению, очистка остановленных камер.
* `_process` в том же одиночном inference executor: детекция → обновление трекера, в том числе с `[]` → immutable результат. JPEG и event loop не обращаются к изменяемому tracker state. CPU-трекинг не блокирует asyncio loop.
* `DetectionResult.tracks` — immutable snapshot именно этого кадра. Preview v1 дополнен `tracks`; canvas подписывает подтверждённые детекции ID, не рисует LOST. Детекции-кандидаты пока без ID.
* Параметры worker'а: `PERSON_TRACK_MAX_AGE`, `TRACK_MATCH_IOU`, `TRACK_ACTIVATION_CONFIDENCE`; конкретная семантика — [ADR-032](decisions/ADR-032-bytetrack-runtime.md).

В M5 зоны и события ещё не подключались; текущая реализация M6 описана ниже. Линии, запись track sessions, аналитика и уникальные посетители пока отсутствуют. ONNX/WebRTC — дальнейшие adapters, не заглушки работающей функции.

## Milestone 6: опасная зона

* `shared/zones/{model,geometry}.py`: immutable ZoneShape/ZoneSpec, валидация простого нормализованного polygon и point-in-polygon с включённой границей. `shared/events/domain.py`: типизированное событие входа; PersonState дополнен IN_DANGER_ZONE.
* API: ZoneService/ZoneRepository/ZoneModel, camera-scoped CRUD и миграция c631d038af01; CameraSpec включает зоны и effective интервалы. Worker не обращается к PostgreSQL.
* `rules/{zone_engine,registry}.py`: membership/dwell/grace/confidence/cooldown в одиночном inference executor после tracker. DetectionResult содержит tracks/zones/events из одной сцены и кадра; в лог выходят события только актуального run. Preview v1 передаёт enabled zones и состояние треков.
* Frontend: ZoneEditor с локальным черновиком и REST, SVG overlay над canvas с учётом letterbox, красные рамки IN_DANGER_ZONE. Модель/API и worker выполняют правила; UI только редактирует и отображает.
* События пока генерируются и логируются, а не пишутся в БД/Redis Stream. Это сознательная граница M6/M7, а не гарантированная доставка. [ADR-033](decisions/ADR-033-danger-zone-runtime.md).

## Добавлено в Milestone 7

* shared/telemetry/event_bus.py — transport names; worker/messaging/events.py — bounded outbox, Lua Stream+pub/sub и retry, не блокирующий inference. pipeline/telemetry.py — отдельный JSON latest-only hub.
* API application/event_service.py — статусные переходы/аудит; repository/events.py — история и row lock; redis/ingest.py — consumer group/batch/idempotency/reclaim/dead letter; redis/live.py — per-process fanout; redis/tasks.py — readiness фоновых задач. Lifespan запускает и отменяет их до закрытия клиентов.
* events + миграция 14d6499b16a2. FK зон SET NULL, история soft-deleted камер сохраняется. track_sessions/snapshots/analytics таблиц пока нет.
* Один frontend useRealtime, bounded volatile alarm store, пагинированный EventsView/карточки с заметкой и ACK/FP. useTelemetry только для focus, preview остаётся независимым.
* Точные гарантии и остаточные риски — [ADR-034](decisions/ADR-034-event-delivery-realtime.md). M6-граница выше описывает историю этапа, а не текущее отсутствие доставки.

## Добавлено в Milestone 8

Shared stdlib LocalSnapshotStorage, отдельный bounded SnapshotWriter/thread pool worker, optional EventMessage snapshot, одна DB-транзакция event+metadata, UUID JPEG endpoint и event detail Vue. API retention имеет независимую maintenance task (не включена в event_delivery readiness probe), Redis lease renewal и safe ownership release. Shutdown worker дожидается capture/encode до остановки publisher. См. [ADR-035](decisions/ADR-035-event-snapshots.md).

## Добавлено M9

Line CRUD → CameraSpec.lines → scheduler → SceneRegistry (ZoneEngine затем LineEngine) → общий immutable DetectionResult/events → M8 SnapshotWriter → M7 outbox/ingest/SSE. Без нового потока доставки и без нового PersonState. Side/confidence/cooldown bounded активными tracks/runs; geometry/epoch reset предотвращает синтетические crossing. См. ADR-036.

## M10: отдельная аналитика

Accepted inference result → event-loop AnalyticsCollector → bounded AnalyticsPublisher → ad:analytics:ingest → backend AnalyticsIngest → PostgreSQL camera_samples/track_sessions → AnalyticsRepository (SQL aggregates) → AnalyticsService (window/status policy) → thin REST route → dashboard/TrackTimeline. Alarm pub/sub/Stream, JPEG writer и preview не заменены. API analytics task имеет отдельный readiness probe; worker analytics_ok/dropped не объявляют успешную запись в БД. Нет DB connection в worker. См. ADR-037 для семантики и caps.

## M11: расширение правил и экспорт

ZoneEngine Visit получает continuous-observation timer и once-per-confirmed-visit marker; typed event идёт прежним alarm transport/snapshot/history путём. Нет нового PersonState/отдельного event bus. Effective threshold API/camera-owned, severity worker-owned. Export: shared repository predicates/projected SELECT → EventService → off-loop CSV codec → готовый HTTP attachment только после полной проверки limits. Старые M10 sampled analytics/retention границы не изменены. Текущий этап M11, подробнее PROGRESS/ADR-038; ранние future-only упоминания loitering/CSV выше исторические.
