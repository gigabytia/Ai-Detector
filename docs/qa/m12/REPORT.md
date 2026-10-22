# M12: измерения CPU pipeline

Потоки — копии одного статичного bus MP4; target10 FPS на каждый. Warmup5с, затем20с; модель YOLO26n640, CPU, batch4/wait20. Это изолированный capture→detector→ByteTrack→scene pipeline без внешнего storage I/O и без viewers, не capacity SLA для реальных RTSP.

| Камер | M11 FPS/камера | M12 FPS/камера | local p95 M11→M12, мс | CPU M11→M12, % одного ядра | sampled peak RSS M11→M12, МиБ |
|---|---:|---:|---:|---:|---:|
| 1 | 9.61 | 9.76 | 161.8 → 114.0 | 77.8 → 80.2 | 526.0 → 535.1 |
| 4 | 3.63 | 5.81 | 360.1 → 238.0 | 110.0 → 173.5 | 696.1 → 754.4 |
| 8 | 1.84 | 3.00 | 344.7 → 234.3 | 121.2 → 172.8 | 784.7 → 795.2 |

CPU100% = одно логическое ядро,200% = два. RSS — максимум250мс samples после warmup, не системная RAM и не абсолютный lifetime peak. local latency harness — captured_at→delivery в одном процессе, не sensor/RTSP/network/decode→browser/persist. Production /metrics использует monotonic capture handoff.

M11 request INFERENCE_THREADS=2 был перезаписан Ultralytics в1 при первом predict. M12 восстанавливает явную настройку после predictor setup; effective2 подтверждён в metadata/health. Предварительные runs `threads1-*` сравнивали requested values при одинаковом effective1 и не доказывают влияние threads.

## Повтор8 камер
- baseline-repeat-8: effective threads1, total15.51 FPS, per-camera1.94, local p95327.1мс, CPU119.4%, sampled peak RSS785.5МиБ.
- final-repeat-8: effective threads2, total23.24 FPS, per-camera2.91, local p95243.4мс, CPU171.9%, sampled peak RSS798.8МиБ.

## ABBA: только batch-wait, adapter/config M12 одинаковы

| Policy | Измеренных кадров | local p50, мс | local p95, мс |
|---|---:|---:|---:|
| legacy | 391 | 105.4 | 134.7 |
| current | 392 | 93.3 | 125.2 |

Legacy принудительно ждёт deadline даже без другой RUNNING камеры. Current заканчивает сбор, когда все RUNNING/DEGRADED камеры уже представлены; для других камер deadline сохранён. Значения объединены по raw frames двух20с windows каждой policy, не усреднённые p95. Самостоятельные windows в evidence.json.

## Отвергнутые/промежуточные варианты

| Вариант8 камер | total FPS | local p95, мс | sampled peak RSS, МиБ |
|---|---:|---:|---:|
| threads1-8 | 13.71 | 371.8 | 788.6 |
| optimized-8 | 13.52 | 402.8 | 804.2 |
| batch1-8 | 12.17 | 149.9 | 680.7 |

Эти exploratory runs выполнены до thread-reset fix, actual1 по библиотечному setup (ранние meta не содержат effective field). Request1 не был отдельным treatment. Batch1/wait0 снизил RSS/local latency, но уступил по throughput, поэтому не принят default. Deadline-only `optimized-8` сам по себе не дал выигрыша: full batch4 не ждёт свободного слота; single20с variance/metrics overhead не доказывают причинного ухудшения. Final M12 measured matrix/repeat actual2 приведены выше.

## Ограничения и данные

Все raw frames/batches/samples/meta сохранены отдельно по run. Уникальный ключ frame=(camera_id,frame_id); FPS сверены независимым count, p50/p95/p99 — sorted interpolation. Пустых/duplicate keys нет. Constant warnings ожидаемы: один camera_id в1-camera run, фиксированный batch size, queue_max1 и стабильный degraded count. Никакие строки/камеры по этим предупреждениям не исключались.

Capture pending queue≤1 на камеру; выбранный batch отдельно≤4. Drops — latest-frame replacements, не потерянные сохранённые события. На4/8 камерах DEGRADED ожидаем, target10 не достигнут; не скрываем уменьшением target или порога. GPU недоступен (CPU build), его загрузка/VRAM не измерялись. Реальные RTSP, accuracy, full4/8 storage-I/O, GPU, Docker/CI/Windows не проверены. Нет ONNX/TensorRT, batching policy/default4 и target10 не снижены.
