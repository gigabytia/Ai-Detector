# API

Интерактивная документация — `http://localhost:8000/docs` (OpenAPI генерируется FastAPI). Контракт для frontend — `frontend/openapi.json`.

## Ошибки

Все ошибки возвращаются в одном формате:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": [{"loc": ["body", "name"], "msg": "Field required"}]}}
```

Коды ошибок домена:

| HTTP | code | Когда |
|---|---|---|
| 404 | `CAMERA_NOT_FOUND` | камеры нет или она удалена |
| 404 | `ZONE_NOT_FOUND` | зона не найдена в указанной камере |
| 422 | `UNPROCESSABLE` | больше 16 зон на камеру |
| 409 | `CAMERA_ALREADY_EXISTS` | имя занято не удалённой камерой |
| 422 | `CAMERA_LIMIT_REACHED` | уже `MAX_CAMERAS` камер |
| 422 | `INVALID_CAMERA_SOURCE` | URL не подходит к типу или загруженного файла нет |
| 422 | `UPLOAD_REJECTED` | расширение не из `UPLOAD_ALLOWED_EXTENSIONS` или файл пустой |
| 413 | `UPLOAD_TOO_LARGE` | больше `UPLOAD_MAX_BYTES` |
| 422 | `VALIDATION_ERROR` | тело запроса не прошло схему |

## Health (API)

| Запрос | Ответ |
|---|---|
| `GET /health/live` | `200 {"status":"alive"}` — процесс жив, зависимости не проверяются |
| `GET /health/ready` | `200` или `503`: `{"status":"ready","dependencies":[{"name":"database","ok":true,"error":null},{"name":"redis","ok":true,"error":null}]}` |

## Состояние системы

`GET /api/v1/system/status`

```json
{
  "status": "ok",
  "checked_at": "2026-10-08T10:20:01Z",
  "dependencies": [{"name": "database", "ok": true, "error": null}, {"name": "redis", "ok": true, "error": null}],
  "workers": [{"worker_id": "worker-1", "version": "0.1.0", "started_at": "2026-10-08T10:19:55Z", "last_seen_at": "2026-10-08T10:20:00Z", "uptime_seconds": 5.7}]
}
```
`status = "degraded"`, если недоступна зависимость или нет ни одного worker'а. Worker виден, пока его heartbeat в Redis не истёк (5 с).

## Камеры

| Запрос | Ответ |
|---|---|
| `GET /api/v1/cameras` | `200 [CameraRead]` — не удалённые, по имени |
| `POST /api/v1/cameras` | `201 CameraRead`; тело `{name, source_type, source_url, enabled=false}` |
| `GET /api/v1/cameras/{id}` | `200 CameraRead` |
| `PATCH /api/v1/cameras/{id}` | `200 CameraRead`; любое из `name`, `source_type`, `source_url` |
| `DELETE /api/v1/cameras/{id}` | `204`; мягкое удаление, камера останавливается ([ADR-011](decisions/ADR-011-camera-soft-delete.md)) |
| `POST /api/v1/cameras/{id}/start` · `/stop` | `200 CameraRead`; меняют желаемое состояние `enabled` |
| `POST /api/v1/cameras/{id}/restart` | `200 CameraRead`; включает камеру и пересоздаёт сессию (новый `run_id`) |

```json
{
  "id": "bbb13f72-…", "name": "Склад — проход", "source_type": "rtsp",
  "source_url": "rtsp://***:***@10.0.0.5:554/stream1", "enabled": true,
  "created_at": "…", "updated_at": "…",
  "runtime": {
    "status": "RUNNING", "capture_fps": 25.0, "frame_size": [1280, 720],
    "last_frame_at": "…", "last_error": null, "reconnect_attempts": 0,
    "last_reconnect_attempt_at": null, "worker_id": "worker-1", "updated_at": "…"
  }
}
```
`source_url` всегда с маскированными учётными данными. `runtime: null` — ни один worker не сообщает о камере (выключена, ещё не стартовала или worker не запущен). Ответ на start/stop приходит до того, как worker применил изменение; фактический статус виден в `runtime` через 1–2 с ([ADR-028](decisions/ADR-028-worker-commands-best-effort.md)).

Источники: `rtsp://…` / `rtsps://…`; `upload://{file_ref}` (сначала загрузить файл); `mock://walk_through`, `mock://two_people`.

## Загрузка видео

`POST /api/v1/uploads`, `multipart/form-data`, поле `file` → `201 {"file_ref": "…32 hex….mp4", "source_url": "upload://….mp4", "size_bytes": 546118, "original_name": "clip.mp4"}`. Имя файла генерируется; исходное имя не используется как путь ([ADR-012](decisions/ADR-012-file-sources.md)).

## Внутренний API worker'а

Не входит в OpenAPI. Заголовок `Authorization: Bearer $WORKER_API_TOKEN`; без токена — `401`, если токен не настроен в API — `503`.

| Запрос | Ответ |
|---|---|
| `GET /api/v1/internal/worker/cameras` | включённые камеры как `CameraSpec` (URL без маскировки) |
| `GET /api/v1/internal/worker/cameras/{id}` | `CameraSpec` или `404`, если камера удалена |

## Health (vision worker, порт 8001)

| Запрос | Ответ |
|---|---|
| `GET /health/live` | `200 {"status":"alive"}` |
| `GET /health/ready` | `200`/`503`: `status`, `redis_ok`, `last_heartbeat_at`, `detector_loaded`, `detector` (backend/model/device). |
| `GET /status` | runtime-статусы камер этого worker'а (как `runtime` выше, плюс `camera_id`, `run_id`) — для отладки |


