# ADR-018. Типы API на frontend

Статус: принято (Milestone 1)

Типы TypeScript генерируются из OpenAPI FastAPI (`openapi-typescript`) в `frontend/src/api/generated.ts`, команда `npm run api:types`; CI проверяет, что сгенерированный файл актуален. Тонкий клиент на `fetch` поверх этих типов, без генерации всего клиента. DTO WebSocket/SSE описаны в OpenAPI через `shared/telemetry`.

**Почему:** Единый контракт (§154) без тяжёлого генератора клиента.
