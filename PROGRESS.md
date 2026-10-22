# PROGRESS

Читать в начале каждой сессии.

## Текущий этап

**Milestone 15 — сохраняемый CPU/CUDA-профиль.** База полный M14 ca55552; единый uv.lock с default CPU и исключающей CUDA13.0 группой (torch2.14.1/torchvision0.29.1), preflight versions/build/real matmul+NMS, fail-closed, отдельный локальный выбор без перезаписи .env. GPU_WINDOWS.md и UPDATE_MILESTONE_15.md. Первая GPU-команда `.\start.cmd --profile cuda`, затем обычный start.cmd. Physical GPU/Windows acceptance требует компьютера пользователя; прежние production gates открыты.

### Исторический M14

**Milestone 14 — локальный запуск после распаковки.** База полный M13 c76adca, настоящая Git-история и веса сохранены. Fixed npm lint trio/lock, preinstall guard/strict engines, IPv4 Redis defaults, start.cmd → Python launcher с frozen installs, infrastructure/protocol preflight, migration/model checks, empty-only demo seed, readiness/logs/owned-process shutdown. START_WINDOWS.md и UPDATE_MILESTONE_14.md. Existing .env/data не перезаписывать/не паковать. QA в docs/qa/m14; Windows-native/контейнерный запуск не заявлять. Production NO-GO M13 сохраняется. Ниже этапы исторические.

Реализация заново восстановлена на базе присланного архива Milestone 3 после утраты предыдущего рабочего окружения. Это не побайтовое восстановление незавершённой сессии: использованы сохранённые архитектурные документы, ADR и доступный контекст. Исходный `AI_DETECTOR_v2_MASTER_PROMPT.md` в архиве отсутствовал.

## Milestone 13 — результат предыдущей сессии

4832 persisted events /4832 snapshots после controlled shutdown; SQL/CSV/dashboard ID sets согласованы, both Streams0. Выявленные проблемы и принятые решения — ADR-040. БД migration не добавлена, head b6b7cfcd87c5. Фактический scope и все незакрытые production gates см. AUDIT_REPORT: auth/target capacity/dependencies/licenses/durability не маскируются успешными тестами. Не пересоздавать Git, не включать private env/runtime/DB/video в архив.

## Milestone 12 — результат предыдущей сессии

База полный M11 `0a0aafd`, история/веса сохранены. Всего19 benchmark runs: initial baseline, tuning, исправления по замерам, repeats/ABBA; no speculative ONNX/TensorRT.

- Найден и исправлен reset `torch.set_num_threads`: Ultralytics CPU setup при первом predict перезаписывал request2 в actual1. После warmup настройка восстановлена, actual2 доступен в worker readiness и detector_info metric. Unit регрессии1/2/8 и реальный repeat на коде M11 подтверждают диагноз. Значение default2 сохранено, но CPU consumption реально увеличивается.
- Scheduler не ждёт недостижимый batch: по одному frame/camera; если все RUNNING/DEGRADED камеры уже выбраны, сбор заканчивается. Deadline20мс для других running камер, fair rotation/latest-only/target sampling/stop-stale guard сохранены. ABBA при одинаковом adapter2: local p50 legacy105.4→current93.3мс, p95134.7→125.2мс (по raw frames2×20с на policy), не обещание фиксированных20мс.
- Worker `/metrics`: standard process CPU/RSS, cumulative whole-call real/scripted detector и local monotonic latency histograms, batch size/wait/inflight, processed/errors/stale/generated alarm counters, live-camera gauges/FPS/depth/drops/tracks/result age, RAM outboxes/drops/health и cached heartbeat. С bounded labels, удалением stale camera children, no network I/O/PG на scrape. Не full observability platform: backend false-positive operator counter/GPU utilization/Redis backlog не выдуманы. prometheus-client0.26.0 frozen.
- Portable isolated benchmark CLI с source/model SHA, requested/effective threads, timings, resource samples, frame keys/counts, validation1..300с и no overwrite. RAW/единый evidence/independent numeric checks/report/chart в docs/qa/m12. Main matrix1/4/8: FPS/камера M11 9.61/3.63/1.84 → M12 9.76/5.81/3.00; local p95161.8/360.1/344.7 →114.0/238.0/234.3мс. Repeat8:15.51→23.24FPS total, CPU119.4→171.9% одного core. Short static-video CPU test, не RTSP SLA; цель10/камеру на4/8 не достигнута.
- Проверки: **254 Python unit,41 integration,129 frontend**, strict mypy172, Ruff174, linters/types/build Node24.15.0, alembic no diff/lock/OpenAPI match/production audit0. Compose mappings static only. Живой3-camera YOLO+mock: actual2, entry/loiter→CSV/history/JPEG,24 scrapes за12с Redis outage, processing продолжается, queue peak48, drops0, оба Streams0 после восстановления.

Shutdown worker1.01с/API с SSE3.16с,6 финальных sessions/оба Streams0 и5 JPEG после worker stop; CLI smoke/invalid args PASS. Доказательства и ограничения — docs/qa/m12/README.md. Frontend логика не менялась, browser/UI/visual QA M11 не заявляется повторно. ECharts chunk warning и dev audit4high прежние. Auth нет; trusted network. RAM/AOF/crash/snapshot/analytics retention ограничения M7–M11 сохраняются. GPU utilization/VRAM/CUDA, ONNX/TensorRT, real RTSP/moving accuracy, длительный4/8 full storage I/O, Docker/CI/Windows не проверены. Source MP4 runtime исключён из архива; exact rerun требует те же байты, любые другие clips — отдельный эксперимент.

Следующие работы: длительная end-to-end нагрузка/реальные потоки на целевом CPU/GPU и проверка deployment/security; не обещать throughput до измерений.

## Milestone 11 — результат предыдущей сессии

База — полный M10 `1f01891` (Kostya); Git не пересоздавался. В новом архиве настоящая `.git`, исходники, веса, QA и инструкция обновления.

### Сделано

* Loitering внутри существующей membership machine пары track/zone, без нового PersonState. Source timestamps, strict duration>threshold, entry dwell включён, одна попытка на confirmed visit. Таймер непрерывного наблюдения сбрасывается на outside/LOST/backward timestamp/gap>2с; fired marker сохраняется при jitter/occlusion до подтверждённого выхода. Геометрия/disable/removal/epoch/size/run/lifecycle сбрасывают соответствующие визиты. Независимый type/track cooldown по ADR-008, не блокируется cooldown входа.
* Typed LoiteringMetadata: историческое zone_name, bbox/anchor, duration/threshold/stability; тип PERSON_LOITERING_IN_DANGER_ZONE проходит прежний UUID/publish/ingest/SSE/snapshot/operator state и dashboard by_type. Снимок необязателен, его ошибка не отменяет тревогу.
* API default LOITERING_THRESHOLD_SECONDS=10, nullable override камеры0..3600 с горячим применением без смены run; worker SEVERITY_LOITERING=warning. Миграция b6b7cfcd87c5 добавляет только nullable camera_configs.loitering_threshold_seconds с CHECK. Compose env mappings добавлены, сами контейнеры не запускались.
* GET /api/v1/events/export: единый predicate builder с list (camera/status/type/aware start/end [start,end)), все persisted matching rows, включая soft-deleted камеры, deterministic order. Один projected SQL SELECT, не N+1; statement timeout15с, formatting вне event loop. Полный bounded CSV до50000строк/20МиБ, иначе422 EXPORT_TOO_LARGE без частичного200; PG error503 JSON до download.
* UTF-8 BOM/comma/CRLF/UTC, multiline quotes, null→empty, JSON metadata, numeric scores/IDs, без source credentials/storage_key. Spreadsheet formula mitigation апострофом. UI type/period filters общие list/live/export; frozen period + refresh, busy/error/retry, Blob download/revoke/cancel on unmount. Новый event label/toast/detail + duration/threshold, camera setting/i18n/OpenAPI/TS, ADR-038.

