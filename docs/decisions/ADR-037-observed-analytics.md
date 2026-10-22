# ADR-037 — Наблюдаемая аналитика и завершённый track timeline

Статус: принято в M10. Дополняет ADR-019/034; уточняет ранний план analytics_aggregates в database.md.

## Решение

Worker collector получает только accepted results после stale-run guard на event loop. Никаких сетевых/SQL вызовов в inference. Хранит последнее наблюдение секунды по camera/run и отдаёт его при переходе секунды/stop. Последний частичный бакет flush при stop. UUID5(camera,run,second), retry не создаёт дубль. CameraSample persons — detections count; in-zone — состояние треков. Значения могут различаться из-за подтверждения/LOST; это не количество идентифицированных посетителей.

Среднее/максимум — по этим сохранённым observations; это сознательно более простой MVP, **не** ранний план frame-weighted persons_avg/persons_max. Мы не называем sampled max истинным пиком. observed_seconds суммирует consecutive captured_at gaps≤2с, без extrapolation; большие gaps исключены. Интервал относится конечной секунде и потому на границах фильтра приблизителен. Gap не создаёт нулевые строки.

Track session = camera/run/track ID от первого подтверждённого наблюдения до последнего, только после removal/lifecycle/graceful shutdown. Состояния NORMAL/IN_DANGER_ZONE/LOST; разрыв наблюдений>2с между retained track observations становится LOST. Нет новых domain states/rules. Cap4096 активных track records,2048segments с явным truncated; незавершённые при crash теряются (ADR-019). Нет periodic active-track persistence/re-ID. Выборка — перекрывающие период завершённые сессии, полностью, keyset(end,id).

Отдельный bounded1000 RAM outbox, Stream ad:analytics:ingest, group analytics-db, dead ad:analytics:dead max1000. XADD retry с тем жеUUID, consumer commit→ACK/XDEL, pending/reclaim30с. Payload≤512KiB, schema extra forbid; poison→dead; unknown camera reference отбрасывается с warning (не создаёт orphan FK). Путь не публикует alarm pub/sub и не меняет существующую event transaction. Full/outage после2с shutdown drain может терять analytics; лог/diagnostics, не блок inference/alarm. RAM и AOF everysec не являются exactly-once durable capture. DB insert идемпотентен после фактической доставки.

Backend выполняет агрегаты SQL в одном read-only REPEATABLE READ snapshot. UTC-aware [start,end), default24ч, max31д,≤120 бакетов. False positive — текущий статус события, входит в total. Denominator average events — все выбранные зарегистрированные камеры, включая архивные/disabled/нулевые; пустой набор→null. Active cameras отдельным Redis read (RUNNING/DEGRADED), ошибка→null, это now и не часть исторического snapshot. PG error→503, не нули.

ECharts/SVG на lazy dashboard route, не самописный canvas. People chart только одной камеры: не складываем несовпадающие по времени observations разных камер. Внутри chart bucket среднее observations, без интерполяции gaps. Отдельный TrackTimeline с пропорциональными state spans и точным accessible list; не CameraCard. UI фильтры1ч/24ч/7д + ручное обновление фиксированного окна; loading/empty/error/retry отличимы.

## Последствия

Нет покадровой записи/DB в worker, ограничены память/размер ответа. Аналитика приблизительна и неполна при crash/drop, завершённые треки запаздывают. Новые таблицы пока **без retention/rollup**: мониторить рост/backup/disk;≤31д не ограничивает хранение. Более точные aggregates/retention — отдельная миграция после измерений, не скрытое обещание M10. Lazy ECharts chunk ~557kB/~189kB gzip, предупреждение размера сохранено. Нет auth/CSV/loitering в M10.
