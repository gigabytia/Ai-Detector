# M13 → M14: воспроизводимый локальный запуск

База — полный M13 c76adca; настоящая Git-история и проверенные веса сохранены. Автор нового commit — Kostya. Новых DB миграций и model/runtime replacement нет; Alembic head b6b7cfcd87c5.

1. Backup БД/Redis/файлов/своего .env; остановить старые app processes. Не удалять Docker volumes.
2. Обновить исходники, **сохранить рабочие .env и data/uploads/snapshots**. Для новой папки перенести их осознанно. Свои Git-коммиты сохранить отдельно; не заменять .git, если она содержит собственную историю.
3. В корне Windows-проекта выполнить `start.cmd`. Нужны поддерживаемый Node, uv и запущенный Docker Desktop/Compose. См. START_WINDOWS.md. Скрипт создаёт .env только при отсутствии, с random token, существующий файл оставляет побайтно.
4. Frontend lint trio pinned14.9.0/10.12.0/10.11.1 + coherent lock, npm ci, preinstall guard и engine-strict. Не делать individual downgrade/force/legacy peer bypass. Известные dev-only advisories не объявлены исправленными.
5. REDIS_URL в шаблоне/defaults API/worker —127.0.0.1; container Redis hostname не менялся. Preflight проверяет реальные локальные PG/Redis до миграции/запуска, не маскирует отсутствие серверов как успех.
6. Свои процессы Ctrl+C завершает, БД/Redis и существующие записи/файлы не удаляет. Посмотреть readiness/UI/логи и свои камеры. Empty DB получает только явно демо mock cameras; при любых существующих cameras automatic seed не выполняется.

Public production NO-GO M13 сохраняется: auth, target capacity/real RTSP/GPU/24h/containers/Windows acceptance, durability/retention/licensing. M14 улучшает воспроизводимость старта, не снимает эти gates. Windows-native/.cmd/Docker execution в QA не заявлено.
