# QA Milestone 12

## Контроль качества

- `check-final.log`: **254 Python unit,129 frontend (23 файла)**, strict mypy172 файлов, Ruff/format174 файлов, ESLint/Prettier/vue-tsc, production build Node24.15.0. M11 unit241 +13 новых: bounded buffer, monotonic clock/unknown latency, restart/removal labels, histogram/registry isolation, HTTP metrics без network I/O, eligible batch membership, one-camera no impossible wait success/error,3 thread warmup reset cases, stop-during-wait.
- `integration-final.log`: **41 passed**, PostgreSQL17.10/Valkey9.0.5. M12 storage schema/contracts не меняет; alembic no diff, uv lock check, backend OpenAPI regeneration совпала, production npm audit0. Пакет prometheus-client0.26.0 зафиксирован новым uv.lock.
- Compose YAML/performance env mappings проверены статически; Docker/CI/Windows/GPU не запускались. Lazy ECharts chunk556.91kB/189.09kB gzip предупреждает о размере, build успешен. Прежние dev audit4high не исправлялись.

## Измерения

Основной отчёт [REPORT.md](REPORT.md), единый evidence.json. **19 runs**, каждый5с warmup +20с measured window. Raw grains отдельно: frames (одна delivery), batches (один detector call), samples (одна250мс process sample), metadata. Повтор M11 использовал исходники commit0a0aafd через PYTHONPATH, не M12 emulation; в meta effective_torch_threads1. M12 actual2. Main matrix1/4/8 и repeat8 сохранены; ABBA одной камеры держит adapter/threads одинаковыми и меняет только wait policy.

Benchmark — копии одного paced6с static bus MP4,810×1080,15FPS,90 кадров, input640, SHA-256 вmeta. Это проверка pipeline throughput, не varied/moving-CCTV accuracy или уникальных физических посетителей. Реальный исходный runtime MP4 **не включён** в ZIP; для сравнимого повтора нужны те же байты. Portable CLI принимает собственный локальный clip; с другим clip цифры несопоставимы. Source characteristics — source-video.json. Скрипт не скачивает ничего, использует bundled проверенные веса и требует запуск из корня repo.

CPU2 logical vCPU, Xeon2.90GHz, cgroup RAM4GiB, CPU quota unlimited; PyTorch2.14.1+cpu, Python3.12.15. Process CPU100%=одно логическое ядро, RSS peak — sampled после warmup. Capture queue≤1/камера, selected batch отдельно≤4. Нет full API/Redis/DB/snapshot/analytics I/O в4/8 load runs, нет viewers в main matrix. Runtime I/O проверялся отдельно на3 камерах.

Числа проверены independent raw line count/ключами(camera_id,frame_id)/sorted quantile interpolation. Нет пропущенных/duplicate keys. Constant profiler warnings ожидаемы (fixed batch, один ID в1cam, depth1, стабильный degraded); ничего не удалено. Exploratory `threads1-*` до исправления сравнивали requested settings, а не фактически разные thread counts; не используются как причинное доказательство.

HTML график построен canonical inline builder, static preflight прошёл; helper загрузки SessionFile не вернул результат, поэтому inline preview не публиковался и не заявляется. Исходный HTML/spec остаётся в архиве, график не пересоздавался обходным путём. Скриншоты/экспертный визуальный review не выполнялись.

## Живой pipeline и отказ Redis

`live-proof.json`:3 камеры (CPU YOLO +2 mock), readiness actual_threads2, real/scripted detector histograms, entry/loitering→история/CSV matching IDs, JPEG читается.24 успешных scrapes /metrics во время12с Redis outage; heartbeat failure виден, processed counter растёт, analytics RAM queue достигла48 waiting records. После восстановления events/analytics health1, drops0, оба Streams0. Это не zero-loss гарантия при crash: прежние RAM/AOF окна сохраняются. Scrape не ждёт Redis/PG; outbox gauge не включает уже взятый pending record или Redis Stream backlog.

Shutdown: worker1.01с/API с открытым SSE3.16с, runtime keys удалены, оба Streams0,6 новых completed sessions при остановке,147 sessions для текущих runs,5 JPEG читаются после worker stop. Benchmark CLI smoke выполнен, threads0 отвергнут с exit2; shutdown-final.log/benchmark-smoke.log/benchmark-invalid.log. Outage/shutdown скрипты .txt привязаны к sandbox paths/ports и останавливают сервисы; не запускать на production. Integration требует отдельные test DB/Redis, **лучше отдельный Redis instance: Pub/Sub не изолируется логическим DB13**. Случайные test camera UUID не должны пересекаться с живыми; в этом прогоне live listener получал404 для test UUID без изменения настоящих камер.

## Не проверено

GPU utilization/VRAM/CUDA/ONNX/TensorRT, реальные RTSP/потери сети/декодирование камер, moving accuracy, длительная4/8-camera полная storage нагрузка, Docker/CI/Windows, production SLA и auth. Short sequential runs без confidence interval; нельзя переносить throughput на другое железо/ролик. Defaults target10/batch4/wait20/threads2 не занижались ради PASS; на4/8 target10 не достигнут, DEGRADED не маскировался. Следующие проверки — на целевом железе/реальных потоках и длительная end-to-end нагрузка, затем следующая оптимизация по замерам.
