# База данных (PostgreSQL)

SQLAlchemy 2.x (async, asyncpg), миграции Alembic (имена на английском). Все `timestamptz` в UTC. UUID генерирует приложение (`uuid4`), для событий — worker. Пишет в БД только backend (REST + ingest).

## Схема

```text
cameras 1─1 camera_configs
   │1
   ├─N zones ──┐
   ├─N lines ──┤ (SET NULL)
   ├─N events ─┘ 1─0..1 snapshots
   ├─N track_sessions 1─N track_segments
   └─N analytics_aggregates
```

### cameras
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | не меняется после перезапуска |
| name | text not null | уникально среди не удалённых: `UNIQUE (name) WHERE deleted_at IS NULL` → 409 |
| source_type | text not null | `CHECK IN ('file','rtsp','mock')` |
| source_url | text not null | `rtsp://…`, `upload://{file_ref}`, `mock://{scenario}`; учётные данные RTSP хранятся здесь, наружу — только маскированно |
| enabled | bool not null default false | желаемое состояние «камера работает» |
| assigned_worker | text null | задел под распределение (§144); MVP — `NULL` = любой worker |
| created_at, updated_at | timestamptz not null | |
| deleted_at | timestamptz null | мягкое удаление ([ADR-011](decisions/ADR-011-camera-soft-delete.md)) |

### camera_configs
Переопределения настроек камеры; `NULL` = глобальный default из конфигурации ([behavior.md](behavior.md)). Типизированные колонки, не JSON.

| Колонка | Тип | Ограничение |
|---|---|---|
| camera_id | uuid PK, FK cameras ON DELETE CASCADE | |
| target_fps | real null | `> 0 AND <= 30` |
| detection_confidence | real null | `0 < x < 1` |
| zone_enter_dwell_seconds | real null | `>= 0` |
| zone_exit_grace_seconds | real null | `>= 0` |
| event_cooldown_seconds | real null | `>= 0` |
| loitering_threshold_seconds | real null | `> 0` |
| snapshot_enabled | bool null | |
| updated_at | timestamptz not null | |

### zones
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | |
| camera_id | uuid FK cameras CASCADE, index | |
| name | text not null | |
| points | jsonb not null | `[{"x":0.1,"y":0.2}, …]`, валидируется Pydantic: ≥ 3 точек, 0 ≤ x,y ≤ 1, площадь > 0, без самопересечений → иначе 422 |
| enabled | bool not null default true | |
| created_at, updated_at | timestamptz | |

### lines
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | |
| camera_id | uuid FK cameras CASCADE, index | |
| name | text not null | |
| p1_x, p1_y, p2_x, p2_y | real not null | `CHECK 0..1`; P1 ≠ P2 (валидация схемы) |
| enabled | bool not null default true | |
| created_at, updated_at | timestamptz | |

### events
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | создаётся worker'ом; основа идемпотентной записи |
| camera_id | uuid FK cameras | без каскада (история сохраняется) |
| run_id | uuid not null | запуск `CameraSession`; track_id уникален только внутри него |
| track_id | int not null | для UI «Track #17» |
| type | text not null | `PERSON_ENTERED_DANGER_ZONE`, `PERSON_CROSSED_LINE`, `PERSON_LOITERING_IN_DANGER_ZONE` |
| severity | text not null | `critical`, `warning`, `info` |
| status | text not null default 'NEW' | `NEW`, `ACKNOWLEDGED`, `FALSE_POSITIVE` ([ADR-007](decisions/ADR-007-event-statuses.md)) |
| zone_id | uuid null FK zones SET NULL | |
| line_id | uuid null FK lines SET NULL | |
| occurred_at | timestamptz not null | wall clock захвата кадра события («timestamp» из §40) |
| source_ts_ms | bigint null | время в источнике (позиция в видеофайле) |
| detector_confidence | real not null | средняя confidence детектора за окно подтверждения |
| event_confidence | real not null | см. behavior.md §7 |
| message | text not null | короткий текст на русском для CSV/логов; UI строит текст через i18n по `type` |
| metadata | jsonb not null | типизирован по `type` (Pydantic discriminated union): `bbox`, `anchor`, `dwell_seconds`, `direction` |
| note | text null | заметка оператора, ≤ 2000 символов |
| created_at | timestamptz not null | время записи в БД |
| acknowledged_at, false_positive_at | timestamptz null | аудит (§157) |
| updated_at | timestamptz not null | |

