# QA Milestone 5

Проверены unit/integration тесты, статический анализ, сборка и живой путь YOLO → ByteTrack → атомарный JPEG/JSON → canvas. Условия, результаты и ограничения — в [PROGRESS.md](../../../PROGRESS.md#milestone-5--результат-текущей-сессии).

* `checks.txt` — полный вывод `make check`, без ANSI-разметки.
* `runtime.txt` — вывод live smoke, горячих настроек/restart, браузера и SIGTERM.
* `monitoring.png`, `focus.png`, `mobile.png`, `mobile-dark.png` — автоматические скриншоты локального Chromium. Утилита просмотра изображений в песочнице вернула инфраструктурную ошибку; визуальная оценка скриншотов через неё не выполнялась. Canvas, реальные подписи, JS-ошибки и overflow проверялись браузерными assertions.

Реальный MP4 собран из статичного официального Ultralytics bus.jpg (180 кадров, 15 FPS); предназначен для интеграционного smoke, не для оценки трекинга на CCTV. Движение и пропуски проверены готовым ByteTrack на детерминированных наблюдениях и mock-сценариях.

Команды (PowerShell и bash):

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy shared/src backend/src vision-worker/src tests
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```

Интеграционные тесты требуют PostgreSQL/Redis и настройки DATABASE_URL/REDIS_URL: `uv run alembic -c backend/alembic.ini upgrade head`, затем `uv run pytest -m integration`. Новых миграций в M5 нет.
