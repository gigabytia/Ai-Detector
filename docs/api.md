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
| `GET /health/ready` | `200`/`503`: `{"status":"ready","redis_ok":true,"last_heartbeat_at":"…"}`. С Milestone 4 добавится «модель загружена». |
| `GET /status` | runtime-статусы камер этого worker'а (как `runtime` выше, плюс `camera_id`, `run_id`) — для отладки |
