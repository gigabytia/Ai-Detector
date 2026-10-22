# Обновление M11 → M12

Архив содержит настоящую полную `.git` M4→…→M12, исходники, веса, QA. Не git init, не заменять только bundle. База M11 0a0aafd, автор Kostya.

1. Backup PostgreSQL/Redis/AOF/uploads/snapshots; сохранить свои .env/изменения. Остановить API/worker, распаковать в отдельную папку; git status/log/fsck, history не пересоздавать. Для существующего clone fetch/ff из распакованного repo.
2. Python3.12, Node ^22.22.2 или >=24.15.0 (QA24.15.0). Перенести свой .env/mounts, `uv sync --frozen` (новый prometheus-client0.26.0), `npm --prefix frontend ci`.
3. `uv run alembic -c backend/alembic.ini upgrade head`: новых M12 migrations нет, head остаётся b6b7cfcd87c5. Нельзя пропустить предыдущую M11 migration при обновлении с M10. Камеры/геометрия/events/snapshots/analytics сохраняются.
4. Запустить API/worker/frontend прежним способом. INFERENCE_THREADS=2 теперь реально применяется **после** predictor warmup; до M12 Ultralytics мог перезаписать его в1. Нагрузка CPU/throughput могут вырасти, сначала наблюдать метрики. Defaults target10/batch4/wait20/threads2 сохранены; override только после своих замеров. Compose теперь передаёт inference/preview параметры, но контейнеры в QA не запускались. Image CPU-only, GPU не заявлен.
5. Worker `/health/ready` → detector.inference_threads actual, `/metrics` — Prometheus по worker port8001, без auth, не публиковать в интернет. `process_cpu_seconds_total`/RSS, histogram detector whole-call/local frame, buffer/inflight/outbox gauges. Границы — docs/metrics.md. Ранний inference_ms UI остаётся amortized duration/frame внутри batch, не E2E latency.
6. Для собственного measured baseline: `uv run python benchmarks/pipeline.py --source /path/to/clip.mp4 --cameras 8 --threads 2 --batch 4 --duration 20 --out /tmp/qa-8`. Source/model SHA и actual threads в meta; outputs не перезаписываются. CPU-only isolated pipeline, no external storage. Exact runtime bus MP4 не вложен. Сравнивать одинаковое железо/clip/settings; GPU/real RTSP/full storage нужны отдельно. Не запускать нагрузку/QA outage на production.

Документы: PROGRESS.md, docs/qa/m12/README.md/REPORT.md и ADR-039. Не обещается10FPS на8 CPU-камерах или zero loss. Прежние RAM/AOF/retention/security риски остаются. Новая оптимизация после измерений на целевой среде, не вслепую TensorRT.