### Проверено

| Проверка | Результат |
|---|---|
| make check | **241 Python unit +129 Vitest**, strict mypy170 файлов, ruff/format/ESLint/Prettier/vue-tsc и production build на Node24.15.0 |
| PostgreSQL17/Valkey9 integration | **41 passed**: прежние37 + loitering delivery/replay/operator state, CSV71 строк при странице50/half-open/FP/type/archived/formula/empty/invalid, cap/503 JSON, config default/override/inherit/validation/internal worker spec |
| Живой pipeline | default10с mock → duration10.066666666666668с, один alarm того же track/visit с entry и JPEG1280×720. CPU YOLO на статичном bus MP4 →8 loitering events на точке проверки; hot threshold без смены run. Это не moving-CCTV accuracy benchmark |
| CSV/Chromium | скачанный CSV совпал с history IDs,19 столбцов/Unicode/BOM/quoted multiline/formula-note проверены csv+pandas. Browser filters/download/retry503/detail/UI threshold2с,390px light/dark без overflow/pageerror0; PNG/DOM, без экспертной оценки изображений |
| PostgreSQL outage | новый loitering alarm по SSE при offline DB, CSV503/JSON без attachment; после восстановления те же event/snapshot UUID и JPEG SHA-256, recovered event в CSV, оба backlog0 |
| Миграции/контракты | empty UTF8 DB, M10→M11, test-only downgrade/upgrade, no schema diff, lock/OpenAPI match, production npm audit0; Compose YAML/env проверены статически |

Graceful shutdown: worker0.54с/API с SSE3.22с, оба backlog0,7 новых completed sessions и5 читаемых JPEG после worker stop. Все доказательства — [docs/qa/m11/README.md](docs/qa/m11/README.md).

### Ограничения и следующий этап

Loitering консервативен при пропусках: LOST и gap>2с не считаются непрерывным пребыванием. Уже сработавший визит не создаёт повтор после короткого occlusion/jitter; cooldown без zone_id может подавить одновременный alarm другой зоны. Hot decrease может сработать на следующем кадре, но не перевооружает fired visit. Stability1 означает текущий непрерывный observed interval, не вероятность истинности события.

CSV — синхронная bounded выгрузка, не background job/stream unlimited. DB projection≤50001 rows, buffered result/CSV потребляют память; codec в thread, но много параллельных exports отдельно не нагрузочно тестировалось. Caps проверены также уменьшенными тестовыми пределами, не50k-row стресс-прогоном. Содержит operator notes/metadata: хранить как служебные данные. Апостроф — mitigation для spreadsheet imports, не гарантия поведения всех Excel/importers. Native Excel/LibreOffice import не проверялся. При смене фильтров во время download используется snapshot фильтров на момент клика. CSV не содержит снимки или live-pending, snapshot_id может отсутствовать/истечь. Нет авторизации, trusted-network only.

Прежние RAM/AOF/active-track crash/storage/analytics-retention ограничения сохраняются. Redis outage отдельно для M11 не повторялся (M10 coverage остаётся), Docker/CI/Windows/GPU/RTSP/4–8-camera performance и реальная moving-CCTV accuracy не проверены. Lazy ECharts chunk ~557kB/~189kB gzip по-прежнему предупреждает о размере, production build успешен. Dev audit4high прежнего дерева не исправлялись; production0.

Следующий — **M12: сначала измерить latency/FPS/GPU/CPU/RAM/queue depth, затем оптимизировать** (§172), не обещать throughput без замеров.

## Milestone 10 — результат предыдущей сессии

База — полный M9, `c30a4d8` (Kostya), восстановленный из проверенного полного архива. История не пересоздана. Исходники, веса, QA и настоящая `.git` включены в новый архив.

### Сделано

* Отдельный bounded analytics outbox/Redis Stream → backend ingest → camera_samples и track_sessions. До одного последнего наблюдения в секунду, не покадровый INSERT. UUID5 при retry, commit перед ACK/XDEL, pending/reclaim и poison dead letter; тревоги идут прежним независимым путём.
* Collector завершает track session при удалении трека, stop/restart камеры и graceful shutdown. Сегменты NORMAL/IN_DANGER_ZONE/LOST; gap >2 с явно LOST, максимум2048 сегментов с truncated marker. Identity camera/run/track, не re-ID/уникальные посетители.
* Миграция a9345caf81b1 после M9; прежние камеры, геометрия, события и снимки сохранены. REST dashboard с SQL GROUP BY в одном read-only REPEATABLE READ snapshot, UTC [start,end), максимум31 день и120 временных бакетов. Completed-track keyset pagination, limit≤50.
* Dashboard: total/critical/false positives, active-now cameras (nullable при Redis error), average events per registered camera, completed tracks; ECharts/SVG события по времени/камерам/типам, статистика камер и отдельный TrackTimeline. Фильтры1ч/24ч/7д, камера, ручное обновление, loading/empty/error/retry, mobile/light/dark. People chart только выбранной камеры, пропуски не превращаются в нули.
* OpenAPI/TS, ADR-037, QA и UPDATE_MILESTONE_10.md. Зафиксировано отличие от раннего целевого analytics_aggregates: фактически хранятся последние 1Hz observations; среднее и максимум не frame-weighted и не истинный покадровый пик. Observed seconds — сумма коротких межкадровых интервалов, не uptime.

### Проверено

| Проверка | Результат |
|---|---|
| make check | ruff/format, strict mypy **168 файлов**, ESLint/Prettier/vue-tsc, **213 Python unit +123 Vitest**, production build на **Node24.15.0** |
| PostgreSQL17/Valkey9 integration | **37 passed**: предыдущие33 + dashboard cross-foot/half-open/UTC offsets/archived/nulls, keyset ties/overlap, ingest replay/poison/rollback и invalid/empty states |
| Живой стенд | 2 mock + CPU YOLO на статичном bus MP4; fixed-window SQL = dashboard = суммы всех3 event breakdown:47. На точке проверки862 observations,100 completed sessions; stop → active0/Stream0 |
| PostgreSQL outage | dashboard503, inference продолжает;22 pending analytics UUID сохранены после восстановления, backlog0 |
| Redis outage8с |24 наблюдения периода доставлены после AOF restart, backlog0; живой worker/RAM queue, не гарантия сохранности при падении процесса |
| Chromium |3 ECharts SVG непустых, фильтры, people chart, раскрытие timeline,390px без overflow, error не показывает нули/retry, pageerror0; PNG/DOM/layout, без экспертной оценки изображений |
| Миграции/контракты | empty UTF8 DB, M9→M10, downgrade/upgrade test-only, alembic check no diff, frozen lock/OpenAPI match, production npm audit0 |

