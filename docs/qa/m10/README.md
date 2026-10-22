# QA — Milestone 10

Linux x86_64, Python3.12.15, **Node24.15.0**, PostgreSQL17.10 UTF8, Valkey9.0.5; CPU YOLO26n/ByteTrack и2mock. База — настоящий полный Git M9 c30a4d8 (Kostya). Фактически проверенный Node удовлетворяет package engines; прежние M9 логи Node24.14.1 исторические.

## Автоматические проверки

* make-check.log: **213 Python unit +123 Vitest**, strict mypy168 файлов, ruff/format, ESLint/Prettier/vue-tsc, production build. Новые14 Python cases:1Hz latest/partial flush, short-gap duration и fractional cross-second>2с без clipping, final-track once/identity/run isolation, out-of-order ignore, state transitions и gap LOST,2048 segment cap/truncated, payload validation, bounded queue/no alarm channel. Новые8 frontend: window params/null-gap/count axes, timeline/details/truncation и dashboard/error/filter flows.
* integration.log: **37 passed** на реальных PostgreSQL/Valkey (предыдущие33+4). KPI cross-foot, [start,end) и equivalent timezone offsets, selected camera/archived/zero-vs-null, completed overlap/keyset ties, independent ingest duplicate/poison/rollback/recovery, invalid/empty windows/cursor. Использованы отдельная test DB и Redis13.
* upgrade-m9-m10.log: live M9→M10. empty-db-migration.log: весь путь с пустой UTF8 DB. migration-roundtrip.log: test-only downgrade M10→M9→M10. alembic-check.log: нет schema diff. lock-check.log: frozen lock согласован. OpenAPI повторно сгенерирован и byte-for-byte cmp совпал. npm-audit-production.json:0 vulnerabilities; dev4high прежнего transitive дерева не исправлялись force-update.
* Сборка успешна, но lazy AnalyticsView/ECharts chunk556.83kB minified/189.06kB gzip даёт Vite warning>500kB. Предупреждение не скрыто.

## Живой стенд

* live.log + live-dashboard.json: 2mock и CPU YOLO на MP4 из статичного bus.jpg, не moving-CCTV benchmark. После stop/drain fixed-window SQL count47 = total_events = sums(events_over_time/by_type/by_camera). На этой точке862 camera observations,100 completed tracks; active0, analytics backlog0. Реальный file camera: sampled mean4/max4, observed75.065218с,52 finalized tracks; зона не задана, отсутствие событий не ошибка. Значения относятся только к этому фиксированному окну, не всем последующим запускам.
* outages.log: QA PostgreSQL реально остановлена на5с. Inference продолжает, dashboard503,22 pending analytics UUID после восстановления найдены в БД, backlog0. Valkey остановлен8с и перезапущен с AOF:24 observations периода восстановлены из работающего bounded worker RAM outbox, backlog0. Это не тест host/process crash и не zero-loss гарантия. До финального restart эти проверки выполнялись на той же M10 реализации транспорта, до небольшого уточнения UTC/gap UI.
* browser.log: после restart актуального backend/worker; real Vite/API и local Chromium/Playwright.3 ECharts SVG с ненулевыми path/размером, period/camera filters, selected-camera people chart, track details.390px без horizontal overflow, light/dark PNG; forced503 не показывает правдоподобные нули, retry восстанавливает данные, pageerror0. Это DOM/layout/API проверки. Скриншоты сохранены, image viewer недоступен — экспертная визуальная проверка не заявляется.
* shutdown.log: актуальный код, worker **0.82с**, API с открытым SSE **3.22с**. WS закрылся, runtime/heartbeat keys удалены, оба Streams0. При stop появилось **7 новых финальных sessions** (всего171 сохранённая session от текущих3runs);5 JPEG читаются после остановки worker. Active cameras0. Треки ID не уникальные физические люди.
* api-ready.json/worker-ready.json: после restart — ready, analytics_ingest probe/analytics_ok=true, dropped0 на точке проверки. Это не обещание future no-loss.

Скрипты scripts/ специфичны sandbox: .py.txt копировать в .py, адаптировать пути/порты. Они останавливают сервисы; **не запускать на production**. Нет новых пользовательских данных/снимков в архиве, только QA screenshots/обезличенная telemetry.

## Границы результата

M10 содержит sampled1Hz observations и completed-only timeline, не frame-weighted aggregates и не physical unique visitors. Cap4096tracks/2048segments/1000outbox, truncated/drop diagnostic. No-sample неизвестно, не0; max sampled, gap>2с не uptime; no multicamera asynchronous occupancy sum. Manual refresh, UTC≤31д/120buckets, full overlapping sessions. Отдельный live-camera count не часть MVCC snapshot. Новые таблицы без automatic retention/rollup: мониторить growth/backup/disk/Stream. RAM/AOF и незавершённые tracks при crash имеют окна потери. Снимки/диск имеют прежние ограничения.

Windows, Docker/CI, GPU, RTSP, moving-CCTV accuracy и4/8-camera throughput не проверены. No auth/CSV/loitering; trusted network only. Следующий M11: loitering и CSV. Семантика — ADR-037, обновление — UPDATE_MILESTONE_10.md.
