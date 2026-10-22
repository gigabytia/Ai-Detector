# Разработка

## Что нужно

| Инструмент | Версия | Зачем |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.12+ | Python 3.12 и зависимости (ставит Python сам) |
| Node.js | 22.22+ или 24.15+ | frontend |
| Docker Desktop | любой актуальный | PostgreSQL и Redis (минимум) |

`make` не обязателен: у каждой команды есть эквивалент для PowerShell. Команды одинаковые в PowerShell, bash и cmd, кроме копирования файла.

## Первый запуск без Docker для приложений (Windows и Linux)

```powershell
Copy-Item .env.example .env          # bash: cp .env.example .env
uv sync
npm --prefix frontend ci
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
uv run ai-detector-seed              # две демо-камеры (mock), повторный запуск ничего не дублирует
```

API и worker должны знать один и тот же `WORKER_API_TOKEN` (в `.env.example` — dev-значение; вне локальной машины замените на случайное). Без токена worker не получит список камер, а API ответит на внутренние запросы `503`.

Затем в трёх терминалах:

```powershell
uv run ai-detector-api               # http://localhost:8000/docs
uv run ai-detector-worker            # http://localhost:8001/health/ready
npm --prefix frontend run dev        # http://localhost:5173
```

Откройте http://localhost:5173/settings: база данных и Redis — «Доступно», в «Обработчики видео» — ваш `WORKER_ID`. На http://localhost:5173/monitoring демо-камеры через 1–2 с переходят в «В работе».

В Docker seed запускается вручную: `docker compose exec api ai-detector-seed`.

## Пример видео (§108)

Видео в git не хранятся (`data/` в `.gitignore`). Подойдёт любой локальный `.mp4`/`.mov`/`.mkv`/`.avi`: «Камеры» → «Добавить камеру» → «Видеофайл». Файл загружается в `UPLOAD_PATH` и воспроизводится по кругу в реальном темпе. Для проверки детекции людей (с Milestone 4) нужна запись, где в кадре есть люди. Для проверки только захвата достаточно тестовой таблицы:

```powershell
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=25 -t 30 -pix_fmt yuv420p sample.mp4
```

## Проверка RTSP без камеры

```powershell
docker compose --profile media up -d mediamtx
ffmpeg -re -f lavfi -i testsrc2=size=1280x720:rate=25 -c:v libx264 -preset ultrafast -tune zerolatency -g 25 -f rtsp rtsp://localhost:8554/cam1
```

