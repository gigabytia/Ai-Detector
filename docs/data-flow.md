# Потоки данных

Все времена в бэкенде — UTC, timezone-aware. Три вида времени в кадре никогда не смешиваются (§34): `source_ts_ms` (время источника: PTS файла или монотонное время захвата live), `captured_at` (wall clock UTC при захвате), `processed_at` (wall clock после inference). Подробно — [ADR-010](decisions/ADR-010-time-sources.md).

## 1. Кадр → событие (внутри worker'а)

```text
FrameSource.read()            поток захвата камеры; кадр = numpy-массив, без копий
   ▼
LatestFrameBuffer (1)         новый кадр вытесняет необработанный (freshness > completeness)
   ▼
InferenceScheduler            берёт кадры камер, у которых наступил срок по TARGET_FPS;
   ▼                          батч ≤ INFERENCE_BATCH_SIZE, ожидание ≤ INFERENCE_MAX_WAIT_MS
PersonDetector.predict(batch) → list[list[Detection]] (только person, conf ≥ DETECTION_CONFIDENCE)
   ▼  для каждой камеры батча, в своём try/except
PersonTracker.update(dets)    вызывается ВСЕГДА, в т.ч. с [] (§17): predict → match → update → age → remove
   ▼
EventEngine.process(tracks, scene)
   ├─ ZoneEngine: точка = низ-центр bbox (норм.) → point-in-polygon → state machine по (трек, зона)
   ├─ LineEngine: сторона линии с hysteresis → пересечение
   ├─ LoiteringRule
   └─ CooldownFilter (camera + track + type, wall clock)
   ▼
PipelineResult(camera_id, frame_info, tracks, events, stats)
   ├─► telemetry slot камеры (последнее значение)            → WS превью, если камера открыта
   ├─► events → SnapshotWriter (пул потоков) → outbox        → Redis
   ├─► StatsAccumulator (1 с бакеты)       → раз в 10 с пакет → outbox
   └─► TrackSessionRecorder (сегменты состояний) → при удалении трека → outbox
```

Кадр выбрасывается сразу после обработки; в БД кадры не пишутся (§6).

## 2. Событие → оператор и БД

```text
worker: событие создано (id = UUID, генерирует worker)
   ├─ JPEG snapshot в пуле потоков → SnapshotStorage.put()  (≈10–30 мс; inference не ждёт)
   ├─ PUBLISH  ad:events:live        {EventLiveDTO}          ── мгновенная доставка
   └─ XADD     ad:ingest  kind=event {EventIngestDTO + snapshot}  ── надёжная запись
          │                                     │
API (каждый процесс): SUBSCRIBE           API: XREADGROUP group=api-ingest (один получатель)
          ▼                                     ▼
SSE /api/v1/events/stream             batch INSERT ... ON CONFLICT (id) DO NOTHING; XACK
          ▼                                     │
Frontend: toast + бейдж на карточке,             │
вставка в кэш Vue Query                          ▼
                                            PostgreSQL events + snapshots
```

* Публикация в два канала: оператор видит тревогу, даже если PostgreSQL недоступен; запись надёжна, потому что сообщение остаётся в Stream до `XACK` ([ADR-017](decisions/ADR-017-event-persistence.md)).
* Повторная доставка безопасна: `id` события — первичный ключ.
* Если оператор нажал «Подтвердить» раньше, чем ingest записал событие, API отвечает `409 EVENT_NOT_PERSISTED_YET`, frontend повторяет запрос через 500 мс (до 5 раз).
* Изменение статуса: `PATCH /events/{id}` → service → repository → `PUBLISH ad:events:updates` → SSE `event.updated` у всех операторов.

SSE-сообщения: `event.created`, `event.updated`, `camera.status`; комментарий-heartbeat каждые 15 с. История через SSE не досылается: при переподключении frontend инвалидирует запросы событий и камер.

## 3. Конфигурация и команды

```text
UI → REST (камера / конфиг / зона / линия / start / stop / restart)
   → service → PostgreSQL  (cameras.enabled — желаемое состояние)
   → PUBLISH ad:worker:commands {type: camera.changed | camera.restart, camera_id}
worker: команда → GET /api/v1/internal/worker/cameras/{id} (токен) → CameraSpec
        → CameraManager.reconcile(): запустить / остановить / применить конфиг
```
* Полная сверка (`GET /api/v1/internal/worker/cameras`) — при старте worker'а и после восстановления связи с Redis (команды, пропущенные за время разрыва, не теряются); если API недоступен — повтор, текущие сессии продолжают работать ([ADR-028](decisions/ADR-028-worker-commands-best-effort.md)).
* `camera.changed` для работающей камеры с тем же источником (например, переименование) не переоткрывает поток.
* Новая зона/линия/порог применяется без перезапуска источника: `CameraSession` получает новый `SceneContext`; состояния треков по удалённым зонам сбрасываются.
* `CameraSpec` содержит URL с учётными данными; в публичном `CameraRead` URL маскируется (`rtsp://***:***@host/...`), в логах — только host.