Graceful shutdown: worker **0.82с**, API с SSE **3.22с**, оба Streams0/runtime keys removed;7 новых финальных sessions и5 JPEG после worker stop.

Полные доказательства и логи — [docs/qa/m10/README.md](docs/qa/m10/README.md).

### Ограничения и следующий этап

* Незавершённые треки при аварии worker теряются (ADR-019); live-active sessions не записываются каждыеNсек. RAM outbox1000 и AOF everysec имеют окно потери; переполнение аналитики логируется/видно в worker readiness, inference/alarms продолжаются. Collector≤4096 активных треков;2048 segments/session, payload≤512KiB.
* 1Hz last sample: mean/max не всекадровые, no-observation=null, factual zero=0. Observed seconds не wall-clock uptime: gap>2с исключён, короткий gap начисляется конечной секунде, границы периода приблизительны. Occupancy по разным камерам не суммируется. Все зарегистрированные, включая archived/zero-event, входят в знаменатель среднего событий; false positives включены в total, их статус текущий.
* Автоматического retention/rollup для новых таблиц нет: контролировать рост, indexes/backup/disk/Stream. До31д/120бакетов ограничивает ответ, не объём сохраняемой истории. Full track session при пересечении окна не обрезается по фильтру. Live cameras из Redis не часть исторического MVCC snapshot.
* Lazy ECharts route chunk ~557kB minified/~189kB gzip даёт предупреждение Vite >500kB; build успешен, размер не скрыт. Dev audit4high из прежних зависимостей, production0.
* Нет auth/CSV/loitering; trusted-network only. Windows, Docker/CI, GPU, RTSP, moving-CCTV accuracy и4/8-camera throughput в M10 не проверены. Статичное YOLO видео — регрессия интеграции, не качество трекинга на реальном движении. Прежние snapshot/disk/retention ограничения сохраняются.

Следующий — **M11: loitering и экспорт событий CSV** (§171), без преждевременной оптимизации M12.

## Milestone 9 — результат предыдущей сессии

База — полный M8, HEAD `01ff302` (Kostya). История не пересоздавалась; новый архив содержит настоящую `.git`, исходники, веса и QA. Прежние разделы ниже — история этапов.

### Сделано

* Camera-scoped CRUD lines, max16 под parent row lock, normalized distinct ordered P1/P2, enabled/name/timestamps. Миграция `e2c6db45c9b8`, nullable events.line_id с SET NULL; geometry/name исторического события не исчезают при редактировании/удалении.
* Per-run LineEngine после ZoneEngine: bottom anchor, signed distance/hysteresis0.01, finite segment projection, обе стороны; baseline без тревоги, LOST freeze и crossing при recovery. Min hits3, bounded confidence window, wall-clock cooldown camera/run/track/type (общий линиям, отдельный от зоны). Crossing не создаёт PersonState.
* Side reset при geometry/disable/delete; rename сохраняет side; source epoch/discontinuity/size/run/lifecycle очищают scene. Hot worker spec/atomic preview lines без смены run.
* Typed PERSON_CROSSED_LINE/LineCrossMetadata, validator соответствия refs/type/metadata, line ownership при ingest. Прежний M7/M8 путь SSE/history/snapshot/status/note, optional JPEG; исторические line_name/endpoints/direction сохранены.
* Редактор первой линии: две упорядоченные точки на кадре/keyboard, undo/clear/cancel/enable/save/delete-confirm, взаимная блокировка с зоной, arrow/P1/P2 preview. Новый alarm title и детали с сохранённой линией/направлением поверх исходного JPEG. OpenAPI/TS, ADR-036 и UPDATE_MILESTONE_9.md.

### Проверено

| Проверка | Результат |
|---|---|
| make check | ruff/format, strict mypy **158 файлов**, ESLint/Prettier/vue-tsc, **199 Python unit + 115 Vitest**, production build |
| PostgreSQL/Valkey integration | **33 passed**: прежние29 + line CRUD/notify/scope/spec/limit, event+snapshot/replay/operator state, historical geometry/delete и cross-camera FK |
| Живой поток | Оба signed направления при развороте endpoints mock-линии, JPEG1280×720; hot geometry и disable22с/re-enable без смены run, старые metadata неизменны |
| PostgreSQL outage | PERSON_CROSSED_LINE по SSE до ingest, JPEG уже записан, PATCH409; после восстановления тот же event/snapshot UUID и JPEG SHA-256, backlog0 |
| Chromium | Historical SVG coordinates, note persisted, keyboard editor→REST→hot preview, click cap2/undo/cancel, zone edit blocked; 390px без overflow, pageerror0; PNG/DOM/layout, без экспертной visual оценки |
| Миграции/контракты | Пустая UTF8 DB, M8→M9, downgrade/upgrade test-only, alembic no diff, frozen lock/OpenAPI match, production audit0 |

Shutdown worker **1.19с**, API с SSE **3.24с**, runtime keys удалены/Stream0, JPEG доступны после worker stop. Доказательства — [docs/qa/m9/README.md](docs/qa/m9/README.md), обновление — [UPDATE_MILESTONE_9.md](UPDATE_MILESTONE_9.md).

### Ограничения и следующий этап

Для локализованных имён в JSONB нужен PostgreSQL UTF8. Исходные SQL_ASCII sandbox базы сохранены, QA перенесён backup/restore в отдельную UTF8 базу; схема сама кодировку не меняет. Новый type требует согласованного обновления API/worker. Line CRUD до16, редактор только первой с явной подсказкой; direction относительно P1→P2, не экрана. Нет direction filter/loitering/track sessions/CSV/auth/dashboard. Качество crossings на реальном движущемся CCTV, Windows, Docker/CI, GPU, RTSP и нагрузка4/8 не проверялись; CPU YOLO на статичном bus MP4 — только регрессия существующего пути. Redis outage M8 не повторялся, RAM/AOF/filesystem/retention ограничения сохраняются. Node24.14.1 sandbox ниже engine: использовать поддерживаемый Node.

Следующий — **M10: dashboard, event statistics, camera statistics, timeline**. Не смешивать с будущим loitering.

## Milestone 8 — результат предыдущей сессии

База — полный M7, HEAD `2d6aca3` (Kostya). Реальная полная `.git` и цепочка M4 → M5 → M6 → M7 сохранены; новый архив содержит и M8. Прежние результаты ниже — история этапов, не описание текущих ограничений, если M8 их явно снимает.

### Сделано

