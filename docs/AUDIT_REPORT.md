# Финальный доступный аудит — Milestone 13

Дата стенда: 2026-10-22. База M12 `ac41f76`; изменения M13 проверены до commit, source hashes сохранены в QA. Автор commit — Kostya; исходная настоящая Git-история сохранена. Это инженерный аудит доступной локальной среды, **не сертификация, не гарантия отсутствия дефектов и не полный pentest**.

## Решение

**Локальная доверенная среда: проверенные gates пройдены после исправлений. Public/shared production: NO-GO.** Серьёзные воспроизводимые дефекты, обнаруженные этим аудитом, устранены и закрыты регрессиями. Нерешённые production blockers перечислены ниже; их нельзя считать исправленными ограничением портов. Требуется отдельный приёмочный прогон на целевом оборудовании.

## Охват и границы

Linux, Python3.12.15, Node24.15.0,2 logical CPU, RAM~4GiB, PostgreSQL17, Valkey (Redis-compatible). Реальные YOLO26n/ByteTrack, API/FastAPI, Streams/pubsub/SSE, WS preview, JPEG, CSV, PostgreSQL analytics. Источник — зацикленная **статичная** bus MP4810×1080/15FPS, не движущееся CCTV и не реальная RTSP. SHA-256 `bc961607210ec3bd0c98c0c8207c9609ef229833af31381a1a0952c11a796e5a`. Вес модели имеет проверенный SHA в THIRD_PARTY_NOTICES.md. Runtime MP4 не включён; повторные замеры требуют тех же bytes/host/settings.

Проверялись затронутые resource/lifecycle/transaction пути, input/path validation, scopes token/origin, event/analytics retry+idempotency, capture/scheduler и shutdown, storage/retention semantics, HTTP contracts, миграции, зависимости, deploy defaults и лицензии. Регрессии прежних модулей входят в suite; это не означает покрытие каждой ветки, каждого браузера или каждого типа отказа. Integration/live используют разные Redis **instances**: logical DB не изолирует Pub/Sub.

## Найдено и исправлено

| Приоритет | Дефект / риск | Исправление и подтверждение |
|---|---|---|
| High | Race camera quota:12 concurrent create при max3 создавали8 камер | Transaction advisory lock перед count/insert; повтор ровно3 успешных, остальные422; интеграционная регрессия |
| High | Multipart parser мог заполнить temp disk раньше file limit | ASGI whole-body cap file+1MiB для declared/chunked, закрытие partial spools; independent file cap, CORS/413 unit tests |
| High | CSV ограничивал готовый результат, но сначала материализовал все rows; не было export concurrency gate | Один server-side cursor,100-row batches, incremental caps,2 exports/process; реальные50000/50001 rows/20MiB и3 concurrent requests |
| High | Снимки терялись при штатных burst: в preliminary run1008 JPEG на3552 alarms |32-job/128MiB conservative raw-frame budget,2 threads, busy/failed metrics; unit burst32 и byte cap; финальный run каждый event имеет metadata/JPEG |
| High | Advisory scan:25 известных Python findings в certifi/Pillow | frozen certifi2026.10.19/Pillow13.0.0 + security constraints; повторный scan без известных findings в проверенных packages,2 local CPU packages skipped |
| High deployment | Нет owner директории snapshot в fresh container, default nginx upload1MiB, unauth ports на всех интерфейсах | Создание/chown data dirs до UID10001, nginx2049m, loopback-only publishes; **только static validation**, Docker daemon недоступен |
| Medium | Пустой source update игнорировался; нестроковые cursor components/internal non-ASCII token могли дать500 | Явные проверки/корректные422/401, тесты; snapshot metadata DB outage теперь503 |
| Low | Невалидная proxy error shape или запрещённый localStorage могли ломать UI error handling/theme | Defensive parsing и storage fallback;5 новых frontend tests и production browser smoke |

Advisory count — результат установленного сканера, не независимое подтверждение эксплуатации. Повышение snapshot budget не гарантирует снимок при произвольной перегрузке: alarm без JPEG остаётся допустимым fallback.

## Автоматические gates

- **265 Python unit +46 PostgreSQL/Valkey integration +134 frontend tests: PASS.** База до исправлений254/41/129.
- Ruff/check+format178 Python files; strict mypy176 source files; ESLint, Prettier, vue-tsc, production Vite build: PASS.
- Frozen lock, generated OpenAPI JSON/TS parity: PASS. API response schema не менялась; новые ограничения/ошибки описаны в docs/api.md. Alembic head `b6b7cfcd87c5`; M13 migration нет.
- Только пустая выделенная test DB: upgrade head → downgrade base → upgrade head, `alembic check`: PASS. Никакая production DB не откатывалась.
- npm production audit:0 findings. Full dev tree:4 high advisory nodes в lint-only braces chain, **не исправлены**, см. blockers.
- pip-audit:0 known findings среди просканированных зависимостей после update; torch2.14.1+cpu и torchvision0.29.1+cpu не найдены в PyPI advisory lookup и skipped. Это не «все зависимости безопасны».
- Heuristic secret scan: current tracked text≤2MiB, exact .env-path history и HTTP remotes — без findings. Не полный entropy/all-history secret audit; private QA env не включён.
- Compose YAML/loopback bindings/data-dir-before-USER/nginx cap: static PASS, не container runtime PASS.

## Живая проверка полного pipeline

Сначала15с прогрев каждого этапа, затем4 камеры180с и8 камер300с. Включены настоящие preview consumers каждого потока, SSE и analytics probes примерно каждые5с, snapshots и persist. Жёсткая цель10FPS на каждую камеру **не достигнута**; DEGRADED под CPU saturation ожидаем и не скрываем. Это один последовательный run, не throughput SLA/производственное 24/7 испытание. FPS/CPU/RSS диагностические данные и независимая арифметика — `qa/m13/evidence.json`; не заявляется ускорение относительно M12.

