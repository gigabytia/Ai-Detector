# Поведение системы: правила и значения по умолчанию

Все значения в таблице — default в конфигурации (pydantic-settings, env), не hardcode. Отмеченные «(камера)» можно переопределить для камеры в `camera_configs`. Значения с пометкой **[агент]** в ТЗ не заданы и выбраны при проектировании ([ADR-021](decisions/ADR-021-agent-defaults.md)).

## 1. Параметры

Параметр появляется в коде вместе с функцией, которая его использует (§56). `.env.example` содержит только уже используемые параметры.

| Параметр | Default | Где применяется |
|---|---|---|
| `TARGET_FPS` (камера) | 10 **[агент]** | частота обработки, 1–30; умолчание API и переопределение камеры |
| `MODEL_MANIFEST_PATH` | `models/person-detector/manifest.yaml` | модель, SHA-256, класс person, размер входа |
| `INFERENCE_DEVICE` | `auto` | `auto` \| `cpu` \| `cuda`; `auto` = CUDA при наличии, иначе CPU |
| `INFERENCE_BATCH_SIZE` | 4 **[агент]** | максимум кадров в батче |
| `INFERENCE_MAX_WAIT_MS` | 20 **[агент]** | ожидание добора батча |
| `DETECTION_CONFIDENCE` (камера) | 0.25 | порог детектора |
| `DETECTION_IOU` | 0.45 | NMS |
| `INFERENCE_THREADS` | 2 | CPU-потоки PyTorch; размер входа — из манифеста (`input_size=640`) |
| `PERSON_TRACK_MAX_AGE` | 25 | кадров без совпадения до удаления трека |
| `TRACK_MATCH_IOU` | 0.5 | порог IoU сопоставления |
| `TRACK_ACTIVATION_CONFIDENCE` | 0.25 | минимум confidence для нового трека |
| `EVENT_MIN_TRACK_HITS` | 3 **[агент]** | трек участвует в правилах после N кадров с детекцией |
| `ZONE_ENTER_DWELL_SECONDS` (камера) | 0.25 | подтверждение входа |
| `ZONE_EXIT_GRACE_SECONDS` (камера) | 0.5 **[агент]** | подтверждение выхода |
| `LOITERING_THRESHOLD_SECONDS` (камера) | 10 | долгое нахождение |
| `LINE_HYSTERESIS` | 0.01 **[агент]** | полоса нечувствительности у линии (норм. ед.) |
| `EVENT_COOLDOWN_SECONDS` (камера) | 3 | подавление повторов |
| `SEVERITY_ZONE_ENTER` / `SEVERITY_LINE_CROSS` / `SEVERITY_LOITERING` | `critical` / `warning` / `warning` | важность событий |
| `SNAPSHOT_ENABLED` (камера) | true | снимок события |
| `SNAPSHOT_PATH` | `./data/snapshots` | локальное хранилище |
| `SNAPSHOT_RETENTION_DAYS` | 30 **[агент]** | срок хранения снимков |
| `PREVIEW_FPS` | 5 **[агент]** | FPS превью для открытых камер |
| `PREVIEW_MAX_WIDTH` | 640 **[агент]** | ширина превью, px |
| `RECONNECT_INITIAL_DELAY_SECONDS` / `RECONNECT_MAX_DELAY_SECONDS` | 1 / 30 **[агент]** | backoff переподключения (×2) |
| `MAX_CAMERAS` | 8 **[агент]** | лимит при создании камеры (422) |
| `UPLOAD_MAX_BYTES` | 2 ГБ **[агент]** | загрузка видео |
| `UPLOAD_ALLOWED_EXTENSIONS` | `.mp4,.mov,.mkv,.avi` **[агент]** | загрузка видео |
| `WORKER_OUTBOX_MAX_ITEMS` | 10000 **[агент]** | буфер сообщений при недоступном Redis |
| `TEST_MODE` | false | фиксированные часы и сценарии (§181) |

Константы кода (не настраиваются в MVP, при необходимости вынесем): DEGRADED при `processed_fps < 0.8 × min(TARGET_FPS, FPS источника)` дольше 5 с либо при ошибке inference; автоматическое восстановление при нормализации; TTL статуса 5 с; пакет аналитики раз в 10 с; JPEG quality 80.

