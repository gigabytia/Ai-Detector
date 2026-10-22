# ADR-035. Event snapshots и retention M8

Статус: принято, Milestone 8. Реализует ADR-015/021, дополняет ADR-034.

## Capture и доставка

Один **исходный полный кадр**, без draw/resize, JPEG quality90. SnapshotWriter с отдельным executor2, не более4 заданий (ссылки на immutable Frame, не копии). Inference не ждёт. При disabled/busy/codec/disk error тревога идёт без вложения; image capture не определяет readiness события. UUID снимка детерминирован uuid5(event.id,"snapshot"); один key на событие. После записи файл+metadata передаются одним EventMessage в прежний outbox. Повтор Redis не запускает JPEG заново. Shutdown: stop inference → drain snapshots → stop/drain events → close camera/runtime/clients. Зависший локальный syscall не имеет жёсткого deadline; это не asynchronous object storage с тайм-аутом.

SnapshotMetadata проверяет UUID, AwareDatetime, canonical key, dimensions/size/content type и binding к event/camera/UTC day. Ingest понимает старый DomainEvent. Невалидный optional snapshot логируется и игнорируется, валидная тревога остаётся. Event+metadata commit одной транзакцией, ACK после. UUID/event_id unique, replay не переписывает operator state и не воскрешает metadata старше retention. Live pub/sub сериализуется отдельно в базовый DomainEvent, ключ файла туда не попадает.

**Нет distributed transaction с файловой системой.** Worker crash до XADD/RAM-outbox overflow может оставить orphan; физические/DB backup надо согласовывать. Прежние окна потери RAM/AOF из ADR-034 сохраняются. Metadata не гарантирует наличие файла после ручного удаления/отказа диска.

## Storage и API

Shared stdlib protocol put/open/delete, реализация LocalSnapshotStorage. Logical key `snapshots/{cameraUUID}/{UTC yyyy/mm/dd}/{snapshotUUID}.jpg`. SNAPSHOT_PATH — root для содержимого `snapshots/`: prefix удаляется при отображении, то есть физически root/camera/date/id.jpg, **без второго snapshots/**. API/worker используют одинаковый private volume; другие хосты требуют общего mount или будущей реализации protocol.

Atomic NamedTemporaryFile в том же каталоге → flush/fsync → replace, cleanup partial при ошибке. Canonical UUID/date/jpeg keys, no traversal, no symlink components/final symlink; regular-file open с O_NOFOLLOW где доступно. Root должен быть доверенным: это не sandbox против конкурентного adversarial изменения каталогов. Запретить доступ посторонних пользователей и прямую HTTP-раздачу storage root.

API UUID lookup metadata, 404 missing/expired, image/jpeg, nosniff, private no-store. Не отдаёт storage_key, не принимает filesystem path. Streaming chunks, закрытие fd. Нет Range/thumbnail/resizing/API auth. EventRead содержит nullable id/url/dimensions через select-in, не по одному query на строку.

## Retention

API maintenance task раз в час (настраивается), default30 дней. SET NX EX120, token-owned renewal каждые30с и compare-delete release. Потеря lease/Redis прерывает проход; delete идемпотентен, событие никогда не удаляется. Metadata batch100, file delete до rowdelete; ошибка unlink сохраняет row для retry. Отсутствующий файл не мешает удалению metadata. Потеря DBcommit после unlink временно оставляет missing-file reference и безопасно повторяется.

Orphan JPEG обход потоковый batches100, удаление по mtime только старше того же cutoff и без ссылки metadata. Старые .snapshot-*.part тоже убираются. Новые файлы до ingest не затрагиваются. После прерывания уже запущенный to_thread syscall может закончиться: lease не является distributed filesystem fencing. Нужен мониторинг cleanup errors/диска/backlog. Задача maintenance не входит в readiness event_delivery (это не критический путь доставки), ошибки явно в логах.

## UI

Event detail показывает JPEG и исторические bbox/anchor из самого события, optional overlay; текущую зону не выдаёт за историческую. Сам JPEG без графики. Нет captured polygon/name, before/after кадров. No-image/expired/404/broken-image не прячут event/status/note. config select inherit/on/off, default принадлежит API. Snapshot retention не является удалением event history.
