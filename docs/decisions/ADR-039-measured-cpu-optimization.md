# ADR-039 — измеряемая CPU optimization и локальные метрики

Статус: принято, M12. База ADR-006/021/038; не менять domain state/rules/storage ради throughput.

19 short runs показали saturation ~15FPS total на8 копиях static MP4 при request threads2. Repeat исходников M11 показал actual torch threads1: Ultralytics первый predictor setup перезаписывает global PyTorch thread setting. Исправление — восстановить явный setting после одноразового warmup; actual count в readiness/metrics. Не менять default2 и не вводить autotuning/магическую оценку CPU. На8 повторе M12 actual2 дал23.24 totalFPS против15.51 baseline; CPU119.4→171.9% одного core. Это использование большего CPU, не бесплатный speedup или GPU/RTSP SLA.

Batch collector не может брать две frames одной камеры. Поэтому ждать configured batch4 при единственной RUNNING камере бессмысленно; закончить сбор, когда нет другой eligible camera. Для других running/DEGRADED cameras deadline20мс и fair rotation сохранены; source reconnect не блокирует batch. ABBA single camera при одинаковом detector2 отделяет этот эффект от thread fix: pooled raw p50~105.4→93.3мс; не гарантированные20мс и не statistical confidence interval.

Наблюдаемость — worker-local per-instance Prometheus registry, fixed histogram buckets и bounded labels, no external I/O на scrape. Capture handoff monotonic clock не заменяет source timestamps для правил/analytics. Whole detector-call latency отделена от прежнего elapsed/batch-size inference_ms. Source network/decode/browser/persistence latency не измеряется новым local metric. Dropped captures, waiting outbox и stream backlog — разные сущности.

Benchmark CLI отделён от production entrypoint, no external stores, outputs19 raw runs+единый evidence, независимый count/quantile check и exact metadata. Политика legacy-batch-wait доступна только в benchmark для ablation, не runtime setting. M11 repeat взят из commit0a0aafd без новой Git истории.

Не включать ONNX/TensorRT/GPU-compose до CUDA/target-device measurements. Не снижать target/defaults, не отключать тревоги/снимки, не писать кадры в БД ради PASS. На4/8 target10/камера не достигнут. Далее real RTSP/GPU/длительный full-pipeline/storage load и deployment/security. RAM/AOF/crash/retention ограничения прежние. Детали QA/report/metrics в соседних docs.