## 2. Точка человека и координаты

* Точка отсчёта (anchor) — **нижний центр bbox**: `((x1 + x2) / 2, y2)`.
* Зоны и линии хранятся в нормализованных координатах `0 ≤ x, y ≤ 1` (0,0 — левый верхний угол). Детектор и трекер работают в пикселях; worker нормализует bbox делением на размер кадра. Сравнение anchor с зоной/линией — в нормализованном пространстве (это эквивалентно пиксельному, т.к. масштабирование аффинно).
* Смена разрешения камеры не сдвигает зону.

## 3. Трекинг

* ByteTrack (`trackers 2.6.1`) через adapter ([ADR-032](decisions/ADR-032-bytetrack-runtime.md)). `tracker.update()` вызывается на **каждом** обработанном кадре, в том числе с пустым списком детекций.
* «Пропущенный кадр» — обработанный (по `TARGET_FPS`) кадр без совпадения, а не кадр источника. При 10 FPS 25 кадров ≈ 2,5 с.
* Трек без совпадения переходит в `LOST`, на `PERSON_TRACK_MAX_AGE`-м последовательном пропуске удаляется. Если за это время найден снова — тот же `track_id`, без новых событий входа.
* `track_id` — положительное целое, уникально в пределах камеры и запуска (`run_id`). Межкамерной идентификации нет.
* Новый кандидат получает ID после следующего совпадения; до подтверждения рисуется только детекция. `first_seen`, `age`, `hits` начинаются с подтверждения; `age` включает пропуски, `hits` — наблюдения. Center — центр bbox, anchor — низ-центр.
* `LOST` содержит последнее наблюдение, не текущий bbox: его рамка не рисуется, число людей равно числу детекций текущего кадра. Пустые детекции передаются трекеру; ошибка inference не подменяется пустым результатом и не старит треки.
* Цикл файла/mock, reconnect или смена разрешения сбрасывают сцену, но не счётчик публичных ID внутри run. Capture `source_epoch` сохраняет факт разрыва даже при вытеснении первого кадра из latest-frame буфера. Горячая смена FPS/порога не сбрасывает трекер.
* С M6 реализованы `NORMAL`, `IN_DANGER_ZONE`, `LOST` и правило входа в зону. Track sessions, линии, loitering и аналитика — последующие этапы; timestamps разделены на UTC и время источника.

## 4. Состояния человека

`PersonState`: `NORMAL`, `IN_DANGER_ZONE`, `LOST`. Пересечение линии — мгновенное событие, а не состояние ([ADR-014](decisions/ADR-014-person-states.md)).

Для каждой пары (трек, зона) — автомат членства:

```text
OUTSIDE ──anchor внутри──► ENTERING ──внутри ≥ dwell──► INSIDE ──anchor снаружи──► EXITING
   ▲            │ снаружи                    (событие входа)  ▲          │ снаружи ≥ grace
   └────────────┘                                            └─внутри────┘          ▼
   ◄──────────────────────────────────────────────────────────────────────────── OUTSIDE
```

* `IN_DANGER_ZONE`, если хотя бы одна зона в `INSIDE` или `EXITING`. Иначе `NORMAL`.
* Граница полигона считается внутренней областью.
* Время dwell, grace и loitering считается по `source_ts_ms` кадров. Пока трек `LOST`, автомат заморожен; при удалении трека визит закрывается без событий.
* Человек, появившийся сразу внутри зоны, после dwell считается вошедшим.

## 5. Правила событий

Правило применяется только к трекам с `hits ≥ EVENT_MIN_TRACK_HITS` и в состоянии не `LOST`.

| Событие | Условие | Сколько раз |
|---|---|---|
| `PERSON_ENTERED_DANGER_ZONE` (critical) | переход `ENTERING → INSIDE` | один раз за визит |
| `PERSON_LOITERING_IN_DANGER_ZONE` (warning) | визит длится ≥ `LOITERING_THRESHOLD_SECONDS`, отсчёт от первого кадра внутри (начало `ENTERING`); время в `EXITING` с возвратом входит в визит | один раз за визит; выход сбрасывает |
| `PERSON_CROSSED_LINE` (warning) | подтверждённая сторона линии сменилась | на каждую смену стороны |

