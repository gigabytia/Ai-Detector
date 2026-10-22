# QA — Milestone 9

Linux x86_64, Python3.12.15, PostgreSQL17.10 UTF8, Valkey9.0.5, CPU YOLO26n/ByteTrack +2mock; Node24.14.1 ниже engine (использовать ^22.22.2 или >=24.15.0). База — полный Git M8 01ff302, автор Kostya.

## Автоматические

* make-check.log: **199 Python unit, 115 Vitest**, strict mypy158 файлов, ruff/format, ESLint/Prettier/vue-tsc и production build. Новые22 Python tests: обе стороны, полоса/касание, finite segment/концы/extension, обратный P1/P2, LOST/confidence, min_hits, wall-clock cooldown общий линиям/разный tracks, rename/edit/disable/delete, source/run/size reset, совместные zone+line без PersonState change, typed metadata/refs.
* integration.log: **33 passed**, реальные PostgreSQL/Valkey; прежние29 + CRUD validation/scope/hot spec/notify, limit16, crossing+snapshot/duplicate/operator note/FP/geometry edit/delete/history/replay, чужая line reference→null.
* migration-roundtrip.log: M8→M9, downgrade/upgrade только test DB, alembic check no schema diff. empty-db-migration.log — все revisions с пустой UTF8 DB. lock-check.log, OpenAPI повторно сгенерирован и cmp совпал; npm-audit-production.json —0 vulnerabilities. Dev-audit не повторялся.

## Живые

* live.log: walk_through идёт слева направо и сбрасывает source epoch при loop, не движется назад. Для второго signed направления **развёрнуты endpoints линии**; получены RIGHT_TO_LEFT и LEFT_TO_RIGHT в одном camera run, оба с исходным JPEG1280×720. Нельзя выдавать loop за обратный crossing. Preview содержит точную hot line geometry. Изменение name/endpoints не переписывает старые metadata; disable22с (сценарий20с) подавляет события, re-enable сохраняет run.
* postgres-outage.log: вся QA PostgreSQL остановлена; новый PERSON_CROSSED_LINE пришёл по SSE с direction, JPEG записан до ingest, PATCH409, storage_key не раскрывается. После восстановления тот же event UUID, snapshot UUID, SHA-256 JPEG, backlog0. Это восстановление при работающем worker/Redis, не host-crash zero-loss гарантия.
* browser.log: реальный API/Vite + local Chromium/Playwright. Историческая линия exact normalized coordinates в SVG, сохранение note, editor keyboard coords → REST → hot preview geometry; cap2/click/undo/cancel без write, zone editor заблокирован на время line draft. Desktop/light/dark/390px screenshots, horizontal overflow0, pageerror0. Это DOM/layout/API проверки; PNG сохранены без экспертной визуальной оценки через image viewer. Letterbox математически проверяется прежними geometry tests; отдельный live letterbox сценарий M9 не заявляется.
* shutdown.log: worker **1.19с**, API с открытым SSE **3.24с**; runtime/heartbeat keys удалены, Stream0, пять JPEG читаются после остановки worker.

Исходная SQL_ASCII QA DB сохранена: для локализованных line_name JSONB использована отдельная UTF8 копия, не fallback с потерей имени. Скрипты scripts/ специфичны sandbox; .py.txt скопировать в .py и адаптировать пути. Integration только отдельные DB (TRUNCATE + Redis13 flush). Outage/shutdown реально останавливают сервисы — не production.

Новые линии испытывались на детерминированном mock; реальный CPU YOLO на MP4 из статичного bus.jpg продолжал создавать zone events, но это не quality benchmark crossing на движущемся CCTV. Не проверены Windows, Docker/CI, GPU, RTSP, 4/8-camera нагрузка и host loss. M8 RAM/AOF/storage/retention ограничения сохраняются; Redis-outage M8 не повторялся для M9. Нет auth/CSV/loitering/track sessions/dashboard. Следующий M10 — event/camera statistics и timeline.
