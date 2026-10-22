# Windows: запуск после распаковки

## Одна команда

Для NVIDIA см. **[GPU_WINDOWS.md](GPU_WINDOWS.md)**: первый запуск ` .\start.cmd --profile cuda `, затем выбор запоминается. Без выбранного профиля — CPU. Обычный launcher переопределяет INFERENCE_DEVICE только у своих процессов, не в .env.

Нужны **uv>=0.13.5**, поддерживаемый **Node.js** (`^22.22.2` либо `>=24.15.0`) и **запущенный Docker Desktop с Linux containers и современным Docker Compose v2**. Первый запуск требует Интернета для установки зависимостей/образов. Сам сценарий не устанавливает Docker/Node и не обходит их политики безопасности.

Откройте PowerShell **в корне Ai-Detector**, не в `frontend`:

```powershell
.\start.cmd
```

Когда появится `READY`, откройте **http://localhost:5173**. Терминал оставьте открытым. `Ctrl+C` завершает запущенные этим сценарием API/worker/frontend; PostgreSQL/Redis и их Docker volumes остаются. Приложение доступно только локально; авторизация оператора этим обновлением не добавляется.

### Что делает сценарий

1. Проверяет Node, согласованные версии ESLint/Vue config/plugin и lockfile, наличие uv/Docker Compose.
2. Если `.env` отсутствует — создаёт из `.env.example` и генерирует случайный внутренний worker token. **Существующий `.env` не изменяет** и не печатает его значения.
3. Выполняет `uv sync --frozen` с выбранной взаимоисключающей CPU/CUDA-группой и `npm ci --include=dev`. Проверяет версии/сборку PyTorch/torchvision и реальные matmul/NMS до запуска инфраструктуры. Подробности — GPU_WINDOWS.md.
4. Запускает **только postgres/redis** через Compose, ждёт container health, затем выполняет настоящий Redis PING и PostgreSQL SELECT1 по эффективным настройкам приложения.
5. Выполняет Alembic upgrade head и проверяет/при необходимости скачивает веса с SHA-проверкой. В M15 новой миграции нет.
6. Только если таблица камер **полностью пустая** и лимит≥2, создаёт две явно демонстрационные камеры и зоны. При существующих записях ничего не seed/reset/delete.
7. Запускает API → readiness → worker → readiness → frontend, проверяет открытие UI. Логи каждого сервиса: `data/dev-logs/<дата-время>/api.log`, `worker.log`, `frontend.log`. При ошибке одного процесса останавливает остальные свои процессы; чужие процессы не завершает.

## Обновление уже работающей установки

Сначала остановите старые API/worker/frontend и сделайте backup БД, Redis persistence, `.env`, `data/uploads` и `data/snapshots`.

- При распаковке в прежнюю папку **не удаляйте `.env` и `data`**. Они отсутствуют в архиве намеренно, не должны заменяться шаблоном.
- При распаковке в новую папку перенесите свой рабочий `.env` и нужные uploads/snapshots либо настройте пути к прежним каталогам. ZIP исходников не содержит ваших видео, JPEG или БД. Существующие записи камер в PostgreSQL сами по себе не восстанавливают файлы видео.
- Если есть собственные Git-коммиты/изменения, не заменяйте свою `.git` вслепую: сохраните их и обновляйте через Git отдельно. Архив содержит исходную историю проекта + M15, не историю вашего локального компьютера.
- Сценарий не вызывает `docker compose down -v`, не очищает БД и не заменяет существующий `.env`.

После этого:

```powershell
.\start.cmd
```

Повторная установка по lockfile выполняется намеренно, чтобы убрать локально изменённое дерево npm. Для уже проверенной неизменённой установки есть `--skip-install`.

## Режимы

```powershell
.\start.cmd --setup-only                 # подготовить/проверить/мигрировать без запуска приложений
.\start.cmd --skip-install               # не переустанавливать уже согласованные зависимости
.\start.cmd --no-infra                   # свои УЖЕ запущенные локальные PG/Redis, без Docker
.\start.cmd --no-infra --setup-only
```

`--no-infra` не эмулирует Redis и не игнорирует проверку подключения. Это локальный launcher, не менеджер remote/production deployment: remote DSN и публичные binds отвергаются без перезаписи настроек. Для иных deployment используйте существующие ручные команды и `docs/deployment.md`.

## Если снова не запускается

### ERESOLVE / предложения npm downgrade

Проверенная тройка: `@vue/eslint-config-typescript=14.9.0`, `eslint=10.12.0`, `eslint-plugin-vue=10.11.1`. Config14.9.0 поддерживает ESLint10/plugin10; config14.0.1 — другая несовместимая тройка.

Не выполняйте отдельный downgrade ESLint/config, `npm audit fix --force`, `--force` или `--legacy-peer-deps`. Если уже меняли package files — сначала сохраните их копии и восстановите **оба** `frontend/package.json` и `frontend/package-lock.json` из этого релиза, затем снова `start.cmd`. Preinstall guard отвергает известные несогласованные pins/bypass flags; `npm ci` использует versioned lockfile. Намеренное обновление требует согласованной проверки guard/lock/tests, а не обхода peer dependencies.

Четыре high-узла известного **dev-only** advisory braces остаются открытыми; это не причина применять автоматический breaking downgrade. Production npm audit проверяется отдельно. Блокировка install scripts в изменённом npm-дереве не должна обходиться массовым approve: сначала восстановите проверенный lock и изучите конкретный пакет.

### Redis timeout / readiness не проходит

Для процессов Windows вне контейнеров шаблон использует `REDIS_URL=redis://127.0.0.1:6379/0`, PostgreSQL — `127.0.0.1:15432`. Для контейнеров Compose по-прежнему использует имена `redis`/`postgres` внутри своей сети. Не меняйте container DSN на host loopback.

```powershell
docker compose ps
docker compose exec redis redis-cli ping
Test-NetConnection 127.0.0.1 -Port 6379
```

Ожидаются здоровые контейнеры, PONG и TcpTestSucceeded True. Если существующий `.env` содержит другой адрес/порт/пароль, сценарий не перезаписывает его — поправьте настройки локально. Системные environment variables имеют приоритет над `.env`: проверьте их, не публикуя значения с секретами. API/worker должны использовать одинаковый token и Redis. Не присылайте полный `.env` в чат.

### Port already in use

Остановите прежний экземпляр приложения. Сценарий не убивает неизвестный процесс ради освобождения порта. Frontend требует5173 (`--strictPort`), чтобы не уйти незаметно на порт вне CORS. Для API/worker используются порты `.env`; `API_BASE_URL` должен соответствовать API_PORT.

### Нет worker.log / сервис завершился

Логи создаются после успешных prerequisite/preflight/migration/model шагов. Если ошибка произошла раньше — причина в основном терминале. При ошибке во время запуска worker смотрите каталог, напечатанный как `Service logs:`; файл не нужно собирать вручную перенаправлением вывода другой команды.

## Проверка релиза и ограничения

Прямой Windows/.cmd/Docker Desktop прогон в Linux-стенде недоступен. Проверены Python orchestration и ветка Windows cleanup unit-тестами, Node guard и чистый npm ci; живой Linux native запуск с отдельными PG/Valkey, API/worker/frontend, демо/снимками, Ctrl+C и повторным setup. Это не новая Windows/RTSP/GPU/production сертификация. Доказательства — `docs/qa/m14/README.md`; ограничения M13 остаются в `docs/AUDIT_REPORT.md`.
