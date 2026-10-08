# ADR-021. Значения по умолчанию, не заданные в ТЗ

Статус: принято (Milestone 1)

Выбраны агентом и помечены **[агент]** в `docs/behavior.md`: `TARGET_FPS=10` (реалистично для 1–2 камер на CPU с nano-моделью), `INFERENCE_BATCH_SIZE=4`, `INFERENCE_MAX_WAIT_MS=20`, `EVENT_MIN_TRACK_HITS=3`, `ZONE_EXIT_GRACE_SECONDS=0.5`, `LINE_HYSTERESIS=0.01`, `SNAPSHOT_RETENTION_DAYS=30`, `PREVIEW_FPS=5`, `PREVIEW_MAX_WIDTH=640`, backoff 1→30 с, `MAX_CAMERAS=8`, лимиты загрузки, `WORKER_OUTBOX_MAX_ITEMS=10000`. Временного сглаживания anchor (EMA) нет: дребезг гасят dwell, grace, hysteresis и минимальный возраст трека (§138). Все значения пересматриваются после замеров в Milestone 12.

**Почему:** Нужны рабочие значения; при отсутствии данных выбраны консервативные.
