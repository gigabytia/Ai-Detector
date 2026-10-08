# ADR-002. Отдельный vision worker

Статус: принято (Milestone 1)

Inference, захват и правила работают в отдельном процессе vision-worker. Модель загружается один раз на worker. Worker **не подключается к PostgreSQL**: конфигурацию камер он получает через internal REST API (`/api/v1/internal/worker/cameras`, токен `WORKER_API_TOKEN`), а результаты отправляет в Redis. Внутри: поток захвата на камеру, один поток inference (detector + tracker + правила последовательно), пул потоков для JPEG, asyncio для I/O.

**Почему:** Иначе worker пришлось бы зависеть от моделей SQLAlchemy backend'а или дублировать их. Один поток inference избавляет от блокировок вокруг состояния трекеров.
