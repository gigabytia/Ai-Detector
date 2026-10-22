# ADR-034. Event bus, ingest и realtime M7

Статус: принято, Milestone 7. Уточняет ADR-004/017.

## Транспорт и гарантии

* `EventPublisher.offer()` вызывается scheduler только для актуального run. Отдельная async-задача отправляет DomainEvent через Lua: `XADD ad:ingest * event {json}`, временный маркер ожидания записи и `PUBLISH ad:events:live {json}`. Inference не ждёт Redis. Очередь ограничена 1000 ожидающими событиями плюс одно in-flight; backoff 0.25…5 с. После неоднозначного сетевого результата возможна повторная публикация **того же UUID**. Это at-least-once, не exactly-once transport.
* Redis недоступен: обработка камер продолжается, readiness worker = 503, RAM-outbox повторяет отправку. Переполнение — CRITICAL с event_id, счётчик dropped, readiness остаётся 503 до перезапуска. Shutdown пытается отправить остаток в пределах 2 с после завершения текущей операции (её socket timeout до 5 с), иначе явно логирует число недоставленных событий.
* **RAM-outbox не переживает аварийное падение worker.** После успешного XADD сохранность зависит от Redis AOF/репликации/диска. Compose включает AOF с обычным everysec, а не fsync на каждое событие: авария Redis/хоста может потерять последнее окно записи. Это не гарантия нулевой потери при любых отказах. Для неё нужен отдельный дисковый outbox/более строгая инфраструктура.
* Input Stream намеренно **не MAXLEN-trimmed**: при долгом отказе PostgreSQL backlog растёт. Нужны мониторинг диска/памяти, AOF, `maxmemory-policy noeviction` и резервное копирование. Нельзя вручную FLUSHDB/XTRIM входной очереди. Это standalone Redis, не Redis Cluster.

## Ingest

В каждом API-процессе consumer `api-{uuid}` в единственной группе `api-ingest`. Группа создаётся с `0`/MKSTREAM, поэтому события, отправленные до старта API, не пропускаются. Пакет ≤200 сообщений, одна AsyncSession/транзакция. Сначала собственные pending, затем XAUTOCLAIM чужих pending с idle ≥30 с, затем новые сообщения. Ошибка Redis/БД — backoff без ACK.

После PostgreSQL commit: Redis transaction `DEL` временных маркеров, `XACK`, `XDEL`. Потеря ответа после commit безопасна: `INSERT ON CONFLICT(id) DO NOTHING` не меняет существующие status/note/audit. Удалять запись из Stream можно, потому что durable consumer group сейчас одна; перед добавлением другой группы политику XDEL надо изменить.

Невалидный JSON/схема, payload >64 KiB, отсутствующий camera_id → bounded `ad:ingest:dead` (примерно 1000 записей), ACK и XDEL одной Redis-транзакцией после commit валидной части пакета. Неизвестная/удалённая зона не уничтожает событие: nullable FK; существующие зоны блокируются key-share до вставки. Soft-delete камеры сохраняет историю. Строка events хранит source_ts_ms как float, сохраняя дробные миллисекунды текущего Frame.

## API, SSE и оператор

REST `/events` — keyset pagination по `(occurred_at DESC,id DESC)`, limit 1…200, фильтры camera_id/status; `/events/{id}` — чтение/PATCH. Только `NEW → ACKNOWLEDGED | FALSE_POSITIVE`; повтор уже выбранного статуса идемпотентен, смена финального — 409. Row lock сериализует операторов. Заметка ≤2000 символов, в любом статусе; отсутствие note не стирает её, null очищает. Audit timestamp фиксируется один раз.

Опубликованный, но ещё не записанный UUID → `409 EVENT_NOT_PERSISTED_YET` (маркер до 24 ч; удаляется после успешного ingest), frontend делает до четырёх ограниченных повторов. История недоступна → 503. Commit статуса не зависит от pub/sub: ошибка уведомления не откатывает БД; REST resync исправляет UI.

Один LiveHub/pubsub на API-процесс, одна очередь 128 на SSE-клиента. `event.created` — DomainEvent без запроса в БД (работает при её отказе); `event.updated` — EventRead; `camera.status` — уведомление для REST refresh. `resync` при подключении/восстановлении Redis, `unavailable` при его отказе; heartbeat-комментарий раз в 10 с. Нет SSE replay/Last-Event-ID: история восстанавливается через REST, не обещается повтор тревожных toast за время отключения. Медленный клиент отключается с resync вместо тихой потери тревог. Отключение удаляет очередь. Uvicorn API ограничивает graceful drain 3 с, чтобы открытый SSE не блокировал SIGTERM; после cancel generator/lifespan выполняют cleanup.

Frontend держит один EventSource на приложение, последние 200 ещё не сопоставленных live alarm и bounded dedupe последних 2000 UUID. История пагинирована независимо от этого лимита. Уведомления/переподключение инвалидируют Query; каждые 15 с REST reconciliation. Камеры: SSE-triggered REST до 1 раза/с, fallback polling 2 с при разрыве, 15 с при подключении. Это не сохранённые аналитические агрегаты.

Фоновые API-задачи контролируются readiness `event_delivery`; неожиданный выход логируется и даёт 503. Ошибка publisher также отражается в readiness worker.

## Отдельная WS-телеметрия

Браузер `/live/cameras/{id}/telemetry`, напрямую worker `/cameras/{id}/telemetry`. Та же проверка Origin/lifecycle, что у preview; JSON без JPEG, до 5 сообщений/с, latest-only очередь 1, timeout отправки 2 с. Payload: version/camera_id/run_id/frame_id/captured_at/source_ts_ms/inference_ms, persons, persons_in_zone, tracks (normalized bbox/confidence/state/ID). Смена/остановка session закрывает сокет. На focus-странице независимые счётчики, reconnect 0.5…8 с, stale через 3 с. Рамки продолжают рисоваться **только из атомарного preview-пакета**, а не из несинхронной telemetry.

## Не входит

Snapshots/event detail с изображением — M8. Линии, loitering, запись track sessions и аналитики, CSV/расширенные фильтры/retention, авторизация — последующие этапы. API и worker доступны только в доверенной локальной сети. Windows, Docker/CI, GPU и настоящая RTSP-камера на M7 не проверялись.