* Shared stdlib SnapshotStorage/LocalSnapshotStorage, полный исходный JPEG качества 90 без графики. Atomic temp+fsync+replace, UUID/UTC key, canonical path validation, отказ от symlink-компонентов; worker пишет, API читает/чистит один private directory/volume.
* SnapshotWriter: отдельный thread pool (2), максимум 4 ожидающих/обрабатываемых задания. Снимок только при событии, inference не ждёт JPEG/диск/Redis. При disabled/overflow/codec/disk error публикуется сама тревога без снимка. Shutdown сначала останавливает inference, затем дожидается снимков, затем завершает event delivery.
* EventMessage с optional SnapshotMetadata. Один ingest payload, event + metadata одной транзакцией PostgreSQL; ACK после commit. Legacy M7 payload и повреждённый optional snapshot не теряют валидную тревогу. Повтор не меняет status/note, expired metadata не воскрешается. Pub/sub отдаёт только DomainEvent, без storage_key.
* Миграция `48f1a410c0ce`: snapshots (unique event_id, file metadata), nullable camera_configs.snapshot_enabled. API defaults + hot three-state camera override (inherit/on/off), без смены run. Shared SNAPSHOT_PATH, compose volume, retention 30 дней по умолчанию.
* UUID-only JPEG API `/api/v1/snapshots/{id}`, 404 missing/expired, nosniff/private no-store; EventRead дополняется snapshot id/url/width/height. История старых и soft-deleted камер сохраняется.
* API retention под token-owned Redis lease с renewal/compare-delete. Batches 100; сначала файл, потом metadata, ошибка удаления остаётся retryable; события не удаляются. Старые orphan JPEG и atomic temp очищаются консервативно по mtime.
* `/events/:eventId`: исходный кадр, переключаемые исторические bbox/anchor поверх него, status/note и метаданные; явные empty/missing/error/loading states, retry. Не подставляется текущая геометрия камеры. Journal links, mobile/light/dark, OpenAPI/TS/ADR-035 и upgrade guide.

### Проверено

| Проверка | Результат |
|---|---|
| make check | ruff/format, strict mypy **150 файлов**, ESLint/Prettier/vue-tsc, **177 Python unit + 103 Vitest**, production build |
| Real PostgreSQL/Valkey integration | **29 passed**: прежние API, snapshot transaction rollback/retry, duplicate/operator state, REST JPEG/404/soft delete, bad optional attachment fallback, retention/orphans/failed delete, no expired resurrection, private live payload, lock ownership |
| Живые камеры | YOLO/ByteTrack MP4: snapshot **810×1080**, preview **640×853**; mock: **1280×720**, preview **640×360**. Hot off/on даёт события без/со снимком в том же run |
| PostgreSQL полностью остановлена | SSE alarm + файл до ingest, PATCH 409; после возврата тот же event UUID/snapshot UUID и SHA-256 JPEG, backlog 0 |
| Redis остановлен на 21 с | worker not ready, run IDs сохранены; **13 событий и 13 снимков** доставлены после восстановления, backlog 0 |
| Chromium | Историческая рамка совпадает с image/normalized coordinates, overlay toggle, note save, no-snapshot и missing-file retry, event404 и journal navigation; 390px без overflow, pageerror 0. PNG сохранены; visual image viewer не использован |
| Контракты/миграции/зависимости | M7→M8, downgrade/upgrade на тестовой БД, alembic check без diff, frozen lock/OpenAPI match; production audit 0 vulnerabilities |

Shutdown: worker **0.66 с**, API с открытым SSE **3.18 с**, runtime keys удалены/Stream0; JPEG читаются после остановки worker. Доказательства и скрипты — [docs/qa/m8/README.md](docs/qa/m8/README.md). Обновление — [UPDATE_MILESTONE_8.md](UPDATE_MILESTONE_8.md).

### Ограничения и следующий этап

Файл и PostgreSQL не являются одной распределённой транзакцией: авария до XADD может оставить orphan, позднее удаляемый retention. RAM-outbox и AOF everysec имеют прежние окна потери. Задания JPEG bounded, но сам локальный disk syscall не имеет гарантированного deadline; зависший filesystem может задержать drain. Storage root должен быть доверенным, не writable для посторонних; это не sandbox против adversarial filesystem races. API и worker на разных хостах требуют shared mount/будущий другой SnapshotStorage. Backup БД и файлов согласовывать; это не HA object storage.

Retaining files требует мониторинга диска/Stream/cleanup logs; metadata может временно ссылаться на отсутствующий файл — UI это обрабатывает. Retention — техническое удаление снимков, а не настройка срока хранения всей истории. Текущая зона не рисуется на старом кадре: сохранены bbox/anchor, не polygon/name snapshot. Автоматического before/after, CSV, авторизации, track sessions и dashboard ещё нет.

Следующий — **Milestone 9: линия, crossing detection и событие**. Windows, Docker/CI, GPU, RTSP, moving-CCTV quality и 4/8-camera нагрузка не проверены. Sandbox Node 24.14.1 ниже package engine; использовать поддерживаемый Node. Все прежние ограничения сохраняются, если выше явно не сняты.

## Milestone 7 — результат предыдущей сессии

База: проверенный полный архив M6, SHA-256 `45cded322ea60069a4a53e87f7e093ebe403ace34afa2976606874e5c958f909`, HEAD `4995cae`. Полная `.git` восстановлена и сохраняется в новом архиве. Коммит оформляется от **Kostya** с исходной Git-идентичностью.

### Сделано

* Bounded RAM-outbox worker, retry, Lua Stream+pub/sub, UUID при повторе. Inference не ждёт Redis; overflow/ошибка доставки отражены в readiness и логах.
* events и миграция `14d6499b16a2`; ingest ≤200, одна транзакция, idempotent INSERT, ACK/XDEL после commit, pending retry/reclaim ≥30 с, bounded dead letter. Нет покадровой записи.
* REST history/read/status/note, keyset pagination, camera/status filters, row-lock переходы NEW → ACK/FP с audit. 409 pending + ограниченные frontend retries. История мягко удалённых камер сохраняется.
* SSE fanout без запросов к БД, heartbeat, reconnect/resync/overflow cleanup, одно подключение frontend + periodic REST reconciliation. Отдельная latest-only JSON WS-телеметрия и focus-счётчики без смешивания с preview-рамками.
* Панель событий: live alarm до persistence, история, фильтры, pagination, ACK/ложная тревога/заметка; state bounded. OpenAPI/TS/docs/ADR-034 и upgrade guide обновлены.

### Проверено

| Проверка | Результат |
|---|---|
| make check | ruff/format/mypy strict, ESLint/Prettier/vue-tsc, **163 Python unit + 97 Vitest**, production build |
| PostgreSQL/Valkey integration | **23 passed**: прежние API + duplicate UUID, DB failure/Pending reclaim, poison/dead letter, pub/sub без записи, keyset/audit/soft delete, потерянный ACK после commit, competing operators |
| Живой отказ PostgreSQL | SSE тревога получена при остановленной БД, PATCH → 409, pending/backlog=1; после возврата записан тот же UUID, backlog=0 |
| Живой отказ Valkey 21 с | worker readiness=503, камеры сохранили run IDs; 3 события из окна сбоя доставлены и записаны после восстановления, backlog=0 |
| Реальный YOLO/ByteTrack + 2 mock | Тестовый MP4 из статичного bus.jpg: 4 сохранённых входа с реальными track IDs; отдельная telemetry persons=4/in-zone=4; это не CCTV quality benchmark |
| Chromium | ACK/FP сохраняют audit и заметку, статусный фильтр; отдельные telemetry/preview sockets, 390px без overflow, light/dark screenshots, pageerror=0. Image viewer недоступен: визуальную оценку PNG через него не заявляем |
| Миграции/контракт/Git | upgrade с пустой БД и upgrade M6; downgrade/upgrade на тестовой БД, alembic check без diff, lock/OpenAPI совпали; full .git/fsck/ZIP проверяются при передаче |

