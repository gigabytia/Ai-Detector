# QA — Milestone 8

Linux x86_64; Python3.12.15, PostgreSQL17.10, Valkey9.0.5, CPU. Node24.14.1 ниже package engine: использовать поддерживаемую версию. База — M7 full Git 2d6aca3.

## Автоматические

* make-check.log: linters/format, strict mypy150 файлов, **177 Python unit / 103 Vitest**, production build. Storage atomic replace/failure/traversal/symlink/age/UTC; full-resolution untouched pixels, disabled/busy/disk/codec fallback; shutdown ordering. Vue overlay coordinates/toggle, no-image/error/retry, camera three-state override.
* integration.log: **29 passed** на реальных PostgreSQL/Valkey: прежние23 + snapshot REST/replay/soft-delete/missing, bad optional attachment, retention/failed delete/orphans, transaction rollback before ACK, expired replay + private pubsub payload, lock renewal/release ownership.
* migration-roundtrip.log / alembic-check.log: M7→M8 и downgrade/upgrade только на тестовой БД, no schema diff. lock-check.log, повторный OpenAPI совпал. npm-audit-production.json — 0 production vulnerabilities; dev-audit не повторялся.

## Живые

* live.log: YOLO/ByteTrack на MP4 из статичного bus.jpg (не quality benchmark) даёт JPEG810×1080 против preview640×853; mock JPEG1280×720 против640×360. Полный JPEG доступен по UUID. Off/on camera config сохраняет run, новые events без/со снимком.
* postgres-outage.log: PostgreSQL остановлена целиком; live event уже доставлен, файл записан; operator PATCH409. После возврата тот же event/snapshot UUID и JPEG SHA-256, stream0. Live JSON не содержит storage_key.
* redis-outage.log: Valkey/AOF остановлен на21с. Worker readiness503, run IDs не меняются; после восстановления13 events и13 snapshots доступны, backlog0. RAM/Redis host crash не моделировался, zero-loss не заявляется.
* browser.log: локальный Chromium/Playwright + реальные API/Vite. Exact DOM image/SVG alignment и bbox coordinate, original dimensions, toggle, note persisted, no-image, forced404+retry, event404, journal→detail. 390px без horizontal overflow, pageerror0. Light/dark/desktop/mobile PNG рядом. Проверены DOM/layout/API; visual image viewer не использован и визуальная экспертная оценка не заявляется.
* shutdown.log: worker с открытым telemetry завершился за **0.66с**, API с открытым SSE за **3.18с**; runtime/heartbeat keys удалены, Stream0, пять новых JPEG доступны после остановки worker. Unit test отдельно проверяет порядок inference → snapshots drain → delivery drain.

scripts/ — фактически использованные sandbox-specific сценарии. Python сохранён как .py.txt, чтобы не включать standalone QA в строгий source lint; для повторения скопировать в .py и адаптировать пути/порты/PID. browser.cjs требует Playwright/Chromium. Outage/shutdown реально останавливают сервисы: только QA окружение! `make check` и integration с отдельными DB — штатные команды.

Нет проверки Windows, Docker/CI, GPU/CUDA, RTSP, moving-CCTV quality, 4/8-camera нагрузки, filesystem hang/host loss и adversarial filesystem concurrency. Полные ограничения — PROGRESS/ADR-035.
