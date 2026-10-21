# AI Detector v2

Система видеонаблюдения: детекция и трекинг **людей**, события входа в опасную зону, пересечения линии и долгого нахождения в зоне, интерфейс оператора.

**Статус:** Milestone 5 завершён — YOLO person detection и ByteTrack, стабильные ID в пределах камеры/run, восстановление после временной потери и удаление просроченных треков, live canvas с ID. Зоны и события — следующие этапы. Подробности — [PROGRESS.md](PROGRESS.md).

## Архитектура

Frontend (Vue 3) ↔ API (FastAPI) ↔ PostgreSQL / Redis ↔ Vision worker. Inference — только в worker'е. Подробно: [architecture.md](docs/architecture.md), [data-flow.md](docs/data-flow.md), [database.md](docs/database.md), [behavior.md](docs/behavior.md), [решения](docs/decisions/README.md).

## Быстрый старт

```powershell
Copy-Item .env.example .env        # bash: cp .env.example .env
uv sync; npm --prefix frontend ci
uv run ai-detector-model           # скачать и проверить веса; можно не выполнять, если веса уже есть
docker compose up -d postgres redis
uv run alembic -c backend/alembic.ini upgrade head
uv run ai-detector-seed           # демо-камеры
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

Стенд предназначен для локальной доверенной сети: аутентификации оператора пока нет. Не выставляйте API/worker напрямую в Интернет. Исходный `AI_DETECTOR_v2_MASTER_PROMPT.md` не входил в присланный архив; восстановление опирается на сохранённые архитектурные документы и контекст сессии.
