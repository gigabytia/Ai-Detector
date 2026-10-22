# Обновление M7 → M8

Полный архив включает настоящую `.git`, всю цепочку истории до M8, исходники, веса и QA. `.env`, `.venv`, node_modules, uploads/snapshots/runtime data не включены. Не перезаписывать свои данные.

1. Сохранить изменения и backup PostgreSQL/Redis/AOF/файлов; остановить API и worker. Распаковать в новую папку, проверить `git status`, `git log -5`, `git fsck --full`. Не делать git init — история уже внутри. Для существующего clone можно fetch из распакованного репозитория и выполнить обычный merge/ff.
2. Перенести свой .env, настроить **одинаковый SNAPSHOT_PATH** API/worker (по умолчанию data/snapshots). Директория private, writable worker/API cleanup. В compose добавлен общий snapshots volume; не подменять/удалять существующие volumes. На разных хостах нужен общий mount. API defaults: SNAPSHOT_ENABLED=true, SNAPSHOT_RETENTION_DAYS=30, SNAPSHOT_CLEANUP_INTERVAL_SECONDS=3600. По камере есть inherit/on/off. Для отключения default поставить false; явные camera overrides его переопределяют.
3. `uv sync --frozen`, `npm --prefix frontend ci` на поддерживаемом Node (см. package.json). Windows PostgreSQL host по-прежнему 127.0.0.1:15432, внутри compose postgres:5432.
4. `uv run alembic -c backend/alembic.ini upgrade head`. Новая 48f1a410c0ce добавляет snapshots и nullable config column, старые events сохраняются без изображений. Не применять downgrade на рабочей БД: он удаляет metadata снимков/override. Файлы миграция не удаляет.
5. Запустить API/worker/frontend как в README. Открыть журнал → детали нового события: исходный кадр, рамка toggle, заметка. Старое событие/disabled/expired image показывает заглушку, а не ошибку всей истории. Снимок необязателен — отказ диска/очереди не отменяет тревогу.
6. Проверить общий mount и чтение JPEG API, свободное место/логи retention. Очистка удаляет только снимки и metadata, не events. Сохранять файлы и DB backup согласованно. Redis consumer/ingest/AOF ограничения M7 остаются.

`make check` безопасен; integration только на выделенной тестовой БД/Redis (очищает таблицы и DB13). Fault scripts реально останавливают сервисы. Авторизации нет: использовать только доверенную сеть/reverse proxy. Полные результаты и границы — PROGRESS.md и docs/qa/m8/README.md. Следующий этап — M9 (линия/crossing), не dashboard/analytics.
