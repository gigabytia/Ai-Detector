# Обновление M8 → M9

Полный архив содержит настоящую .git и историю M4 → M5 → M6 → M7 → M8 → M9, исходники, веса и QA. .env, окружения, node_modules и runtime data исключены. Не выполнять git init.

1. Backup PostgreSQL, Redis/AOF и файлов снимков; сохранить изменения/.env, остановить API/worker. Распаковать в новую папку; проверить git status, git log -6, git fsck --full. Существующий clone можно обновить fetch/ff из распакованного репозитория.
2. Перенести свой .env и mounts, не удалять volumes. Требуется PostgreSQL **UTF8** (SHOW server_encoding): JSONB содержит локализованные line_name. SQL_ASCII не подходит; миграция не конвертирует кодировку. Для старой SQL_ASCII БД нужен отдельный проверенный backup/restore в UTF8, не удаление данных на месте. В QA использована новая UTF8 копия; исходная база сохранена.
3. uv sync --frozen; npm --prefix frontend ci на поддерживаемом Node (^22.22.2 либо >=24.15.0 согласно package.json). Worker новые optional settings: LINE_HYSTERESIS=0.01 (0 < значение ≤0.1), SEVERITY_LINE_CROSS=warning. EVENT_MIN_TRACK_HITS и event_cooldown_seconds уже существуют. API/worker должны обновляться согласованно: старый worker новый тип не создаёт, старый API может его не принять.
4. uv run alembic -c backend/alembic.ini upgrade head. e2c6db45c9b8 добавляет lines и nullable events.line_id; прежние zones/events/snapshots сохраняются. Downgrade удаляет линии/ссылки, не способ обновления рабочей базы.
5. Запустить сервисы как в README. Focus камеры → «Линия пересечения» → P1 и P2 → сохранить. API разрешает16 линий, редактор меняет только первую. У линии два направления; стороны определяются относительно P1 → P2, а не экраном. Новая/изменённая линия сначала накапливает baseline, мгновенная тревога при сохранении не ожидается.
6. Проверить новое событие PERSON_CROSSED_LINE в SSE/истории и деталях. Если снимки включены — полный исходный JPEG с переключаемой исторической геометрией. Изменение/удаление линии не переписывает старые metadata. Snapshot необязателен; отказ картинки не отменяет тревогу.

Старые ограничения M7/M8 доставки, диска, retention, trusted-network/no-auth сохраняются. Integration очищает выделенную test DB/Redis13. Outage/shutdown scripts реально останавливают QA-сервисы, не запускать на production. Результаты — PROGRESS.md и docs/qa/m9/README.md. Следующий этап — M10, dashboard/статистика/таймлайн.