Индексы: `(occurred_at DESC)`, `(camera_id, occurred_at DESC)`, `(status, occurred_at DESC)`, `(type, occurred_at DESC)`.

### snapshots
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | |
| event_id | uuid unique FK events CASCADE | одно изображение на событие |
| storage_key | text not null | `snapshots/{camera_id}/{yyyy}/{mm}/{dd}/{id}.jpg`; путь не от пользователя |
| content_type | text not null | `image/jpeg` |
| width, height, size_bytes | int not null | |
| created_at | timestamptz not null, index | для retention |

Файл — в `SnapshotStorage`, в БД только ключ. `EventRead` отдаёт `snapshot_id` и `snapshot_url` (`/api/v1/snapshots/{id}`) через join. Retention: файлы и строки старше `SNAPSHOT_RETENTION_DAYS` удаляет периодическая задача API под Redis-блокировкой (`SET NX EX`), чтобы при N процессах выполнялась одна.

### track_sessions
| Колонка | Тип | Примечание |
|---|---|---|
| id | uuid PK | |
| camera_id | uuid FK cameras | |
| run_id | uuid not null | |
| track_id | int not null | `UNIQUE (camera_id, run_id, track_id)` — идемпотентность |
| started_at, ended_at | timestamptz not null | wall clock |
| frames_seen | int not null | кадры с совпавшей детекцией |
| avg_confidence | real not null | |

Индекс `(camera_id, started_at DESC)`.

### track_segments
| Колонка | Тип | Примечание |
|---|---|---|
| id | bigint identity PK | |
| track_session_id | uuid FK track_sessions CASCADE | |
| state | text not null | `NORMAL`, `IN_DANGER_ZONE` |
| zone_id | uuid null FK zones SET NULL | |
| started_at, ended_at | timestamptz not null | |

Индекс `(track_session_id, started_at)`.

### analytics_aggregates
| Колонка | Тип | Примечание |
|---|---|---|
| camera_id | uuid FK cameras | PK `(camera_id, granularity, bucket_start)` |
| granularity | text not null | MVP: `'1s'`; позже `'1h'`, `'1d'` |
| bucket_start | timestamptz not null | |
| frames | int not null | обработанные кадры в бакете |
| persons_max | smallint not null | |
| persons_avg | real not null | |
| persons_in_zone_max | smallint not null | |

1 строка/с на работающую камеру: 8 камер ≈ 0,7 млн строк в сутки. Это приемлемо для MVP; роллап в `1h` и retention для `1s` — задача Milestone 10.

## Правила записи

* Никаких покадровых INSERT. Ingest читает до 200 сообщений из Stream и пишет их одной транзакцией (`INSERT … ON CONFLICT DO NOTHING` / upsert для аналитики), затем `XACK`.
* Одна `AsyncSession` — один запрос или один ingest-пакет; между задачами не разделяется.
* Ошибка валидации сообщения → лог с `message_id`, сообщение подтверждается и копируется в `ad:ingest:dead` (Stream с `MAXLEN`), чтобы не блокировать очередь. Ошибка БД → без `XACK`, повтор с backoff.

## Как считаются показатели (§0.3, §72)

| Показатель | Источник |
|---|---|
| Длительность наблюдения | `count(*)` бакетов `1s` с `frames > 0` за период, в секундах |
| Среднее / максимальное число людей | `sum(persons_avg·frames)/sum(frames)`, `max(persons_max)` |
| Уникальные треки | `count(*)` `track_sessions` за период |
| Временной ряд | `analytics_aggregates`; для длинных диапазонов — `date_bin` в SQL |
| Track timeline | `track_sessions` + `track_segments` |
| События всего / critical / ложные / по камере / по типу / по времени | `events`, `GROUP BY` |