## Детекция и настройки камеры (Milestone 4)

* `GET /api/v1/cameras/{id}/config` → `{overrides, defaults, effective}`. Каждая часть содержит `target_fps`, `detection_confidence` и (M6) `zone_enter_dwell_seconds`, `zone_exit_grace_seconds`, `event_cooldown_seconds`; только overrides допускает null.
* `PUT /api/v1/cameras/{id}/config` → тот же ответ. Полная замена: `{}` сбрасывает переопределения. FPS 1–30, confidence >0 и ≤1; лишние поля/ошибочные значения → 422, удалённая/неизвестная камера → 404. Настройки действуют без смены `run_id` и переподключения к источнику.
* Внутренний `CameraSpec` содержит effective `config`; учётные данные источника не выдаются в публичном API.
* Runtime камеры дополнен `processed_fps`, `inference_ms` (время батча / количество реальных кадров, мс), `detections_count`, `dropped_frames` (заменённые в latest-frame буфере), `inference_error` (технический текст, UI показывает безопасное объяснение).
* Worker `GET /health/ready` дополнен `detector_loaded` и `detector: {backend, model, device}`. Готовность требует Redis, живого inference loop и отсутствия серии из трёх подряд ошибочных реальных батчей. Ошибка загрузки модели завершается до запуска HTTP.

### WebSocket превью, версия 1

Браузер: `/live/cameras/{UUID}/preview`; напрямую worker: `/cameras/{UUID}/preview`. nginx/Vite удаляют `/live`. Никакого видео через API/Redis/PostgreSQL.

Каждое binary-сообщение — **один согласованный кадр**: 4 байта unsigned big-endian (длина JSON), JSON UTF-8, затем JPEG. JSON: `version=1`, `camera_id`, `run_id`, `frame_id`, `source_ts_ms`, `captured_at` (UTC), `width`, `height` (исходное разрешение), `inference_ms`, `detections: [{bbox:[x1,y1,x2,y2],confidence}]`. Bbox нормализован 0…1, JPEG уменьшен максимум до `PREVIEW_MAX_WIDTH`, без увеличения маленького кадра. Пустой массив детекций — нормальный результат. С Milestone 5 дополнительно передаётся `tracks: [{track_id,bbox,confidence,state,age,hits,missed_frames}]`. Состояние — `NORMAL`/`IN_DANGER_ZONE`/`LOST` (IN_DANGER_ZONE с M6), `track_id` положителен и уникален только вместе с camera_id/run_id. Bbox нормализован; у LOST — последнее наблюдение, не текущая рамка. `age` — обработанные кадры с подтверждения, `hits` — совпадения, `missed_frames` — последовательные пропуски. Кандидат до подтверждения остаётся в detections без track ID. Поле additive в версии 1: новый frontend принимает также старые пакеты без tracks. В M5 REST/OpenAPI не менялся; M6 добавляет REST зон и интервалы конфигурации.

Только открытые зрители вызывают JPEG-кодирование; частота не выше `PREVIEW_FPS` и частоты обработанных кадров. На камеру не более одного кодирования; на зрителя очередь 1 (latest-only), медленная отправка ограничена 2 с. Остановка/смена сессии закрывает сокет. UI переподключается с backoff 0.5…8 с, не рисует старые рамки на новом кадре, освобождает ImageBitmap и помечает кадр устаревшим через 3 с. Плитки вне viewport не подписываются.

Неизвестная камера или запрещённый Origin → close 1008. Разрешены same-origin и `PREVIEW_ALLOWED_ORIGINS` (JSON-массив). Это защита границы браузера, не авторизация: доступ только в доверенной локальной сети. Авторизация оператора не реализована.

## Опасные зоны (Milestone 6)

| Запрос | Ответ |
|---|---|
| `GET /api/v1/cameras/{camera_id}/zones` | `200 [ZoneRead]`, порядок created_at/id |
| `POST /api/v1/cameras/{camera_id}/zones` | `201 ZoneRead` |
| `PUT /api/v1/cameras/{camera_id}/zones/{zone_id}` | `200 ZoneRead`, полная замена формы |
| `DELETE /api/v1/cameras/{camera_id}/zones/{zone_id}` | `204` |

POST/PUT: `{name, points:[{x,y},...], enabled:true}`. Имя 1..100 символов после trim; 3..64 разных точек, координаты 0..1, ненулевая площадь, без самопересечений/самокасаний/наложений. Закрывающая первая точка не повторяется. Ошибки геометрии → 422 VALIDATION_ERROR. Ответ дополнен id/camera_id/created_at/updated_at. Чужой zone_id → 404 ZONE_NOT_FOUND; удалённый родитель → 404 CAMERA_NOT_FOUND. До 16 зон на камеру; сверх лимита → 422 UNPROCESSABLE.

CRUD публикует camera.changed после commit, worker получает обновлённый CameraSpec; потерянное уведомление восстанавливается периодической сверкой. Тот же источник сохраняет run/track IDs. `config` PUT также заменяет три nullable интервала (0..3600 с), не патчит: передавайте все нужные переопределения.

Preview v1 дополнен `zones: [{id,camera_id,name,points,enabled}]` — только включённые зоны из spec этого кадра. Поле additive; старые пакеты без zones принимаются. Состояние IN_DANGER_ZONE отображается красной рамкой, LOST не рисуется. **Отдельного SSE/event API пока нет**: сгенерированный DomainEvent находится в DetectionResult и JSON-логе worker, не является надёжно сохранённой историей.