## 4. Статус камер

worker раз в 1 с: `SET ad:camera:{id}:status {CameraRuntimeStatus} EX 5` (pipeline на все камеры); у остановленной камеры ключ удаляется сразу. API в `GET /cameras` объединяет данные из PostgreSQL со статусом из Redis (`MGET`); ключа нет → `runtime: null`. Поля: `status`, `capture_fps`, `frame_size`, `last_frame_at`, `last_error`, `reconnect_attempts`, `last_reconnect_attempt_at`, `worker_id`, `run_id`, `updated_at`. `fps_processed` и число людей добавятся с детектором (Milestone 4). До SSE (Milestone 7) UI опрашивает `GET /cameras` раз в 2 с; канал `ad:cameras:status` появится вместе с SSE.

## 5. Превью и телеметрия в браузер (Уровень 1)

```text
Browser ──WS──► /live/v1/cameras/{id}   (dev: Vite proxy /live → worker:8001; docker: nginx)
worker: соединение открыто = камера «открыта в UI»
   для обработанных кадров камеры, не чаще PREVIEW_FPS:
   resize ≤ PREVIEW_MAX_WIDTH → JPEG (пул потоков) → бинарное сообщение
```
Формат бинарного сообщения: `uint32 BE длина JSON` + `JSON TelemetryDTO (UTF-8)` + `JPEG`. Кадр и рамки из одного обработанного кадра — синхронны по построению. Камера без зрителей JPEG не кодирует. Пока по камере идёт превью, кадры, не попавшие в превью, телеметрию не шлют — рамки без картинки не нужны.

```json
{
  "camera_id": "8a0e…", "frame_id": 1234, "source_ts_ms": 51233,
  "captured_at": "2026-10-08T09:41:02.120Z", "frame_size": [1280, 720],
  "fps": 9.8, "persons_in_zone": 1,
  "persons": [{"track_id": 17, "bbox": [0.32, 0.18, 0.47, 0.72], "confidence": 0.91, "state": "IN_DANGER_ZONE"}]
}
```
bbox нормализован (x1, y1, x2, y2). Уровень 3: видео через MediaMTX (WebRTC/HLS), этот же WS шлёт только JSON, frontend сопоставляет по `source_ts_ms` с небольшим буфером ([ADR-005](decisions/ADR-005-video-streaming.md)).

Редактору зоны нужен кадр: он берёт его из того же превью. Если камера остановлена, редактор показывает пустое поле 16:9 с подсказкой «Запустите камеру, чтобы видеть кадр».

## 6. Аналитика и треки

* `StatsAccumulator` на камеру: по каждой секунде wall clock — `frames`, `persons_max`, `persons_avg`, `persons_in_zone_max`. Каждые 10 с — один пакет `kind=analytics` в ingest → batch upsert в `analytics_aggregates`.
* `TrackSessionRecorder`: при смене `PersonState` закрывает сегмент и открывает новый; при удалении трека (или остановке камеры / shutdown) отправляет `kind=track_session` вместе с сегментами. Треки, активные в момент аварийного падения worker'а, теряются ([ADR-019](decisions/ADR-019-track-persistence.md)).
* API считает показатели SQL-запросами по этим таблицам (§105), тяжёлые предагрегаты — позже.

## 7. Загрузка видео

`POST /api/v1/uploads` (multipart; расширения `UPLOAD_ALLOWED_EXTENSIONS`, размер ≤ `UPLOAD_MAX_BYTES`) → файл под сгенерированным именем `{uuid hex}.{ext}` в `UPLOAD_PATH` (запись во временный `.part`, затем переименование) → ответ `{file_ref, source_url}`. Камера типа `file` хранит `source_url = "upload://{file_ref}"`; worker разрешает ссылку только внутри `UPLOAD_PATH` (общий том). Произвольные пути не принимаются ([ADR-012](decisions/ADR-012-file-sources.md)).

## 8. Redis: имена и назначение

| Ключ / канал | Тип | Пишет | Читает |
|---|---|---|---|
| `ad:events:live` | pub/sub | worker | API → SSE |
| `ad:events:updates` | pub/sub | API | API → SSE |
| `ad:cameras:status` | pub/sub | worker | API → SSE |
| `ad:worker:commands` | pub/sub | API | worker |
| `ad:ingest` | Stream, `MAXLEN ~ 100000`, group `api-ingest` | worker | API ingest |
| `ad:camera:{id}:status` | string, TTL 5 с | worker | API |
| `ad:worker:{worker_id}:heartbeat` | string, TTL 5 с | worker | API `/health`, UI «Система» |

Схемы всех сообщений — Pydantic-модели в `shared/telemetry`; ни один слой не передаёт `dict[str, Any]`.
