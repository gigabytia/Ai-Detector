# ADR-038 — Loitering и полный bounded CSV

Статус: принято в M11. Дополняет ADR-008/010/014/033/034/035/037.

## Loitering

Расширяем Visit в существующем ZoneEngine, не создаём второй zone membership автомат. Identity camera/run/track/zone. Continuous observed-inside duration = (source_ts_ms − loiter_since)/1000, без накопления float drift по кадрам. Входной dwell включён, событие возможно только в INSIDE после min track hits. Порог строго превышен, default10с. Не вводим LOITERING PersonState.

Outside sample, LOST, backward source time или inter-frame source gap>2с сбрасывают timer, recovery начинает с нового inside sample. Обычные M6 entry/grace timers не изменены. Fired marker сохраняется при коротком выходе/occlusion, сбрасывается после confirmed exit. Одно срабатывание/попытка на визит; independent loitering cooldown wall-clock/type/track без zone_id по ADR-008 может подавить другую зону. Disable/delete/geometry/track removal/epoch/size/run/lifecycle очищают соответствующие Visit; rename не очищает. Hot threshold применяется на следующем immutable camera spec, не перевооружает fired visit. Снижение порога может немедленно дать первый alarm.

Typed LoiteringMetadata: bbox/anchor, historical zone_name, duration_seconds>threshold_seconds, stability1. Confidence = confidence текущего matched track, stability1 относится к непрерывному наблюдаемому интервалу, не вероятность истинности/качество re-ID. Source duration и captured_at не смешаны. Событие проходит прежние independent alarm publish/Stream/commit-before-ACK/UUID/SSE/snapshot/operator state, без нового транспортного пути.

API default LOITERING_THRESHOLD_SECONDS=10 и nullable camera override0..3600 с CHECK, worker SEVERITY_LOITERING=warning. M11 migration b6b7cfcd87c5 послеa9345caf81b1. Согласованное обновление API/worker/UI из-за strict config/event types; rollback старых binary после новых events отдельно планировать.

## CSV и фильтры

Один predicate builder list/export: optional camera/status/event_type/start/end, aware UTC-normalized [start,end). No implicit NEW-only/FP exclusion. Soft-deleted camera names остаются. Один projected SQL SELECT с outer snapshot join и deterministic occurred_at/id DESC — один snapshot, без ORM N+1. Export не принимает cursor/limit страницы и не включает live-pending. Timeout SQL15с. Поля19, без camera source credentials/storage_key/самих JPEG. ДатаUTC ISO8601Z, metadata compact JSON, null пусто.

Buffered complete CSV UTF8 BOM/comma/CRLF, csv.writer quoting/multiline, spreadsheet formula mitigation апострофом при unsafe leading chars/whitespace formula. CSV quoting само по себе формулы не обезвреживает. Это mitigation, не универсальная гарантия native importers. Выгрузка содержит notes/metadata, обращаться как со служебными данными.

Максимум50000 строк/20MiB, запрос≤50001 rows для обнаружения overflow. При превышении422 EXPORT_TOO_LARGE до200/attachment, не усечённый report; PG/timeout503 JSON. CPU codec через to_thread, не event-loop. Выбран bounded buffering вместо streaming headers200 до возможной ошибки посреди файла. Цена — память проекции/CSV и отсутствие unlimited/background export; concurrent-heavy load не проверен, trusted-network MVP. Нет произвольной server-side пути записи. Browser Blob link download, cleanup/revoke, abort при unmount. Фильтры snapshot на click; будущие UI изменения не меняют текущий request.

UI: camera/status/type/All-time либо fixed1ч/24ч/7д, refresh периода, общие условия для REST/live/export. Для больших All-time файлов сузить период. Empty CSV содержит толькоheader;503/error не скачивается как CSV. Новые labels/toasts/details и настройки локализованы. Нет новых зависимостей.

## Проверка/границы

Unit fake timestamps проверяют threshold equality, lost/outside/gaps, once/exit/reset/hot config/typed metadata. Integration проверяет persisted replay/operator state, CSV>page50/half-open/FP/type/archived/empty/error/caps. CSV parsed csv+pandas, Chromium download, не native Excel UI. Нет zero-loss обещания: RAM/AOF/active-track crash/retention ограничения прежние. M12 — сначала замеры, потом оптимизация.
