# API

Интерактивная документация — `http://localhost:8000/docs` (OpenAPI генерируется FastAPI). Контракт для frontend — `frontend/openapi.json`.

## Ошибки

Все ошибки возвращаются в одном формате:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": [{"loc": ["body", "name"], "msg": "Field required"}]}}
```

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

## Health (vision worker, порт 8001)

| Запрос | Ответ |
|---|---|
| `GET /health/live` | `200 {"status":"alive"}` |
| `GET /health/ready` | `200`/`503`: `{"status":"ready","redis_ok":true,"last_heartbeat_at":"…"}`. С Milestone 4 добавится «модель загружена». |