Shutdown: финальный worker с открытым WS — **0.62 с**, API с открытым SSE — **3.22 с**; runtime/heartbeat удалены, Stream=0. API ограничивает graceful drain long-lived SSE тремя секундами. Production audit: **0 vulnerabilities**; dev-audit не повторялся.

Доказательства и воспроизводимые QA-скрипты — [docs/qa/m7/README.md](docs/qa/m7/README.md).

### Ограничения

RAM-outbox теряется при аварии worker во время отказа Redis. AOF everysec оставляет окно потери при аварии Redis/хоста. Stream не обрезается до записи — контролировать backlog/диск, noeviction/AOF/backup. SSE не replay: REST восстанавливает историю, а не пропущенные toast. UI live буфер 200/недавний dedupe 2000, полная история через пагинацию. Worker не ходит в PostgreSQL.

Снимки/event detail с изображением — M8. CSV, дополнительные type/severity/period фильтры, линии/loitering, сохранённые track sessions/analytics/retention и авторизация не добавлены. Windows, Docker/CI, GPU, реальные RTSP и движущееся CCTV не проверялись; Node в sandbox 24.14.1 ниже engine — использовать поддерживаемую версию. Все прежние ограничения ниже сохраняются, если здесь не уточнено иначе.

## Milestone 6 — результат предыдущей сессии

### Проверка предыдущего этапа

Восстановлен оригинальный архив и Git commit M5 `8e0e842` (Kostya). До изменений M6 повторён полный make check: **122 Python / 64 frontend**, linters/typecheck/build зелёные. В заключительном M6 integration-прогоне также прошли все прежние 11 проверок. M5 не переписан и не переименован задним числом.

### Сделано

* Сохраняемый `zones` CRUD (camera-scoped, 404/422, 16 зон под блокировкой родителя), миграция c631d038af01; простой polygon 3..64 уникальных вершин 0..1, без пересечений/самокасаний/наложений; граница внутри.
* Per-run SceneRegistry/ZoneEngine в одиночном inference executor после ByteTrack. Нижний anchor, OUTSIDE/ENTERING/INSIDE/EXITING, dwell/grace по source timestamps, LOST замораживает время. Cooldown по Clock на camera/run/track/type, одно событие за визит. Изменённая геометрия сбрасывает только свою зону; loop/reconnect/epoch/size и lifecycle очищают scene.
* Immutable типизированный DomainEvent PERSON_ENTERED_DANGER_ZONE (UUID, camera/run/track/zone, severity, UTC/source time, mean confidence × stability, metadata). Событие в DetectionResult и структурированном логе только актуального run. **Надёжная доставка и запись в БД ещё не реализованы: это M7.**
* Hot CameraSpec с zones/effective config без смены run/ID. Nullable camera overrides dwell/grace/cooldown + API defaults; EVENT_MIN_TRACK_HITS и SEVERITY_ZONE_ENTER worker settings. Параметры добавлены в .env.example и compose.
* UI-редактор первой зоны по ADR-009: рисование на видео/SVG, keyboard coords, undo/clear/cancel, enable, save, delete с подтверждением; черновик не перезаписывает другие зоны и не меняет ID при обновлении query. Учёт letterbox и source coordinates; atomic preview zones/IN_DANGER_ZONE, красная рамка и счётчик в зоне, LOST не рисуется.
* Seed добавляет пример зоны каждой seed-камере без зон; повторный запуск не дублирует и не затирает существующие зоны. События seed не имитирует. Документация/ADR-033/OpenAPI/TS-типы обновлены.

### Проверено

| Проверка | Результат |
|---|---|
| make check | Все linters/format/typecheck/build прошли, **151 Python unit + 82 Vitest**, mypy strict 132 файла |
| pytest -m integration | **15 passed** на настоящих PostgreSQL/Valkey |
| Миграции / schema / lock / контракт | Upgrade с пустой БД; downgrade+upgrade на тестовой; alembic check без diff; uv lock --check; повторный OpenAPI совпал |
| Живой YOLO + ByteTrack + 2 mock + WS | 4 входа на реальном статичном тестовом видео; горячая геометрия/disable/re-enable сохраняют run/IDs и меняют состояние |
| Chromium | Редактор пишет правильные normalized coords, padding игнорируется, cancel не меняет БД, красные боксы/track IDs, 390px light/dark без overflow/pageerror |
| Shutdown | Открытый WS закрыт, runtime/heartbeat Redis удалены за **0.82 с** |
| npm audit --omit=dev | **0 уязвимостей** production |

Логи и скриншоты: [docs/qa/m6/README.md](docs/qa/m6/README.md). Image viewer недоступен: визуальная оценка PNG не заявляется; UI проверен через DOM, координаты, canvas и API. Windows, Docker/CI, GPU/CUDA, реальная RTSP-камера, качество на движущемся CCTV и нагрузка 4/8 камер не проверены. Node в песочнице 24.14.1 ниже заявленного engine — использовать поддерживаемую версию. Старые ограничения ниже остаются актуальными, если здесь не уточнено иначе.

### Следующий шаг — M7

Redis pub/sub + Stream, ingest/идемпотентное сохранение событий в PostgreSQL, SSE, отдельная WS-телеметрия и frontend live update. Сейчас event log не заменяет доставку: события теряются при аварии, история/ACK/false positive не доступны. Snapshot — M8, линии/loitering — позже. Не объявлять M7 реализованным из-за работающего preview WS.

## Milestone 5 — предыдущая сессия

Работа продолжена из последнего пользовательского `Ai-Detector.zip`, HEAD `8a7a28c`. Учтены Windows-настройки PostgreSQL: host `127.0.0.1:15432`, внутри Docker по-прежнему `postgres:5432`. Исходное ТЗ снова предоставлено пользователем и сохранено в [docs/spec/AI_DETECTOR_v2_MASTER_PROMPT.md](docs/spec/AI_DETECTOR_v2_MASTER_PROMPT.md). Новые коммиты оформляются от имени **Kostya** с существующей в репозитории Git-идентичностью.

### Сделано