### Пересечение линии

* `s = (P2 − P1) × (A − P1)`, `d = s / |P2 − P1|` — знаковое расстояние anchor `A` до прямой.
* Подтверждённая сторона меняется только при `|d| > LINE_HYSTERESIS`; внутри полосы сохраняется прежняя. Ноль и колебания у линии пересечением не считаются.
* Пересечение засчитывается, только если проекция `A` (в момент подтверждения новой стороны) попадает на отрезок P1–P2, а не на продолжение прямой ([ADR-013](decisions/ADR-013-line-crossing.md)).
* Первый кадр трека только задаёт сторону. Если трек был `LOST` и найден на другой стороне — это пересечение.
* `metadata.direction`: `LEFT_TO_RIGHT` / `RIGHT_TO_LEFT` относительно направления P1→P2 (знак `s` с «−» на «+» и наоборот). Срабатывают оба направления.

## 6. Cooldown и дедупликация

* Ключ: камера + `track_id` + тип события. Часы — wall clock (в тестах — фиксированные). Попытка события раньше чем через `EVENT_COOLDOWN_SECONDS` после предыдущего с тем же ключом подавляется (debug-лог; метрика `events_suppressed_total` — будущий этап).
* Основная защита от повторов — автоматы (один вход за визит); cooldown страхует от «дребезга» визитов длиннее grace ([ADR-008](decisions/ADR-008-cooldown.md)).
* Дубли при доставке исключены первичным ключом `events.id`.

## 7. Confidence события

`event_confidence = mean_conf × stability`, где `mean_conf` — средняя confidence детектора по треку за окно подтверждения (dwell для входа; весь визит для loitering; последние `EVENT_MIN_TRACK_HITS` кадров для линии), `stability` — доля кадров окна, где у трека было совпадение с детекцией (а не только предсказание). Результат в `[0, 1]`. В событие пишутся обе величины.

## 8. Snapshot

Полный кадр события в JPEG, без нарисованных рамок; рамку и зону рисует frontend по `metadata`. Кодируется и сохраняется в пуле потоков, inference не ждёт. Ошибка сохранения — лог, событие уходит без снимка.

## 9. Статусы события

`NEW → ACKNOWLEDGED` или `NEW → FALSE_POSITIVE`. Другие переходы — 409. К событию можно добавить заметку (в любом статусе). Время перехода пишется в `acknowledged_at` / `false_positive_at`.

## 10. Источники

| Тип | Поведение |
|---|---|
| `file` | воспроизводится в реальном темпе (по PTS), по окончании — с начала; при перемотке на начало трекер и автоматы сбрасываются (новый `run_id` не создаётся, `source_ts_ms` продолжает расти) |
| `rtsp` | чтение последнего доступного кадра (буфер OpenCV = 1, буфер сессии = 1 кадр); таймаут открытия и чтения 5 с; при ошибке — `RECONNECTING` с backoff 1 → 30 с |
| `mock` | синтетические кадры по сценарию `mock://{scenario}`; детекции даёт `scripted`-детектор по тому же сценарию ([ADR-016](decisions/ADR-016-mock-mode.md), [ADR-024](decisions/ADR-024-mock-scenarios-location.md)) |
| общее | если обработка отстаёт, файл пропускает декодирование лишних кадров, а не замедляет время видео; `ERROR` — только для неустранимых ошибок ([ADR-025](decisions/ADR-025-frame-source-contract.md)) |

## 11. Аналитика камеры