- Pipeline errors0; bounded event/analytics outbox drops0 в измеренных окнах. Snapshot writer до outage: written=4448, busy=0, failed=0.
- После controlled shutdown: **4832 events = 4832 snapshots**, 3612 observations, 2416 completed track sessions. Это записи треков внутри camera/run, **не уникальные физические люди**.
- Fixed half-open UTC period: SQL ID set = complete CSV ID set без дублей = dashboard total (**4832** events). SSE checked against persisted IDs. WS JPEG/header validation каждого потока: 7353 packets за измерения.
- Redis outage15с: 15 успешных metrics scrapes, analytics RAM queue peak183.0, обработка продолжалась; recovery/drain PASS.
- PostgreSQL outage15с: CSV503 без attachment и analytics503 вместо ложных нулей; 128 pending event UUID сохранены после восстановления, выбранный snapshot UUID/JPEG SHA-256 тот же. Оба Streams догнаны до0.
- SIGTERM с8 активными камерами: worker1.21с, 32 новых финальных sessions; runtime status/heartbeat keys убраны, Streams0, JPEG доступны после stop. API с открытым SSE3.21с.

Последовательные прошлые попытки не смешаны с final raw: ранний full run не проверял корректный preview framing; следующий75с attempt прервался на idle keep-alive boundary httpx/uvicorn, при живых API/worker и без matching endpoint error. В final harness keepalive_expiry2с ниже server idle5с. Эти retries/исходные ограничения описаны PLAN.md; они не объявлены успешным soak.

## Реальный CSV stress

50000 unique rows →200, 11139098 bytes, 1.78с на стенде. Три одновременных exports →200/200/503;50001 row и реальное превышение20MiB →422 без partial attachment. Sampled API RSS baseline/peak в proof; это не RSS hard limit. Snapshot DB outage →503. Existing quoting/UTF8 BOM/19-column/formula mitigation сохранены; native Excel не сертифицировался.

## Browser production smoke

Собранный production frontend через local vite preview, API/WS proxies.7 маршрутов ×1280/390px ×light/dark = **28 layout checks**, horizontal overflow≤1px, 0 pageerrors, preview WS, CSV download, export503/error и analytics503/retry, blocked-storage render: PASS. Скриншоты приложены в QA, но image-view helper недоступен: **не заявлена экспертная визуальная оценка изображений**. Первые Vite dev попытки заменены production smoke, см. PLAN.

## Cold backup / restore drill

После остановки writers и drain: pg_dump → fresh isolated DB, отдельная копия всех referenced JPEG и uploads, сравнение row counts **всех public tables** и SHA-256 всех файлов. PASS: 4832 JPEG, 4 upload files; restored API5 JPEG + CSV/dashboard totals проверены. Redis AOF failover, live online backup/HA, remote disk loss и RTO/RPO этим не проверялись. Dumps/images/private env не включены в source archive, только proofs и manifest digest.

## Открытые production blockers и остаточные риски

1. **Блокер: operator auth/RBAC отсутствуют** на REST/SSE/WS/snapshots/metrics. Trusted localhost only; перед public/shared deployment — coordinated auth или протестированный TLS/auth gateway для всех протоколов. CORS и UUID не access control. Internal token отдельный, заменить example.
2. **Блокер при требовании10FPS/camera:** текущих2 CPU недостаточно для4/8 потоков с этим полным pipeline; требуется измерение target CPU/GPU, не косметическое изменение target FPS. Real RTSP/network reconnect, GPU/CUDA/VRAM, Windows, Docker/CI, moving-person precision/recall и24h soak **не проверены**.
3. **Durability:** RAM outbox/crash/full queues/AOF everysec имеют loss windows; files/DB не distributed transaction; crash незавершённых tracks теряет sessions; SSE без replay, REST — восстановление истории. Controlled outages не доказывают crash-proof delivery.
4. **Capacity/operations:** samples/sessions без automatic retention/rollup, uploads без automatic orphan cleanup/quota, event backlog может расти. Нужны disk budgets/alerts, Stream/pending/dead-letter monitoring и backup policy.32 jobs/128MiB — не total worker RSS cap,2 CSV slots — per API process, не глобальный предел.
5. **Dependency gap:**4 high dev advisory nodes (@vue/eslint-config-typescript→fast-glob→micromatch→braces, GHSA-vfj7-8cjw-p6xm). Installed/latest braces3.0.3 без patched release на момент проверки; npm предлагает downgrade eslint config, не безопасный patch, поэтому не применён. Trusted source/globs only. Torch CPU wheels/native OpenCV codecs/container OS требуют отдельного scan.
6. **Licensing:** Ultralytics/weights AGPL-3.0; THIRD_PARTY_NOTICES и upstream license приложены, но это не юридическое заключение/полный SBOM. Перед распространением/production согласовать способ исполнения obligations/enterprise license и лицензию собственного кода.
7. Не блокирующие локальный build warnings: lazy ECharts~557kB/~189kB gzip, Starlette TestClient/httpx deprecation. Не скрыты и не объявлены ошибками сборки.

## Следующий приёмочный шаг

Закрыть auth/deployment/licensing gates; на целевом host собрать контейнеры с пустыми и существующими volumes, проверить permissions/upload/WS/SSE через gateway; подключить реальные RTSP/GPU и провести не менее24ч soak с заранее заданными FPS/latency/durability/RTO criteria. До этого итог — **проверенный локальный build, не production-ready система**. Порядок обновления: UPDATE_MILESTONE_13.md.