* Типизированный immutable `PersonTrack`, `PersonState` NORMAL/LOST, center и anchor, UTC/source timestamps, возраст, hits и последовательные пропуски.
* `PersonTracker`, adapter к готовому ByteTrack (`trackers 2.6.1`, `supervision 0.31.1`), реестр на `(camera_id, run_id)` в одиночном inference executor. Библиотечные объекты не выходят в домен или preview. Собственного association/Kalman, re-ID, лиц, объектов и pose нет.
* Update на каждом обработанном кадре, включая `[]`. При пропуске — LOST; при возврате до истечения — тот же ID. Удаление строго на 25-м последовательном пропуске (настраивается), без воскрешения просроченного tracklet. Ошибка inference не подменяется пустой детекцией; ошибка tracker изолирована по камере с логом и сбросом повреждённой сцены.
* При loop/reconnect/разрешении сцена сбрасывается, публичные ID внутри run не переиспользуются. `source_epoch` переживает вытеснение первого кадра после разрыва из latest-frame буфера. Stop/delete/ERROR/restart/shutdown очищают tracker registry, даже без новых кадров; история старых ID не накапливается.
* Worker settings: `PERSON_TRACK_MAX_AGE=25`, `TRACK_MATCH_IOU=0.5`, `TRACK_ACTIVATION_CONFIDENCE=0.25`. IoU проверен как настоящий порог перекрытия, без confidence fusion. Камерные FPS/confidence по-прежнему применяются горячо без смены run/ID.
* Preview v1 дополнен tracks из того же кадра; frontend проверяет поля и уникальность ID. Подпись `Человек #ID` только у подтверждённой детекции; LOST bbox не рисуется и не добавляется в счётчик людей. Старые пакеты без tracks также принимаются. REST/OpenAPI и схема БД не менялись.
* `.gitattributes` закрепляет LF для исходников, чтобы Windows checkout не ломал Prettier. Обновлены README, behavior, architecture, data-flow, API/development docs, индекс ADR. [ADR-032](docs/decisions/ADR-032-bytetrack-runtime.md) уточняет устаревший библиотечный путь из ADR-003: ByteTrack перенесён upstream в пакет trackers.

### Проверено сейчас

Linux x86_64, Python 3.12.15, Node 24.14.1 (ниже заявленного engine; использовать поддерживаемый Node), PostgreSQL 17.10, Valkey 9.0.5, CPU. Lock модели/torch сохранён; добавлены trackers 2.6.1 и supervision 0.31.1, версии проверены по PyPI и установленному коду.

| Проверка | Результат |
|---|---|
| `make check` | Все проверки прошли: ruff check/format, mypy strict (120 source files), ESLint, Prettier, vue-tsc, тесты и production build |
| `uv run pytest` | **122 passed**, 11 integration deselected. В том числе стабильность/перестановка ID, пустые кадры, восстановление, ровно 25 пропусков, N=1, confidence 0.25, настоящий IoU, независимость камер/run, loop/reconnect/разрешение, очистка памяти, изоляция ошибок |
| `uv run pytest -m integration` | **11 passed** на настоящих PostgreSQL/Valkey, миграции применены с пустой БД |
| `npm --prefix frontend test` | **64 passed** в 9 файлах, включая контракт tracks и overlay без LOST/выдуманных ID |
| `uv lock --check`, `alembic check`, экспорт OpenAPI | Lock согласован, новых миграционных операций нет; экспорт JSON совпадает с frontend/openapi.json |
| YOLO + ByteTrack + 2 mock через Vite WebSocket | Реальная модель на 12-секундном MP4 из статичного официального bus.jpg: 51 согласованный JPEG/metadata пакет за ~15 с; стабильные ID на соседних кадрах, после цикла новые возрастающие ID при том же run. Оба mock обрабатываются параллельно |
| Горячие настройки / restart | Смена FPS/confidence сохраняет run и ID; restart создаёт другой run с собственной нумерацией от 1 |
| Chromium/Playwright | 3 непустых canvas; перехвачены реальные fillText `Человек #ID`; monitoring/focus, 390px, светлая/тёмная темы; pageerror нет, горизонтального overflow нет. Скриншоты в docs/qa/m5; image-viewer песочницы не смог их открыть, визуальная оценка через него не заявляется |
| SIGTERM при открытом WS | Соединение закрыто, runtime-ключи Redis удалены за ~1.11 с; процессы приложения завершились |
| `npm audit --omit=dev` | Production: **0 уязвимостей**. Полный dev-audit на этом этапе не повторялся; прежний риск указан ниже |

Логи проверок и описание QA — [docs/qa/m5/README.md](docs/qa/m5/README.md).

### Ограничения и следующий шаг

* Windows, Docker compose/CI, CUDA/GPU и реальная RTSP/IP-камера **не проверялись** в этой сессии. Сервисы запущены нативно на Linux, не в Docker. Проверка reconnect — детерминированным источником, не реальным сетевым обрывом.
* Реальная модель проверена на статичном тестовом ролике, а движение/пропуски/IoU — синтетическими детекциями готового ByteTrack. Это не оценка IDF1/качества на настоящем движущемся CCTV и не benchmark 4/8 камер. Наблюдавшаяся скорость preview не является обещанием целевого FPS.
* Новый кандидат подтверждается следующим совпадением; first_seen/age/hits начинаются с подтверждения. При низком FPS/резких движениях/долгой окклюзии ID может измениться: биометрической идентификации нет.
* Треки пока только runtime: PostgreSQL/track sessions/аналитика/уникальные посетители не добавлены. Состояние теряется при аварии worker'а (ADR-019).
* Следующий этап — **Milestone 6: danger zone**, нормализованный polygon, anchor point-in-polygon, dwell и событие по плану ТЗ. Зоны/линии/события раньше своих этапов не имитируются.

## Сделано ранее

### Milestone 4 — детекция людей и визуализация
* `PersonDetector`/`PersonDetection`, Ultralytics adapter: YOLO26 nano, только COCO person, боксы в пикселях исходного изображения. Manifest (backend, веса, SHA-256, вход 640, класс, лицензия), явная атомарная загрузка `uv run ai-detector-model` / `make model`, проверка целостности и warmup до HTTP. При ошибке модели/устройства — CRITICAL и exit 1; скачивания и тихого scripted fallback на старте нет.
* Scripted adapter выбирается по `mock://` и использует тот же сценарий и source timestamp, что и renderer. Реальные и mock-камеры работают одновременно; mock явно помечен «ДЕМО».
* `InferenceScheduler`: отдельный одиночный executor, справедливая round-robin очередь, индивидуальный target_fps, батч до 4 с ожиданием до 20 мс, только последний кадр камеры. Индивидуальные confidence сохраняются при батчинге. Результаты остановленного run_id отбрасываются.
* Runtime: processed_fps, inference_ms, detections_count, dropped_frames, отдельная inference_error; DEGRADED при низком FPS более 5 с/ошибке inference, автоматическое восстановление. После 3 ошибочных реальных батчей readiness 503; успешные mock-камеры не скрывают отказ модели.
* `camera_configs`, миграция `b452b4c88e6b`, GET/PUT `/cameras/{id}/config`: только nullable переопределения FPS/порога, ответы overrides/defaults/effective, в worker-spec — effective. Горячее применение без переподключения; периодическая сверка каждые 30 с исправляет потерянные уведомления.
* `PreviewHub`: JPEG только для зрителей, пул из двух потоков, не более одного encode на камеру и одного ожидающего сообщения на зрителя. Binary WebSocket-пакет содержит JSON и JPEG одного frame_id/run_id; нет несогласованных рамок. Проверка Origin, таймаут медленного зрителя, очистка даже при отключении во время отсутствия кадров.
* Frontend: `CameraImageSource`/`WsPreviewSource`, bounded latest-only decode, backoff; отдельное shallow-состояние на камеру, явное освобождение bitmap. Canvas кадров и нормализованных боксов, подписка только для видимой работающей камеры, устаревший кадр помечается. Плитка открывает крупный просмотр `/monitoring/:cameraId`, редактор FPS/порога с наследованием, валидацией, сбросом и сохранением. Трекинг и уникальные посетители не имитируются.
* Обновлены OpenAPI/TS-типы, README, `.env.example`, Makefile, Docker mount моделей и `.dockerignore` (без host node_modules/venv в контексте), docs и ADR-029…031; ADR-016/028 уточнены. CPU PyTorch и единственная headless-сборка OpenCV; веса и лицензионные сведения включены в передаваемый архив.

