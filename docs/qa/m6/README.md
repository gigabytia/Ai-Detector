# Milestone 6 — проверки

## Повторная проверка M5

Оригинальный архив M5 восстановлен из сохранённой копии, восстановлен исходный commit 8e0e842 (Kostya), а не повторная реализация. До правок M6 повторён make check: 122 Python unit, 64 frontend, ruff/format, mypy strict (120 файлов), ESLint, Prettier, vue-tsc и production build. Лог — m5-recheck.txt. Прежние 11 integration входят в заключительные 15 integration M6.

## M6: автоматические проверки

* checks.txt: make check, 151 Python unit (15 integration исключены), 82 Vitest, mypy strict (132 файла), ruff/format, ESLint/Prettier/vue-tsc, production build.
* integration.txt: 15 passed на PostgreSQL 17.10 и Valkey 9.0.5. Геометрия/независимость камер/soft-delete/лимит зон/notify/spec/config проверены через настоящий API, PostgreSQL и Redis.
* schema.txt, migration-roundtrip.txt: создание с пустой БД, alembic check, downgrade на b452b4c88e6b и повторный upgrade. Все операции только на отдельной тестовой БД.
* uv lock --check — согласован; повторный экспорт OpenAPI побайтово совпал с frontend/openapi.json; npm audit --omit=dev — 0 уязвимостей; compose YAML распарсен, Docker не запускался.

## Живой путь (runtime.txt)

API + worker (CPU YOLO26n/ByteTrack) + две mock-камеры + Vite WS. Реальный файл — статичное официальное Ultralytics bus.jpg в MP4 из прежней QA, не движущееся CCTV. После подтверждения входа у 4 людей IN_DANGER_ZONE. Горячая смена polygon → NORMAL при тех же run/IDs; disable убирает zone из атомарного preview; re-enable возвращает danger без restart. В JSON-логе 4 уникальных события с UTC/source time и confidence; повтор в коротком визите подавлен cooldown. Длительная работа mock-сцен дала входы с исходными timestamps через тот же engine.

Seed выполнен дважды: созданы 2 камеры/2 зоны без дублей, существующая геометрия не перезаписана. Shutdown с открытым WS (shutdown.txt): socket закрыт, Redis runtime/heartbeat удалены за 0.82 с.

## Chromium (browser.json)

Настоящий UI и сервер, не мокап: monitoring/focus, рисование polygon кликами на portrait-видео, чёрные side bars не создают вершину, нормализованные координаты совпадают с заданными с допуском 0.005 (округление экранного пикселя), save через REST, cancel не записывает черновик. Перехвачены красные strokeRect и подписи Человек #ID. Ширина 390px, light/dark, нет pageerror или горизонтального overflow. Скриншоты PNG приложены.

Ограничение инструментов: image viewer песочницы не смог открыть PNG (computer_helper_failed), поэтому визуальная оценка скриншотов не заявляется. Проверки UI выполнены по DOM, геометрии, canvas instrumentation и ответам API.

## Среда и ограничения

Linux x86_64, Python 3.12.15, Node 24.14.1 (ниже engine, для работы нужен поддерживаемый Node), CPU. Docker/CI, Windows, GPU/CUDA, реальные RTSP/потери сети, движущиеся CCTV и нагрузка 4/8 камер здесь не проверены. Snapshot, линии/loitering, история/доставка событий/Redis Stream/SSE — не часть M6.