Добавьте камеру `rtsp://localhost:8554/cam1` (из контейнера worker'а — `rtsp://mediamtx:8554/cam1`). Если остановить ffmpeg или MediaMTX, камера перейдёт в «Недоступна» и вернётся в «В работе» после восстановления потока. Публикация файла через `-re -stream_loop -1 -i file.mp4` после первого круга может отдавать кадры быстрее реального времени (особенность ffmpeg) — для замеров FPS используйте `lavfi`.

## Полностью в Docker

```powershell
docker compose up --build            # frontend: http://localhost:8080
docker compose --profile media up    # + MediaMTX (Уровень 3)
```

## Команды

| make | PowerShell / любой shell |
|---|---|
| `make install` | `uv sync; npm --prefix frontend ci` |
| `make infra` | `docker compose up -d postgres redis` |
| `make up` / `make down` | `docker compose up --build` / `docker compose down` |
| `make migrate` | `uv run alembic -c backend/alembic.ini upgrade head` |
| `make seed` | `uv run ai-detector-seed` |
| `make api` | `uv run ai-detector-api` |
| `make worker` | `uv run ai-detector-worker` |
| `make frontend` | `npm --prefix frontend run dev` |
| `make test` | `uv run pytest; npm --prefix frontend test` |
| `make test-integration` | `uv run pytest -m integration` (нужны запущенные PostgreSQL и Redis) |
| `make lint` | `uv run ruff check .; uv run ruff format --check .; uv run mypy shared/src backend/src vision-worker/src tests; npm --prefix frontend run lint; npm --prefix frontend run format:check; npm --prefix frontend run typecheck` |
| `make fmt` | `uv run ruff check --fix .; uv run ruff format .; npm --prefix frontend run format` |
| `make api-types` | `uv run ai-detector-openapi frontend/openapi.json; npm --prefix frontend run api:types` |
| `make build` | `npm --prefix frontend run build` |

## Контракт API

После изменения схем backend выполните `make api-types` и закоммитьте `frontend/openapi.json` и `frontend/src/api/generated.ts`. CI падает, если они устарели ([ADR-018](decisions/ADR-018-frontend-api-types.md)).

## Тесты

* `tests/unit` — без внешних сервисов, запускаются по умолчанию.
* `tests/integration` — реальные PostgreSQL и Redis по `DATABASE_URL` / `REDIS_URL`; перед запуском нужен `make migrate`. Тесты камер очищают таблицу `cameras` — не запускайте их на базе с нужными данными. Если сервис недоступен, тест **падает**, а не пропускается.
* `frontend/src/**/*.test.ts` — Vitest.

## Миграции

```powershell
uv run alembic -c backend/alembic.ini revision --autogenerate -m "create cameras"
uv run alembic -c backend/alembic.ini upgrade head
```
Имена миграций — на английском.


## Milestone 4: модель и превью

После `uv sync` подготовьте модель: `uv run ai-detector-model` (PowerShell и bash) или `make model`. Команда сверяет SHA-256 из `models/person-detector/manifest.yaml`, записывает временный файл и атомарно заменяет веса. Если веса уже включены в полученный архив, повторная загрузка не обязательна. Worker всегда проверяет их перед запуском, выполняет warmup и завершает работу с кодом 1 при ошибке; автоматического скачивания на старте нет. `INFERENCE_DEVICE=auto` выбирает CUDA только при наличии соответствующей сборки и устройства, иначе CPU. Текущий lock устанавливает CPU PyTorch на Linux/Windows (ADR-030).

Примените миграцию `uv run alembic -c backend/alembic.ini upgrade head`, запустите API, worker и frontend по обычным командам. На «Мониторинге» теперь видно видео; нажмите плитку для крупного просмотра. В «Детекция людей» задайте целевую частоту 1–30 и порог >0…1. Пустые поля наследуют умолчания API. «Сбросить поля» лишь очищает форму — для записи нужен «Сохранить».

Docker: каталог `./models` монтируется в worker read-only. Подготовьте веса на хосте, затем `docker compose up --build`. За reverse proxy используйте same-origin `/live/`, убедитесь, что WebSocket Upgrade не удаляется. При отдельном origin добавьте его в JSON-массив `PREVIEW_ALLOWED_ORIGINS`; не отключайте проверку для публичного доступа. Стенд не имеет авторизации оператора и не предназначен для открытого Интернета.

Новые unit-тесты не скачивают модель, не требуют GPU/сети. Проверка настоящей модели выполняется отдельно на предоставленном видео либо `ultralytics/assets/bus.jpg`; это smoke-тест наличия person-боксов, не оценка качества на вашем наборе данных. Интеграционные тесты по-прежнему требуют PostgreSQL и Redis и не пропускаются при отсутствии сервисов.


## Проверка трекинга (Milestone 5)

Отдельных сервисов/команд для трекера нет: запускается в существующем worker. После обновления зависимостей (`uv sync`) порядок запуска прежний. Параметры `.env`: `PERSON_TRACK_MAX_AGE=25`, `TRACK_MATCH_IOU=0.5`, `TRACK_ACTIVATION_CONFIDENCE=0.25`; их смена требует перезапуска worker. Камерные FPS/confidence по-прежнему меняются горячо в UI.

Детерминированные тесты готового ByteTrack без весов и сервисов (PowerShell и bash одинаково):

```sh
uv run pytest tests/unit/worker/test_tracking.py tests/unit/worker/test_camera_session.py tests/unit/worker/test_detection.py
npm --prefix frontend test
```

Для ручной проверки: запустить mock/file, открыть «Мониторинг» или focus. После подтверждения появляются `Человек #ID`; между соседними наблюдениями ID сохраняется. При цикле видео ID меняется, run сохраняется; после restart ID может снова начинаться с 1, потому что run новый. Это не уникальные посетители и не межкамерное распознавание. Подробности — [ADR-032](decisions/ADR-032-bytetrack-runtime.md).

Исходники закреплены с LF в `.gitattributes`, чтобы Prettier не падал после Windows checkout из-за CRLF. Это не изменение поведения приложения.

## Проверка опасной зоны (Milestone 6)

1. Сохраните свой `.env` и БД. Выполните `uv sync`, `npm --prefix frontend ci`, запустите PostgreSQL/Redis и `uv run alembic -c backend/alembic.ini upgrade head` (новая миграция c631d038af01). Не копируйте .env.example поверх своего файла при обычном обновлении.
2. В `.env` при необходимости добавьте `ZONE_ENTER_DWELL_SECONDS=0.25`, `ZONE_EXIT_GRACE_SECONDS=0.5`, `EVENT_COOLDOWN_SECONDS=3` (API), `EVENT_MIN_TRACK_HITS=3`, `SEVERITY_ZONE_ENTER=critical` (worker). Без записей используются эти defaults. API и worker запускаются как раньше, отдельного сервиса правил нет.
3. `uv run ai-detector-seed` создаёт две mock-камеры и по одному примеру зоны, если у seed-камеры нет зон. Повторный запуск не дублирует камеры/зоны и не перезаписывает существующую геометрию. Удалённая seed-зона при повторном seed появится снова. События seed не имитирует.
4. В крупном просмотре измените зону кликами на изображении либо координатами 0..1 и сохраните. Чёрные полосы не принимают точки. Проверьте cancel, undo, off/on и delete с подтверждением. При входе нижней точки bbox после dwell рамка станет красной; в JSON-логе worker появится PERSON_ENTERED_DANGER_ZONE один раз за визит. Изменение зоны не меняет run/ID.
5. Историческая граница M6: история/подтверждение тогда отсутствовали. С M7 Redis event bus/SSE/история/ACK/FP реализованы; снимки — M8. См. проверки ниже.

Автоматические проверки: `make check`, затем на отдельной тестовой БД `make test-integration` (тесты очищают cameras/configs/zones). `alembic check` сверяет модель и миграции. Проверка downgrade проводилась только на тестовой БД; в рабочей среде downgrade удалит зоны.

## Проверка M7

1. Остановить приложения перед миграцией, `uv run alembic -c backend/alembic.ini upgrade head`, затем обычный запуск API/worker/frontend. `make seed` создаёт 2 mock-камеры/зоны; после запуска worker реальные правила генерируют демо-тревоги за один цикл сценария (до ~15 с).
2. Открыть «События»: NEW, камера/статус, «Подтвердить»/«Ложная тревога», заметка; после reload поля сохраняются. Focus камеры показывает отдельную телеметрию.
3. Только на тестовой инфраструктуре: приостановить PostgreSQL, не Redis. Live event приходит; PATCH ещё не записанного события → 409, в Redis Stream растёт pending. Вернуть PostgreSQL — ingest сохраняет UUID и освобождает backlog. Повторная доставка не стирает статус/заметку.
4. Отказ Redis: обработка кадров продолжается; worker readiness 503, bounded RAM-outbox повторяет доставку. После восстановления сравнить UUID в логе с историей. Не завершать worker при таком тесте, если нужно сохранить RAM-очередь. AOF everysec не является zero-loss гарантией.
5. `make check`, затем `make test-integration`. Интеграционные тесты **трут тестовые таблицы**; test_events дополнительно очищает выделенную Redis DB 13. Никогда не запускайте их на рабочей БД/Redis DB 13 с полезными данными.

Диагностика: `XLEN ad:ingest`, `XPENDING ad:ingest api-ingest`, `XLEN ad:ingest:dead`, health API (`event_delivery`)/worker. Входной Stream не обрезается: контролировать память/диск. Bounded UI хранит только последние live alarms, полная история — REST pagination. При добавлении второго durable consumer group нельзя сохранять текущий XDEL после единственного ACK. [ADR-034](decisions/ADR-034-event-delivery-realtime.md).