## Проверено на этапе Milestone 4 (история)

Окружение: Linux x86_64, Python 3.12.15 (uv), Node 24.14.1, PostgreSQL 17.10, Valkey 9.0.5, CPU. Node в песочнице ниже заявленного в package.json engine >=24.15.0; для своего запуска используйте поддерживаемую версию Node. Реальная модель: Ultralytics 8.4.177, torch 2.14.1+cpu, torchvision 0.29.1+cpu, numpy 2.5.3, OpenCV headless 5.0.0.93.

| Проверка | Результат |
|---|---|
| `uv run pytest` | 98 passed, интеграционные исключены; протокол/боксы, fairness, FPS, scripted, целостность модели, горячая конфигурация, деградация/восстановление, отбрасывание результатов старого run_id, готовность при отказе модели, периодическая сверка, WebSocket/очистка без кадров |
| `uv run pytest -m integration` | 11 passed на настоящих PostgreSQL + Valkey; прежние CRUD/uploads/internal/health и новая конфигурация: defaults, PUT/сброс, валидация, effective в worker-spec, 404 после удаления |
| `ruff check`, `ruff format --check`, `mypy --strict` | Без ошибок |
| Frontend lint / format:check / typecheck / test / build | Без ошибок; 46 Vitest-тестов, включая числовую форму, protocol, reconnect и освобождение bitmap |
| Миграции и `alembic check` | Обе миграции применены с пустой БД; расхождений моделей со схемой нет |
| `uv lock --check` | Lock согласован; CPU-источники зависимостей разрешаются |
| Настоящая модель | Warmup и батч 4 на официальном тестовом bus.jpg; person-боксы найдены на каждом кадре |
| Настоящий видеофайл | MP4 из тестового изображения загружен через API; real inference, JPEG/боксы через Vite WebSocket, 8 последовательных frame_id без дублей; при target_fps=3 наблюдалось около 3 FPS |
| Горячая конфигурация | Смена FPS/порога не меняет run_id; наследование и сброс проверены через API и UI |
| Нагрузка 8 камер | 6 file + 2 mock, CPU: все получают обработку (~1.56–1.57 FPS на этой машине), все корректно DEGRADED, readiness остаётся ready. Это smoke-проверка fairness, не обещание производительности |
| SIGTERM с открытым WebSocket | Обновлённый worker завершился примерно за 0.4 с, статусы и heartbeat `ad:*` удалены |
| Fail-fast | Несуществующий манифест → exit 1 до открытия HTTP; неправильный SHA-256 и отсутствующие веса дополнительно проверены unit-тестами |
| UI, локальный Chromium/Playwright | Реальные и mock-кадры с рамками; focus, числовая валидация, сохранение и сброс, stop/start, светлая/тёмная темы, 390px без горизонтального overflow, pageerror отсутствуют |
| `npm audit` | Production: 0 уязвимостей; полный audit: прежние 4 high в dev-цепочке eslint-config → fast-glob → micromatch → braces |

Скриншоты проверенного UI — `docs/qa/`. Видео для smoke-теста создано из статичного тестового изображения: это не проверка качества на реальном движущемся CCTV-потоке.

## История предыдущих этапов (из исходного архива)

### Milestone 1 — архитектура (подтверждено человеком)
* Документы `docs/architecture.md`, `data-flow.md`, `database.md`, `behavior.md`, ADR-001…021.

### Milestone 3 — камеры
* `shared`: типы источников и их проверка (`rtsp`, `upload://`, `mock://`), маскировка учётных данных, `CameraSpec`, `CameraStatus`/`CameraRuntimeStatus`, команды worker'у.
* API: таблица `cameras` (миграция, частичный уникальный индекс по имени, мягкое удаление), CRUD + `start`/`stop`/`restart`, загрузка видео `POST /uploads` (потоковая запись, лимиты, сгенерированные имена), внутренний API worker'а с токеном, объединение с runtime-статусом из Redis, коды ошибок домена, `ai-detector-seed` (2 демо-камеры).
* Worker: `FrameSource` (файл в реальном темпе по кругу, RTSP через OpenCV/FFmpeg, mock по сценарию), `CameraSession` (поток захвата на камеру, буфер последнего кадра, жизненный цикл по таблице переходов, reconnect с backoff, `ERROR` для неустранимых ошибок), `CameraManager` (сверка с желаемым состоянием), подписка на команды с полной сверкой после переподключения, публикация статусов в Redis раз в 1 с, `GET /status`.
* Frontend: «Мониторинг» — плитки камер со статусом, FPS захвата, разрешением, возрастом последнего кадра и сообщениями §120; «Камеры» — список, добавление (файл с загрузкой / RTSP / демо-сцена, «запустить сразу»), изменение, запуск/остановка/перезапуск, удаление с подтверждением; пустые состояния §122; уведомления (vue-sonner); опрос `GET /cameras` раз в 2 с до SSE.
* `.env.example`, compose (общий том `uploads`, токен, `API_BASE_URL`), CI (миграция перед интеграционными тестами), `make seed`.
* Документация: `docs/api.md` (камеры, загрузки, внутренний API, коды ошибок), правки `data-flow.md`, `architecture.md`, `behavior.md`, `database.md`, `development.md` (seed, пример видео §108, RTSP без камеры), ADR-024…028.

