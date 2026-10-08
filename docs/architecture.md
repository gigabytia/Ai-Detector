# Архитектура AI Detector v2

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
├── pipeline/            # frame_buffer.py (latest-frame), scheduler.py (batch builder), pipeline.py (detect→track→rules), results.py
├── inference/           # detector.py (PersonDetector Protocol), runtime.py (device), adapters/ (ultralytics, onnx_runtime, scripted)
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
| Один поток inference | scheduler собирает свежие кадры камер, у которых наступило время по `TARGET_FPS`, батч до `INFERENCE_BATCH_SIZE` или `INFERENCE_MAX_WAIT_MS` → `PersonDetector.predict(batch)` → для каждой камеры `tracker.update` → `EventEngine.process` | модель одна, GPU-вызовы последовательны; состояние трекеров и правил трогает только этот поток — без блокировок |
| Пул из 2 потоков | JPEG snapshot и превью | кодирование не тормозит inference |
| asyncio loop | HTTP/WS, Redis (publish, команды, heartbeat), outbox | I/O — async (§194) |

Передача из потока inference в asyncio — `loop.call_soon_threadsafe` в ограниченные очереди. Телеметрия: «последнее значение на камеру» (перезаписывается). События/треки/аналитика: bounded outbox (`WORKER_OUTBOX_MAX_ITEMS`); при переполнении отбрасывается самое старое, растёт метрика, статус worker'а → degraded.

Изоляция ошибок: обработка каждой камеры внутри батча в своём `try/except` с `logger.exception`; упавшая камера → `ERROR`, остальные продолжают (§37). Ошибка самого `predict` → камеры батча `DEGRADED`, повтор; при повторяющихся ошибках `/health/ready` = false.

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
