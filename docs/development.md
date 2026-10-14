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
