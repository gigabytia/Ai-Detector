# QA Milestone 11

## Автоматические проверки

- `check-final.log`: 241 Python unit, 129 frontend (23 файла), strict mypy 170 файлов; Ruff/format, ESLint/Prettier, vue-tsc, production build. Python 3.12.15 / Node 24.15.0.
- `integration-final.log`: 41 passed на PostgreSQL17.10/Valkey9.0.5, отдельные test DB и Redis13. Тесты очищают свои данные, не запускать на production.
- Пустая UTF8 БД → head b6b7cfcd87c5; test-only M10 downgrade/upgrade; Alembic no diff, uv lock check, OpenAPI regeneration совпала с committed контрактом. Migration CHECK 0..3600 добавлен явно. В первоначальных локальных draft DB ограничение отсутствовало (они были upgraded до добавления CHECK в ещё не выпущенную миграцию); это выявлено финальной проверкой. Draft DB исправлены, затем downgrade/upgrade и41 integration повторены успешно; новая пустая БД создаёт CHECK штатно.
- Production npm audit: 0. Предупреждение lazy ECharts chunk ~557kB/~189kB gzip сохраняется; build успешен. Compose YAML/env mappings проверены статически, контейнеры не запускались.

## Живой прогон

`live1.log` / `live-proof.json`: mock default10s → alarm при10.0666666667s, один на visit, entry/loiter identity совпала. JPEG1280×720; FP/note и CSV UUID совпали. CPU YOLO на статичном bus MP4 дал8 loitering events; hot threshold не сменил run. Это проверка интеграции, не точности moving CCTV.

`browser-final.log`, пять PNG: реальные Vite/API, camera/status/type/24h, download, принудительный503 → сообщение без файла → retry, details duration/threshold, hot override2s через UI. Chromium390px light/dark: overflow0, pageerror0. Проверены DOM/layout и сняты скриншоты; экспертная визуальная оценка изображений не выполнялась.

`browser-export.csv` / `csv-check.json`: UTF8 BOM, comma, CRLF,19 колонок,1 строка; csv.reader и pandas совпали. Проверены Unicode, quotes/multiline, UTC, ID и защитный апостроф. Native Excel/LibreOffice import не проверялся; CSV не сохраняет стили/формулы. Апостроф — mitigation, не универсальная гарантия безопасности всех spreadsheet consumers.

`outage-final.log` / `outage-proof.json`: PostgreSQL остановлен, loitering приходит SSE; export503 JSON без attachment. После восстановления тот же event/snapshot UUID и SHA-256 JPEG, CSV содержит событие; оба backlog0. Redis outage повторно в M11 не запускался (только прошлое покрытие M10).

`shutdown-final.log`: worker0.54s, API с открытым SSE3.22s, runtime keys удалены, оба backlog0;7 новых completed sessions при остановке,13 сохранённых current-run sessions;5 JPEG читаются после worker stop. Затем API/worker остановлены.

## Границы

Gap>2s/LOST/outside сбрасывают continuous timer; fired marker живёт до confirmed exit, cooldown может подавить другую зону. CSV до50000 строк/20MiB, один bounded buffered SELECT+off-loop codec; лимиты проверены уменьшенными тестовыми caps, не нагрузкой50000 строк/параллельными exports. Новые config/event требуют согласованного обновления API/worker/UI.

Auth нет; только доверенная сеть. RAM-outbox/AOF/crash/retention ограничения прежние. Windows, Docker/CI, GPU, реальная RTSP, moving-CCTV accuracy и нагрузка4/8 камер не проверены. Скрипты `.txt` содержат sandbox paths/ports и изменяют QA камеры/останавливают сервисы — сначала адаптировать, никогда не production. Runtime DB, credentials .env и snapshots не входят в архив. Следующий M12: измерения производительности до оптимизаций.
