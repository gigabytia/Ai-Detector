# Обновление M9 → M10

Архив содержит настоящую полную `.git` M4 → M5 → M6 → M7 → M8 → M9 → M10, исходники, веса и QA. `.env`, окружения, node_modules, uploads/snapshots/runtime data исключены. **Не выполнять git init** и не удалять рабочие volumes.

1. Сохранить свои изменения/.env; backup PostgreSQL, Redis/AOF, uploads и snapshots, остановить API/worker. Распаковать в новую папку; `git status`, `git log -7`, `git fsck --full`. Существующий clone можно обновить fetch/ff из распакованного репозитория.
2. Перенести настройки/mounts. PostgreSQL должен быть UTF8; миграция кодировку не конвертирует. Использовать поддерживаемый Node `^22.22.2 || >=24.15.0` (QA24.15.0), Python3.12. `uv sync --frozen`; `npm --prefix frontend ci` (новая зависимость ECharts).
3. `uv run alembic -c backend/alembic.ini upgrade head`. Новая `a9345caf81b1` добавляет camera_samples/track_sessions и indexes. M9 events/lines/zones/snapshots не удаляются. Downgrade уничтожает новые observations/sessions, это не способ обновления production.
4. Обновить и запустить API/worker согласованно. Новых обязательных env нет. Worker публикует `ad:analytics:ingest`; API создаёт consumer group `analytics-db`. Старый worker не даёт новые наблюдения; старый API их не сохраняет. Не удалять Stream при обновлении.
5. Открыть «Аналитика», дождаться нескольких наблюдений, выбрать камеру/период, нажать «Обновить период». Наблюдения начнутся после M10; исторические события доступны сразу. Timeline содержит только завершённые треки; для проверки остановить камеру и обновить страницу. TrackID — не физически уникальный человек.
6. Контролировать readiness API (analytics_ingest), worker analytics_ok/analytics_dropped, Stream backlog/dead letter и рост БД. Outbox ограничен1000; Redis/host failure имеет окно потери. Нет автоматического analytics retention/rollup — спланировать хранение, не удаляя таблицы вручную во время работы.

KPI: half-open UTC период [start,end), ≤31д; UI1ч/24ч/7д с ручным обновлением. False positives входят в total; denominator — все выбранные зарегистрированные камеры, включая архивные/нулевые. Live active cameras — сейчас, при недоступном Redis неизвестно, не0. Среднее/максимум people — последние 1Hz observations, не покадровый пик; пропуски неизвестны. Завершённые сессии при пересечении периода показываются целиком.

Integration очищает выделенную test DB и Redis13. Outage/shutdown QA скрипты останавливают QA-сервисы — не запускать на production. Ограничения и доказательства: PROGRESS.md, docs/qa/m10/README.md, ADR-037. Следующий — M11 (loitering и CSV).
