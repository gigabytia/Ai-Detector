# AI Detector v2

Система видеонаблюдения: детекция и трекинг **людей**, события входа в опасную зону, пересечения линии и долгого нахождения в зоне, интерфейс оператора.

**Статус:** Milestone 12 завершён в CPU-среде: reproducible benchmark CLI, Prometheus /metrics, исправлено применение inference threads и лишнее ожидание batch. M11 loitering/CSV и предыдущая pipeline сохранены. GPU/реальные RTSP/длительная end-to-end нагрузка не проверены. Обновление — [UPDATE_MILESTONE_12.md](UPDATE_MILESTONE_12.md), проверки — [PROGRESS.md](PROGRESS.md), [измерения](docs/qa/m12/REPORT.md).

## Архитектура

Frontend (Vue 3) ↔ API (FastAPI) ↔ PostgreSQL / Redis ↔ Vision worker. Inference — только в worker'е. Подробно: [architecture.md](docs/architecture.md), [data-flow.md](docs/data-flow.md), [database.md](docs/database.md), [behavior.md](docs/behavior.md), [решения](docs/decisions/README.md).

## Быстрый старт

```powershell
Copy-Item .env.example .env        # bash: cp .env.example .env
uv sync; npm --prefix frontend ci
uv run ai-detector-model           # скачать и проверить веса; можно не выполнять, если веса уже есть
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
uv run ai-detector-seed           # демо-камеры и пример зон
uv run ai-detector-api             # терминал 1
uv run ai-detector-worker          # терминал 2
npm --prefix frontend run dev      # терминал 3 → http://localhost:5173
```
Или всё в Docker: подготовьте веса (`uv sync; uv run ai-detector-model`), затем `docker compose up --build` → http://localhost:8080. Каталог `models` подключается к worker в режиме чтения; без проверенных весов worker завершится с кодом 1. API-контейнер при старте сам выполняет `alembic upgrade head`; для ручного запуска миграций: `docker compose run --rm api alembic upgrade head`.

## Окружение и команды

Переменные — [.env.example](.env.example). Все команды (make и PowerShell), тесты и миграции — [docs/development.md](docs/development.md). API — [docs/api.md](docs/api.md).

## Камеры

