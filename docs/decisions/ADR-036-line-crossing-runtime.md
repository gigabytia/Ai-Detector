# ADR-036. Направленная линия и crossing runtime M9

Статус: принято. Реализует ADR-013 и §5 behavior; дополняет ADR-033/034/035.

## Геометрия и событие

LineShape: name 1..100 после trim, enabled, две нормализованные точки p1/p2 в 0..1. Минимальная длина строго >1e-6; API и SQL CHECK запрещают вырожденный отрезок. Направленный конечный отрезок P1 → P2, anchor — нижний центр bbox. Знак определяется `(P2-P1) × (anchor-P1)`, signed distance делится на длину. Stable side меняется только вне полосы |d| ≤ LINE_HYSTERESIS (default0.01). Первое наблюдение — baseline; касание/движение в полосе не crossing. Для нового знака проекция **текущего anchor в момент подтверждения** должна попасть в [0,1], включая концы. Пересечение продолжения не считается; side всё равно обновляется, чтобы вход вдоль стороны позже не породил отложенную тревогу. Это правило ADR-013, не пересечение двух отрезков траектории.

LEFT_TO_RIGHT = − → +, RIGHT_TO_LEFT = + → − относительно P1 → P2, **не** географическое лево/право экрана. Оба направления включены, отдельного direction filter нет. LOST замораживает side; восстановление на другой стороне считается crossing. Не создаёт PersonState: тот же человек может одновременно войти в зону и пересечь линию.

Минимум EVENT_MIN_TRACK_HITS (default3) cumulative track hits. Confidence: в последних min_hits обработанных наблюдениях (сколько доступно) mean matched confidence × matched fraction, LOST даёт пропуск. Cooldown по wall Clock на camera/run/track/type; общий для всех линий одного track, но отдельный от зоны. Подавленный crossing меняет side и логируется debug. SEVERITY_LINE_CROSS default warning; per-camera event_cooldown_seconds переиспользуется.

## Жизненный цикл

LineEngine находится в SceneRegistry на том же единственном inference executor после tracker/ZoneEngine. Изменение геометрии/disable/delete очищает side только этой линии; rename не очищает. Cooldown трека при правке линии не обнуляется. Новый run, source epoch/loop/reconnect/discontinuity, смена frame size очищают сцену. Удалённые track IDs удаляются из side/windows/cooldown, retain удаляет остановленные runs. Hot CameraSpec обновляет линии без смены run, preview metadata берётся из того же DetectionResult, что JPEG и bbox.

## Данные и доставка

Миграция e2c6db45c9b8 после M8: lines (camera FK CASCADE, coordinates/checks/index, timestamps), nullable events.line_id FK SET NULL. CRUD camera-scoped, max16 под блокировкой родительской камеры, soft-deleted parent404. CAMERA_CHANGED best effort, периодический reconcile восстанавливает пропуск уведомления. Worker не обращается к PostgreSQL.

DomainEvent остаётся одним frozen Pydantic model с union metadata и after-validator, **не** иерархией discriminated event subclasses. Для line type требуется line_id, zone_id=None, LineCrossMetadata (bbox/anchor/stability/direction/line_name/p1/p2); для zone — обратные ссылки/ZoneEntryMetadata. Старые zone payload принимаются. Persisted EventRead допускает null ссылки после удаления; ingest проверяет принадлежность line camera, чужая/удалённая ссылка становится null. Исторические name/p1/p2 остаются в metadata. UTF8 PostgreSQL нужен для JSONB с локализованными именами.

Снимок, Redis outbox/Stream/pubsub, idempotent event+snapshot ingest, status/note audit и retention используют M7/M8 путь без нового канала/покадровой записи. JPEG не содержит графику; UI рисует историческую линию из event metadata, не текущую из камеры. Старые RAM/AOF/filesystem окна потери сохраняются.

## Интерфейс и границы

Редактор только первой линии (как ADR-009 для зоны), явная подсказка при нескольких; остальные не перезаписываются. Две упорядоченные точки на кадре/keyboard, undo/clear/cancel, enable/save/delete-confirm, взаимная блокировка редакторов зоны/линии. Нормализация через source image/object-contain, preview стрелка и P1/P2. История и SSE показывают новый type; детали — снимок, сохранённая геометрия, знак направления и обычные операторские действия.

Нет loitering, track sessions, CSV, авторизации, аналитики или dashboard. Следующий M10 — dashboard со статистикой/таймлайном; качество движущегося CCTV и реальные RTSP не оценивались.