### Milestone 2 — инфраструктура
* uv workspace: `shared` (`ai_detector_core`), `backend` (`app`), `vision-worker` (`vision_worker`); `uv.lock`.
* `shared`: `Clock`, `WorkerHeartbeat`, имена Redis-ключей, JSON-логирование (stdlib).
* API: настройки (pydantic-settings, CORS без `*`, только `postgresql+asyncpg`), JSON-логи, lifespan с engine/Redis, `/health/live`, `/health/ready` (БД + Redis, 503 при отказе), `GET /api/v1/system/status` (зависимости + живые worker'ы), единый формат ошибок, Alembic (async, без миграций — таблицы с Milestone 3), экспорт OpenAPI.
* Worker: `Supervisor`, heartbeat в Redis раз в 1 с с TTL 5 с, HTTP `/health/live`, `/health/ready`, штатная остановка удаляет heartbeat.
* Frontend: Vite + Vue 3 + TS, Pinia, Vue Query, vue-i18n (ru), Tailwind 4, shadcn-vue (Button), Lucide; маршруты `/monitoring`, `/events`, `/analytics`, `/cameras`, `/settings`; светлая/тёмная (графит) темы; индикатор состояния системы и панель на «Настройках»; типы API из OpenAPI.
* Docker: Dockerfile api/worker/frontend, nginx (same-origin `/api`, `/health`, `/live`), `docker-compose.yml` (mediamtx — profile `media`).
* `Makefile` + эквиваленты PowerShell (`docs/development.md`), `.env.example`, CI (`.github/workflows/ci.yml`), `docs/api.md`.
* ADR-022 (TypeScript 5.9), ADR-023 (HTTP worker'а на FastAPI).

## Проверено ранее по полученному архиву (Milestone 3; песочница агента: Linux x86_64, Python 3.12.15, Node 24.14.1, CPU, без Docker)

| Проверка | Результат |
|---|---|
| `uv run pytest` | 72 passed (источники, backoff, буфер, жизненный цикл, сессия с fake-источником: reconnect/ERROR/stop, файл на сгенерированном видео: цикл, монотонное время, discontinuity, mock и сценарии, CameraManager, обработка команд, публикация статусов, схемы) |
| `uv run pytest -m integration` (PostgreSQL 17 + Valkey 9) | 10 passed: CRUD, 409, мягкое удаление и повторное имя, маскировка, лимит камер, публикация команд в Redis, загрузка (413/422, без остатков), токен внутреннего API |
| Тесты сессии 15 прогонов подряд | стабильны |
| `ruff check`, `ruff format --check`, `mypy --strict` | без ошибок |
| `npm run lint` / `format:check` / `typecheck` / `test` / `build` | без ошибок, 18 тестов Vitest |
| Живой запуск API + worker, `ai-detector-seed` (дважды) | 2 mock-камеры → RUNNING, 15 к/с, 1280×720; повторный seed ничего не дублирует |
| stop / start / restart / delete через API | статус пропадает при остановке, restart меняет `run_id`, удалённая камера уходит из worker'а |
| Файл-камера: загрузка mp4 (ffmpeg testsrc2) | RUNNING 25 к/с, 16 с работы при длине ролика 6 с (цикл) |
| Файл удалён с диска | камера `ERROR` «video file not found» без повторов |
| RTSP через MediaMTX 1.21.1 + ffmpeg | RUNNING 25 к/с; MediaMTX остановлен → RECONNECTING с растущим числом попыток; после возврата потока — RUNNING через ~10 с без перезапуска |
| SIGTERM worker'у с 5 камерами | остановка ~1 с, все сессии закрыты, ключи статуса и heartbeat удалены |
| UI в Chromium (Playwright) | добавление файл-камеры через диалог с загрузкой → «В работе» → остановка → запуск → переименование → удаление; ошибка 409 показана в форме по-русски; скриншоты светлой/тёмной темы и пустого состояния |

Milestone 2 проверки (health, отключение Redis, шаги Dockerfile) не повторялись целиком; health-тесты входят в `pytest`.

## Ограничения и что не проверено сейчас

* `docker compose build/up` и CI на GitHub — в песочнице нет Docker и GitHub Actions; YAML только распарсен. Общий том `uploads` и `API_BASE_URL=http://api:8000` в compose не проверены в контейнерах.
* В восстановленной сессии реальная IP-камера/RTSP не подключались. Ранее в Milestone 3 по архиву RTSP проверялся через MediaMTX; это не повторная проверка текущей версии.
* RTSP с потерями пакетов/высокой задержкой и камеры с H.265 не проверялись.
* Интеграционные тесты шли на PostgreSQL 17 и Valkey 9, а в compose/CI — `postgres:18-alpine` и `redis:8.8-alpine`.
* Windows, CUDA/GPU, ONNX и WebRTC не проверялись/не реализованы на этом этапе.
* Качество детекции на пользовательских CCTV-данных не оценивалось. Восемь камер на CPU не достигают целевых 10 FPS — нужна настройка FPS/железа; GPU-оптимизация — позднее.
* Авторизации оператора нет: нельзя открывать API/worker в публичный Интернет. AGPL-3.0 модели/Ultralytics нужно учитывать перед внедрением.

## Версии

Базовые зависимости были зафиксированы в исходном архиве на 2026-10-08. Восстановление Milestone 4 обновило `uv.lock` для inference; фактически проверенные версии перечислены выше. Frontend lock сохранён из исходного архива. Исключение — TypeScript 5.9 вместо 7.0 ([ADR-022](docs/decisions/ADR-022-typescript-version.md)).

## Ключевые решения

* Worker не ходит в PostgreSQL ([ADR-002](docs/decisions/ADR-002-vision-worker-separation.md), [ADR-004](docs/decisions/ADR-004-event-bus.md)); превью — из worker'а ([ADR-005](docs/decisions/ADR-005-video-streaming.md)); событие — в pub/sub и Stream одновременно ([ADR-017](docs/decisions/ADR-017-event-persistence.md)).
* Milestone 3: сценарии mock — в пакете worker'а ([ADR-024](docs/decisions/ADR-024-mock-scenarios-location.md)); временные и неустранимые ошибки источника ([ADR-025](docs/decisions/ADR-025-frame-source-contract.md)); `camera_configs` — с Milestone 4 ([ADR-026](docs/decisions/ADR-026-camera-configs-deferred.md)); RTSP проверяется при запуске, без кнопки «Проверить» ([ADR-027](docs/decisions/ADR-027-source-validation.md)); команды worker'у — уведомление + полная сверка ([ADR-028](docs/decisions/ADR-028-worker-commands-best-effort.md)).
* Интеграционные тесты исключены из обычного `pytest` и при недоступном сервисе падают, а не пропускаются.

## Известные проблемы / риски

* Лимит `MAX_CAMERAS` проверяется без блокировки: два одновременных запроса могут создать камеру сверх лимита. Для 1–8 камер и одного оператора допустимо.
* `npm audit`: 4 high в dev-зависимостях (`braces` через eslint-config → fast-glob → micromatch); в production-сборку не попадают. Исправить обновлением, когда выйдет совместимая версия.
* Публикация файла в RTSP через `ffmpeg -re -stream_loop -1` после первого круга идёт быстрее реального времени — это особенность ffmpeg, не worker'а (см. `docs/development.md`).
* Сообщение `last_error` от worker'а — английский технический текст; UI показывает его мелко под русским описанием.
* Seed (§109) создаёт камеры и пример зоны (M6). События/история — с этапа M7.
* `StarletteDeprecationWarning` для TestClient (httpx → httpx2) — на работу не влияет.
* Риски из Milestone 1 актуальны: cooldown без zone_id ([ADR-008](docs/decisions/ADR-008-cooldown.md)), потеря активных треков при аварии worker'а ([ADR-019](docs/decisions/ADR-019-track-persistence.md)).

## Следующий шаг после Milestone 4 (история, выполнено выше)

Milestone 5 — person tracking: интерфейс `PersonTracker`, ByteTrack adapter, registry и track_id в пределах камеры/run_id, update на каждом обработанном кадре (включая пустые детекции), сброс при discontinuity, отрисовка track ID. Зоны/линии/события пока не добавлять раньше своих этапов.