Источники: локальный видеофайл (загружается через UI, играет по кругу в реальном темпе), RTSP-камера, демо-сцена без камеры (`mock://walk_through`, `mock://two_people`). Как подключить свой `.mp4` и проверить RTSP без камеры — [docs/development.md](docs/development.md#пример-видео-108). Для mock-камер детекции берутся из сценария (маркировка «ДЕМО»); для файла/RTSP работает настоящая модель. Плитка открывает крупный просмотр и настройки. Рамки рисуются на canvas, число людей — число детекций текущего кадра, не уникальных посетителей. ByteTrack сохраняет ID людей внутри камеры и запуска; подтверждённые рамки подписаны `Человек #ID`. Временная потеря детекции сохраняет ID до 25 обработанных пропусков. При цикле видео сцена сбрасывается, старые ID в том же запуске не переиспользуются. Это не распознавание личности и не межкамерный re-ID.

Модель `yolo26n` и Ultralytics: AGPL-3.0; перед production-использованием проверьте лицензионные требования ([ADR-006](docs/decisions/ADR-006-inference-runtime.md)).

Стенд предназначен для локальной доверенной сети: аутентификации оператора пока нет. Не выставляйте API/worker напрямую в Интернет. Исходное ТЗ повторно предоставлено пользователем и сохранено в [docs/spec/AI_DETECTOR_v2_MASTER_PROMPT.md](docs/spec/AI_DETECTOR_v2_MASTER_PROMPT.md).

## Опасная зона

Откройте камеру в «Мониторинге» → «Добавить зону» / «Изменить зону». Добавьте 3–64 вершины по порядку кликами на изображении или координатами 0..1 и сохраните. Самопересечения запрещены. «Отмена» не меняет сохранённую зону; удаление требует подтверждения. UI редактирует одну зону; если API создал несколько, остальные не перезаписываются.

Вход подтверждается по нижней точке bbox после dwell (по умолчанию 0.25 с) и ≥3 совпадений трека. Выход подтверждается через 0.5 с; повторные события ограничены cooldown 3 с. Интервалы можно переопределить в настройках камеры. `PERSON_ENTERED_DANGER_ZONE` отправляется в Redis Stream и live pub/sub, сохраняется в PostgreSQL и появляется на странице «События». После seed и запуска worker mock-сценарии сами создают демонстрационные тревоги через настоящий rule pipeline, не фальшивые покадровые записи. При отказе БД live-тревога приходит до записи, ingest догоняет после восстановления. Гарантии и ограничения доставки — [ADR-034](docs/decisions/ADR-034-event-delivery-realtime.md).

## Realtime (M7)

После обновления: `uv sync --frozen`, `npm --prefix frontend ci`, `make migrate`, затем обычные API/worker/frontend. Новая миграция `14d6499b16a2` создаёт events; старые данные камер/зон сохраняются. Полный порядок — [UPDATE_MILESTONE_7.md](UPDATE_MILESTONE_7.md).

«События»: история, камера/статус, пагинация, NEW → подтверждено/ложная тревога, заметка. Focus камеры: отдельная JSON-телеметрия. Превью и рамки остаются согласованными и не зависят от SSE. Детали события показывают исходный снимок и исторические bbox/anchor. Dashboard добавлен в M10, CSV — в M11; авторизации ещё нет.

**Важно:** RAM-outbox не переживает падение worker при недоступном Redis; AOF everysec тоже имеет окно потери. Stream не обрезается до записи в БД: следите за backlog и диском. Не публикуйте сервисы в Интернет.

## Снимки (M8)

`SNAPSHOT_PATH` — один private directory для API и worker (compose: shared volume). Камера наследует API `SNAPSHOT_ENABLED=true` либо override. На событие — один исходный JPEG; ошибка диска/перегрузка не отменяет тревогу. `SNAPSHOT_RETENTION_DAYS=30`, cleanup каждый час; файлы и metadata удаляются без удаления событий. Подробности — [ADR-035](docs/decisions/ADR-035-event-snapshots.md).

## Линии (M9)

Focus камеры → редактор первой линии, две точки P1 → P2 на кадре/keyboard; API поддерживает16. Оба направления, hysteresis0.01, конечный отрезок, нижний bbox anchor. LEFT_TO_RIGHT = −→+, RIGHT_TO_LEFT = +→− относительно вектора линии; не лево/право экрана. Новая линия/новая геометрия сначала получает baseline. Событие PERSON_CROSSED_LINE идёт через прежние SSE/историю/снимки; старое событие хранит своё имя и endpoints после изменения/удаления линии. Требуется PostgreSQL UTF8. Детали — [ADR-036](docs/decisions/ADR-036-line-crossing-runtime.md).

## Аналитика (M10)

«Аналитика» → последние 1 ч / 24 ч / 7 дней → все камеры или одна → «Обновить период». KPI, ECharts/SVG событий по времени/камерам/типам, статистика наблюдений и отдельный TrackTimeline. При одной камере доступен график людей/людей в зоне; неизвестные интервалы не соединяются и не заменяются нулями. Завершённые треки — camera/run/track, **не уникальные физические люди**. Активные треки появятся после завершения. Среднее/максимум людей считаются по последним наблюдениям каждой секунды, не по всем кадрам. Запросы используют сохранённые данные; live-счётчик камер отражает состояние сейчас, а не выбранный период.

Новый независимый analytics Stream не блокирует alarm pipeline. История требует PostgreSQL; ошибка показывает 503/повторить, не правдоподобный ноль. Автоматического retention наблюдений пока нет — следите за ростом БД. Семантика и пределы — [ADR-037](docs/decisions/ADR-037-observed-analytics.md).

## Долгое нахождение и экспорт (M11)

Непрерывное наблюдение человека внутри danger zone **дольше10с** даёт одно `PERSON_LOITERING_IN_DANGER_ZONE` на подтверждённый визит, warning по умолчанию. Настройки камеры → «Порог долгого нахождения» (пусто = API default `LOITERING_THRESHOLD_SECONDS=10`); worker `SEVERITY_LOITERING=warning`. Подтверждение входа входит в длительность. Любой наблюдаемый выход/LOST/gap>2с сбрасывает непрерывный таймер; короткий выход в пределах grace не перевооружает уже сработавший визит. Новый alarm возможен после подтверждённого выхода и повторного захода. Это правило наблюдений, не физическая идентификация.

«События» → камера / статус / тип / период → **«Скачать CSV»**. Выгружаются все сохранённые строки по фильтрам, не только загруженная страница; live-pending не включены. Всё время либо фиксированные1ч/24ч/7д, «Обновить период» сдвигает окно. CSV UTF-8 BOM, comma/CRLF, UTC ISO8601, quoted multiline fields, mitigation формул префиксом апострофа. Лимит50000 строк/20МиБ: при превышении422 с предложением сузить фильтры, **без молчаливого обрезания**. При отказе БД503/JSON, не файл ошибки. Семантика/ограничения — [ADR-038](docs/decisions/ADR-038-loitering-csv.md).

## Производительность M12

`GET http://localhost:8001/metrics` — worker-local Prometheus, без PG/Redis I/O на scrape; только доверенная сеть. Whole-call detector latency отдельно от прежнего amortized inference_ms; local frame latency — monotonic capture handoff→delivery, не sensor-to-browser. FPS/capture buffer/outbox depth/active tracks/health/CPU/RSS — [docs/metrics.md](docs/metrics.md).

`uv run python benchmarks/pipeline.py --source /path/to/video.mp4 --cameras 8 --threads 2 --batch 4 --duration 20 --out /tmp/benchmark-8` — isolated pipeline, no storage I/O; не менять label/clip/железо при сравнении. Выводит meta+frames/batches/samples JSONL; повторный completed out не перезаписывает. Для native Windows заменить пути. Exact runtime QA MP4 не вложен, source SHA есть в raw meta.

INFERENCE_THREADS теперь восстанавливается после Ultralytics predictor warmup. Старое значение2 фактически могло быть перезаписано library default1: это исправление может повысить CPU consumption. Не применять tuning вслепую. INFERENCE_BATCH_SIZE4 и maxwait20 сохранены; если все RUNNING камеры уже в batch, лишнее ожидание не выполняется.