Длительность наблюдения, среднее и максимальное число людей, число уникальных треков; временной ряд раз в секунду (людей всего, людей в зоне); сегменты треков (состояние, начало, конец) для track timeline. Формулы — [database.md](database.md#как-считаются-показатели-03-72).

## 12. Экспорт

`GET /api/v1/events/export` с теми же фильтрами, что и список (камера, тип, severity, статус, период), отдаёт CSV (UTF-8 с BOM для Excel, разделитель `;`), потоково, не более 100 000 строк.

## Историческая граница M6

Пункты про линии, loitering, snapshot, сохранённые статусы и аналитику выше описывают целевое поведение, не готовые функции. Сейчас работает polygon CRUD/редактор, автомат входа/выхода и генерация PERSON_ENTERED_DANGER_ZONE в DetectionResult и JSON-логе. Доставка, ingest и панель событий — M7. Подробная семантика LOST, геометрии, горячих изменений и окна confidence — [ADR-033](decisions/ADR-033-danger-zone-runtime.md). При генерации события minimum hits проверяется вместе с dwell; настройка severity пока глобальная для worker.

## Реализованная граница M7

События входа доставляются live и пишутся в историю, операторские NEW/ACKNOWLEDGED/FALSE_POSITIVE и заметки сохраняются. Повтор выбранного финального статуса идемпотентен, другой переход блокируется. Снимков, линий, loitering, CSV и сохранённой аналитики пока нет. При отказе БД live тревога остаётся доступной, подтверждение ожидает ingest. Reconnect восстанавливает историю REST-запросом, не SSE replay. Границы сохранности — [ADR-034](decisions/ADR-034-event-delivery-realtime.md).

## Реализованная граница M8

Снимки и event detail реализованы согласно ADR-015/035: один полный JPEG без графики, bbox/anchor overlay Vue (polygon snapshot пока не сохраняется). `SNAPSHOT_ENABLED=true` API default, per-camera inherit/on/off; `SNAPSHOT_PATH=data/snapshots` общий API/worker; `SNAPSHOT_RETENTION_DAYS=30` (1…3650), `SNAPSHOT_CLEANUP_INTERVAL_SECONDS=3600` (10…86400). Snapshot failure не блокирует inference/само событие. История M7 сохраняется и без файла. Строки выше про неготовый snapshot относятся к историческим границам M6/M7. Линии/loitering/analytics по-прежнему не реализованы.

## Граница реализации M9

Правила §5 реализованы LineEngine (ADR-036): конечный отрезок, projection текущего anchor при подтверждении, оба signed направления, hysteresis, LOST freeze/recovery, bounded confidence window, wall-clock cooldown отдельно от зоны. Crossing — событие, не состояние PersonTrack. Линии hot CRUD и историческая геометрия в event detail доступны; loitering, dashboard и аналитика пока нет.

## M10 — dashboard/track timeline

Период UTC [start,end), default24ч, REST≤31д, UI1ч/24ч/7д с ручным обновлением. Events включают false positives, current status; среднее событий делится на все зарегистрированные выбранные камеры, включая архивные/нулевые. Active cameras — сейчас (RUNNING/DEGRADED), Redis error неизвестно/null. Нет PostgreSQL →503/повторить, не нулевые KPI.

People sampled1Hz latest, max не frame peak, mean не frame weighted. Missing observations не zero. Observed duration суммирует gaps≤2с без extrapolation; gap>2с исключён и в retained track timeline обозначается LOST. Треки camera/run/track, не физические уникальные люди, только завершённые, полные сессии при overlap периода. Collector4096/cap2048segments/truncated, outbox1000; caps — implementation safety, не новые env settings. Нет automatic analytics retention. См. ADR-037.

## M11 — loitering / CSV

LOITERING_THRESHOLD_SECONDS=10 в API, camera override nullable0..3600; worker SEVERITY_LOITERING=warning. Strict source duration>threshold, entry dwell включён, но outside/LOST/backward/gap>2с сбрасывает непрерывный таймер. Fired visit сохраняется до confirmed exit, затем cooldown/re-entry. Не меняет M6 entry/grace или PersonState. Подробнее ADR-038.

CSV current camera/status/type/aware [start,end) filters, весь persisted набор, не page50/live-pending. All-time либо UI fixed1ч/24ч/7д+refresh. 50000rows/20MiB cap→422 без truncation, DB/timeout→503 без download. UTC/UTF8BOM/comma/CRLF, formula mitigation; native Excel import не проверен.
