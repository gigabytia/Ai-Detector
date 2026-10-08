# ADR-003. Трекинг людей

Статус: принято (Milestone 1)

Используется готовый ByteTrack из библиотеки `supervision` (лицензия MIT) за интерфейсом `PersonTracker`. Параметры ТЗ переводятся в параметры библиотеки в adapter'е: `track_activation_threshold = TRACK_ACTIVATION_CONFIDENCE`, `lost_track_buffer = PERSON_TRACK_MAX_AGE` при `frame_rate = 30` (тогда буфер равен ровно N кадрам), `minimum_matching_threshold = 1 − TRACK_MATCH_IOU` (библиотека сравнивает стоимость 1−IoU). Adapter сам ведёт реестр треков: определяет `LOST`, возраст и удаление, потому что библиотека возвращает только сопоставленные треки. Точное соответствие параметров проверяется unit-тестами в Milestone 5.

**Почему:** Трекер не пишется с нуля (§16); `supervision` не тянет AGPL-зависимость Ultralytics в трекинг.
