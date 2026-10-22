# Обновление M6 → M7

Архив содержит полный репозиторий с `.git`, исходную историю M4/M5/M6, M7, веса модели, QA и документацию. `.env`, `.venv`, node_modules и runtime data не включены. Не заменяйте локальные данные/БД и не стирайте свой `.env`.

1. Сохранить локальные изменения, сделать backup PostgreSQL и Redis/AOF, остановить API и worker.
2. Распаковать в новую папку. `git status`, `git log -4`, `git fsck --full` должны читать историю. Не делайте `git init`: полноценная `.git` уже есть. Для текущего clone используйте `git fetch <путь к распакованному репозиторию> master` и обычный merge/ff после проверки ветки.
3. Перенести свой `.env`. На Windows host PostgreSQL по-прежнему `127.0.0.1:15432`; внутри Docker `postgres:5432`. Пути UPLOAD_PATH/модели сохранить. Новых обязательных env нет.
4. `uv sync --frozen`, `npm --prefix frontend ci`. Использовать поддерживаемый Node из package.json; sandbox 24.14.1 был ниже engine.
5. Поднять PostgreSQL/Redis. `uv run alembic -c backend/alembic.ini upgrade head`: новая миграция `14d6499b16a2`, таблица events. Камеры/зоны остаются. Downgrade удаляет events, поэтому не использовать его на рабочей истории без backup.
6. Запустить API, worker и frontend обычными командами README. Для демо `uv run ai-detector-seed` (идемпотентно), подождать цикл mock-сценария до ~15 с. События создаёт настоящий rule pipeline, не фиктивный seed insert.
7. Проверить «События», ACK/ложную тревогу/заметку и фокус камеры с телеметрией. Snapshot и event detail с изображением — M8, пока не реализованы.

## Гарантии и мониторинг

После XADD сообщения ждут ingest; ACK/XDEL только после PostgreSQL commit, UUID исключает повторную вставку и не затирает операторские поля. До XADD RAM-outbox ограничен и не переживает падение worker. AOF everysec не гарантирует zero-loss при аварии Redis/хоста. Входной Stream не trim-ится, при длительном отказе БД растёт. Контролировать XLEN/XPENDING, память/диск/dead letter/readiness, использовать noeviction и backup. Не добавлять другую durable consumer group без пересмотра XDEL.

`make check` — безопасные unit/frontend проверки. Интеграционные тесты только на отдельной тестовой БД: они очищают таблицы, а test_events — Redis DB 13. Оставить порты доступными только в доверенной локальной сети: авторизации ещё нет. Полные результаты/ограничения — PROGRESS.md и docs/qa/m7/README.md.
