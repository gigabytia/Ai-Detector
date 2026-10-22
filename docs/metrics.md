# Worker metrics — M12

`GET /metrics` на worker HTTP8001. Prometheus text0.0.4, no-store, без auth, только private/trusted network. Отдельный registry на Scheduler, не global singleton. Scrape читает локальные counters/gauges и standard OS process collector, **не** запрашивает Redis/PG/API/GPU. Доступен при недоступном Redis; health — последнее известное состояние, не новый ping.

| Series | Значение/границы |
|---|---|
| process_cpu_seconds_total / process_resident_memory_bytes | standard prometheus-client ProcessCollector где OS поддерживает; CPU percent=100×rate(cpu_seconds[1m]),100%=одно логическое ядро, не вся машина |
| ai_detector_detector_info | backend/model/device/actual inference_threads; не секреты/source URL, CUDA device не utilization |
| ai_detector_detector_call_seconds / detector_batch_size | histogram whole call и batch size с kind=real/scripted; real failed calls также наблюдаются; scripted successful calls. Не старое amortized inference_ms |
| ai_detector_local_frame_latency_seconds | cumulative histogram monotonic handoff после source.read→result delivery до preview/network/storage completion. Не source PTS/wall clock и не sensor→browser. Frames без monotonic timestamp не считаются, а не превращаются в0 |
| ai_detector_batch_wait_seconds | first selected frame→executor submission; max configured deadline плюс scheduler jitter, не hard realtime |
| ai_detector_inflight_frames | selected batch, включая wait/processing; capture pending buffers отдельно |
| ai_detector_processed_frames_total / pipeline_errors_total / stale_results_total | worker lifetime delivered/failed/obsolete frame results; reset при restart worker, не persistent counts |
| ai_detector_generated_events_total{type} | rule alarms до downstream ACK, не число сохранённых/уникальных физических событий в БД |
| ai_detector_camera_capture_fps / processed_fps | sliding2с, по текущим sessions, не throughput-SLA |
| camera_capture_queue_depth / dropped_frames | depth0/1 и replacement counter run как gauge, reset при restart. Это пропуски кадров по latest policy, не потерянные alarms |
| camera_processed_frames / active_tracks / result_age_seconds / local_latency_seconds | run gauge count, non-LOST tracks последнего result и его age. Age/latency отсутствуют до first result; при stop/restart stale labels удаляются на следующем scrape. Нет run_id/frame_id labels |
| camera_reconnect_attempts | current backoff attempts, сбрасываются при success; не cumulative reconnect total |
| ai_detector_outbox_queue_depth{kind} / outbox_dropped / delivery_healthy | events/analytics waiting RAM queue; **не включает** один взятый pending retry, snapshot tasks или Redis Stream backlog. Drops с startup. Health не end-to-end durability |
| ai_detector_redis_healthy / cuda_enabled | cached heartbeat result и выбранный detector device. CUDA1 не гарантирует idle/VRAM/utilization, эти измерения отсутствуют |

Cumulative histograms имеют фиксированные buckets и bounded kind/type labels; camera gauges только live session IDs, children удаляются после removal, нет cardinality по source URL/run/frame. Result age нужен, чтобы не принять stale active_tracks за текущее наблюдение. Snapshot/preview уже имеют bounded queues/on-demand encoding, но их queue sizes пока не экспортируются. Operator false-positive counter/DB stats/Stream backlog/GPU util не притворяются нулями — их здесь нет.

Для одного worker p95 local за окно: `histogram_quantile(0.95, sum by(le) (rate(ai_detector_local_frame_latency_seconds_bucket[5m])))`. Единицы seconds; coarse histogram p95 не равен exact sample p95 из benchmark. Scrape interval/rate window выбирать на deployment; Prometheus/Grafana stack не развёрнут. process metrics platform-dependent, Windows здесь не проверен.
