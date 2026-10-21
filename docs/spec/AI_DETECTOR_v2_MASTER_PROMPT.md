# MASTER BUILD PROMPT — AI DETECTOR v2

## 0. Исходные данные и правила работы агента (читать первым)

### 0.1 Промпт самодостаточен

Репозиторий создаётся с нуля. Никаких внешних исходников нет: всё, что нужно знать о поведении системы, описано в этом промпте. Если требуется решение, которого здесь нет, выбери самый простой вариант, запиши его одним абзацем в `docs/decisions/` и продолжай работу.

### 0.2 Область: только люди

Анализируется только человек. Детекции объектов (коробки, паллеты и т.п.), определения переносимого груза и pose estimation в текущей версии нет, заглушек под них не создавать (§27).

### 0.3 Поведение системы: правила и значения по умолчанию

Все значения ниже — default в конфигурации, не hardcode. Правила и пороги задокументировать в `docs/behavior.md`.

* **Источники видео:** загруженный через UI видеофайл, RTSP, mock-источник.
* **Точка человека:** нижняя центральная точка bbox. Зона и линия хранятся в нормализованных координатах (0..1).
* **Danger zone:** point-in-polygon. Событие входа создаётся, когда человек находится внутри не менее 0.25 с (`ZONE_ENTER_DWELL_SECONDS`), и только один раз за заход. Cooldown 3 с (`EVENT_COOLDOWN_SECONDS`) действует на комбинацию «камера + track + тип события». Повторное событие — только после выхода и нового входа.
* **Линия:** знак векторного произведения `(P2 − P1) × (P − P1)` сравнивается с предыдущим кадром; смена знака — пересечение; нулевое значение пересечением не считается. Добавить небольшой допуск (hysteresis), чтобы дрожание bbox не давало повторных событий.
* **Loitering:** если человек непрерывно находится в зоне дольше 10 с (`LOITERING_THRESHOLD_SECONDS`), создаётся одно событие на заход (§28).
* **Детектор:** класс `person`, confidence 0.25, IoU для NMS 0.45, размер входа 640; по умолчанию лёгкая модель (класс nano/small).
* **Трекер людей:** ByteTrack через adapter; удаление трека после 25 пропущенных кадров, порог IoU при сопоставлении 0.5, минимальный confidence для создания трека 0.25.
* **Snapshot:** кадр на момент события, сохраняется асинхронно (§42).
* **Статусы события:** `NEW` → `ACKNOWLEDGED` или `FALSE_POSITIVE`; оператор может добавить текстовую заметку.
* **Аналитика по камере:** длительность наблюдения, среднее и максимальное число людей, число уникальных треков; временной ряд раз в секунду (людей всего, людей в зоне); сегменты треков (состояние, начало, конец) для track timeline.
* **Severity по умолчанию:** вход в зону — `critical`, пересечение линии — `warning`, loitering — `warning`; настраивается.
* **Экспорт:** список событий выгружается в CSV с учётом текущих фильтров.

### 0.4 Приоритеты при конфликте требований

В промпте много требований, и часть из них может конфликтовать. Порядок приоритетов:

1. Жёсткие ограничения: tracking только людей (§2), никакого тяжёлого inference в API (§4), никаких проглоченных исключений (§54), никаких секретов в коде и логах (§114), список «не делать сейчас» (§158).
2. Корректность и тестируемость бизнес-логики.
3. Простота: меньше кода и меньше абстракций при равной корректности.
4. Всё остальное.

Останавливайся и задавай вопрос человеку только если решение необратимо или меняет §2, §4 либо стек.

### 0.5 Уровни объёма

Уровни определяют порядок работы, а не отменяют требования. Переходи к следующему уровню только когда предыдущий работает end-to-end и тесты проходят.

* **Уровень 1 — ядро (Milestone 1–8).** Mock-источник и видеофайл, person detection, tracking, danger zone, событие, БД, realtime (SSE/WebSocket), snapshot, UI оператора: карточки камер, редактор зоны, панель событий, подтверждение и ложная тревога. Docker для инфраструктуры. Unit-тесты логики.
* **Уровень 2 — расширение (Milestone 9–11).** Линия, dashboard и аналитика, track timeline, loitering, экспорт CSV, i18n, Vitest, CI, ADR.
* **Уровень 3 — зрелость (Milestone 12 и остальное).** RTSP через MediaMTX с WebRTC/HLS, Prometheus-метрики полностью, Playwright, benchmark 4 и 8 камер, ONNX/TensorRT, GPU-compose.

### 0.6 Окружение команды

* Команда студентов, разработка в основном на Windows. Подготовь путь запуска без Docker для приложений: `uv run` для backend и worker, `npm run dev` для frontend. Docker нужен минимум для PostgreSQL и Redis.
* Каждая команда из `Makefile` должна иметь документированный эквивалент для PowerShell. Не полагайся на то, что на машине разработчика есть `make`.
* Реальных камер и мощного GPU может не быть. Базовый сценарий — CPU-only, 1–2 камеры из mp4 или mock-источника, лёгкая модель. Benchmark проводи на доступном оборудовании и записывай, на каком именно (CPU, GPU, RAM). Не заявляй результаты для железа, которого не было.

### 0.7 Как вести работу

* Веди `PROGRESS.md` в корне: что сделано, что в работе, принятые решения, известные проблемы. Читай его в начале каждой сессии — контекст может сброситься.
* Делай git-коммит после каждого milestone и после каждого значимого шага. Сообщения коммитов — на английском.
* **После Milestone 1 остановись** и покажи человеку `docs/architecture.md`, `docs/data-flow.md`, `docs/database.md`, `docs/behavior.md` и структуру каталогов. Дальше — только после подтверждения.
* Версии зависимостей проверяй в официальной документации. Если доступа к сети нет, используй последние известные стабильные версии, зафиксируй их в lock-файле и пометь в `PROGRESS.md`, что версии не проверены.
* Если не можешь запустить проверку (нет GPU, нет камеры), скажи об этом явно, а не пиши, что всё проверено.

### 0.8 Язык и соглашения

* Интерфейс оператора и документация в `docs/` — на русском.
* Идентификаторы, комментарии в коде, имена коммитов, названия миграций — на английском.

---

## Роль

Ты — senior software architect + senior Python backend engineer + computer vision engineer + ML engineer + senior frontend engineer.

Твоя задача — **с нуля спроектировать и реализовать проект компьютерного зрения** — систему видеонаблюдения, которая находит людей на видеопотоках и сообщает оператору об опасных ситуациях.

Это не задача «сгенерировать как можно больше кода».

Главная задача — создать **чистую, понятную, тестируемую и расширяемую основу**, которая реализует описанные ниже возможности и не превращается в набор случайно связанных файлов.

Проект должен быть пригоден для:

1. разработки небольшой командой студентов;
2. демонстрации в рамках акселератора;
3. дальнейшего расширения;
4. последующего переноса на production-инфраструктуру;
5. замены моделей и inference runtime без переписывания бизнес-логики.

---

# 1. Контекст проекта

Проект — система интеллектуального видеонаблюдения.

Есть веб-интерфейс оператора.

Оператор может:

* подключать несколько видеокамер;
* видеть состояние камер;
* просматривать видеопотоки;
* настраивать для камеры опасную зону;
* настраивать линию/границу;
* видеть людей на видеопотоке;
* получать события, когда человек входит в опасную зону;
* получать события при пересечении заданной линии;
* получать события, если человек слишком долго находится в опасной зоне;
* видеть ID отслеживаемого человека;
* получать снимок события;
* подтверждать событие;
* отмечать событие как ложную тревогу;
* просматривать историю событий и выгружать её в CSV;
* просматривать базовую аналитику;
* просматривать информацию о состоянии камер и системы.

Основной объект анализа:

**ЧЕЛОВЕК.**

---

# 2. ЖЁСТКОЕ ОГРАНИЧЕНИЕ ПО TRACKING

## Разрешён только tracking людей.

В проекте НЕ должно быть object tracking для:

* коробок;
* паллет;
* погрузчиков;
* тележек;
* оборудования;
* любых иных объектов.

Никаких persistent track ID для этих объектов.

Никаких:

```text
BoxTrack
PalletTrack
ForkliftTrack
ObjectTracker
```

и аналогичных сущностей.

Единственные долгоживущие tracking entities:

```text
PersonTrack
```

или эквивалентная сущность.

---

## Детекции объектов в текущей версии нет вовсе

Система анализирует только людей. Детекция объектов (коробки, паллеты и т.п.), определение переносимого груза и pose estimation в текущую версию не входят (см. §27). Если контекстная детекция объектов появится позже, объектного трекинга всё равно не будет.

---

# 3. Основная философия архитектуры

Не строить:

```text
CameraManager
    ↓
вся логика проекта
```

Не строить:

```text
App.vue
    ↓
весь frontend
```

Не строить:

```text
FastAPI endpoint
    ↓
YOLO
    ↓
tracker
    ↓
database
```

в одном месте.

Нужна архитектура:

```text
                         ┌─────────────────────┐
                         │      Frontend       │
                         │ Vue 3 + TypeScript  │
                         └──────────┬──────────┘
                                    │
                       REST + SSE/WebSocket
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      API layer      │
                         │      FastAPI        │
                         └──────────┬──────────┘
                                    │
                         commands / state / DB
                                    │
              ┌─────────────────────┴─────────────────────┐
              │                                           │
              ▼                                           ▼
     ┌─────────────────┐                         ┌─────────────────┐
     │   PostgreSQL    │                         │      Redis      │
     │ persistent data │                         │ event/queue     │
     └─────────────────┘                         └────────┬────────┘
                                                           │
                                                           ▼
                                                ┌──────────────────┐
                                                │  Vision Worker   │
                                                │ CV processing     │
                                                └────────┬─────────┘
                                                         │
                         ┌───────────────────────────────┼───────────────────┐
                         │                               │                   │
                         ▼                               ▼                   ▼
                  Camera Sources                  Inference Runtime     Event Engine
                         │                               │                   │
                         ▼                               ▼                   ▼
                    Frame Queue                    Person Detector       Zone Logic
                                                         │                Line Logic
                                                         ▼                Analytics
                                                   Person Tracker
```

---

# 4. Архитектурный принцип №1

## Web API не должен выполнять тяжёлый computer vision inference.

FastAPI отвечает за:

* REST API;
* WebSocket/SSE;
* конфигурацию;
* команды;
* чтение/запись persistent state;
* авторизацию в будущем;
* выдачу аналитики;
* health checks;
* API documentation.

FastAPI НЕ должен заниматься:

* `YOLO.predict()` в request handler;
* бесконечными camera loops;
* чтением каждого кадра;
* tracking;
* тяжёлым OpenCV processing;
* сохранением каждого кадра.

Inference выполняется в отдельном vision worker.

---

# 5. Архитектурный принцип №2

## Runtime state и persistent state — разные вещи.

Persistent:

```text
Camera
Camera configuration
Zone
Line
Event
Event snapshot metadata
Track session
Analytics
```

Runtime:

```text
Camera connection
capture thread/task
latest frame
FPS
GPU inference state
active tracks
tracker state
processing metrics
queues
```

Runtime state не должен полностью храниться в PostgreSQL.

---

# 6. Архитектурный принцип №3

## Не хранить каждый обработанный кадр в БД.

Нельзя делать:

```text
frame
→ INSERT
→ commit
→ frame
→ INSERT
→ commit
```

для каждого кадра.

Сохранять только:

* события;
* необходимые snapshots;
* агрегированную аналитику;
* track sessions / segments;
* периодические статистические данные.

Операционные данные должны отправляться в storage асинхронно или пакетно.

---

# 7. Архитектурный принцип №4

## Video stream и analytics metadata должны быть разделены.

Не нужно передавать всё видео через FastAPI.

Желаемая архитектура:

```text
Camera
   ↓
Media gateway
   ↓
Browser
```

и отдельно:

```text
Vision worker
   ↓
metadata
   ↓
WebSocket/SSE
   ↓
Browser
```

В браузере можно рисовать:

* bounding boxes людей;
* track IDs;
* danger zone;
* exit line;
* состояния;
* предупреждения.

Таким образом, видеопоток не нужно постоянно JPEG-кодировать на backend только ради отрисовки рамок.

---

# 8. Технологический стек

Используй современные стабильные версии библиотек.

Не нужно слепо копировать версии из данного промпта.

Перед установкой зависимостей проверяй актуальные стабильные версии в официальной документации (см. §0.7, если доступа к сети нет).

---

## Backend

Использовать:

```text
Python 3.12
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
PostgreSQL
Redis
Uvicorn
```

Дополнительно:

```text
httpx
pydantic-settings
orjson
structlog или стандартный logging с JSON formatter
```

Для package management:

```text
uv
```

Использовать `pyproject.toml`. Backend, vision worker и общий пакет `shared` (§78) оформить как участников одного uv workspace.

Не создавать старый-style:

```text
requirements.txt
```

как единственный источник зависимостей.

Можно генерировать lock-файл средствами выбранного package manager.

---

# 9. Frontend stack

Использовать:

```text
Vue 3
TypeScript
Vite
Pinia
TanStack Vue Query
Tailwind CSS
shadcn-vue
Lucide icons
ECharts
```

Использовать:

```vue
<script setup lang="ts">
```

Весь новый frontend — TypeScript.

Никакого большого JavaScript-кода без необходимости.

Vue Query отвечает за server state:

```text
cameras
events
analytics
camera config
system status
```

Pinia использовать для client/UI state:

```text
selected camera
sidebar
filters
theme
modals
operator preferences
```

Не дублировать API-state одновременно в Pinia и Vue Query.

---

# 10. Streaming / Media

Архитектура должна поддерживать:

```text
local video file
RTSP
mock source
```

через общий abstraction:

```text
FrameSource
```

Не писать business logic непосредственно под `cv2.VideoCapture`.

Минимальная реализация может использовать OpenCV/FFmpeg backend.

Интерфейс синхронный: чтение кадров блокирующее, выполняется в собственном потоке захвата источника (§194: CPU/GPU и блокирующее I/O захвата — синхронно в потоке, остальное I/O — async).

```python
class FrameSource(Protocol):
    def start(self) -> None: ...
    def read(self) -> Frame | None: ...   # None — нет нового кадра / источник закончился
    def stop(self) -> None: ...
```

Точная сигнатура на усмотрение агента, но принцип обязателен: источник можно заменить, не затрагивая pipeline.

Для дальнейшего развития предусмотреть возможность подключения:

```text
FFmpeg
GStreamer
MediaMTX
WebRTC
HLS
```

без изменения аналитического pipeline.

---

# 11. Рекомендуемый media gateway

Для архитектуры подготовить поддержку MediaMTX как отдельного сервиса.

Его задача:

```text
RTSP camera
     ↓
MediaMTX
     ↓
WebRTC/HLS
     ↓
browser
```

Vision worker при этом занимается аналитикой, а не раздачей видео тысячей JPEG response.

Для локального MVP можно оставить более простой fallback stream.

Главное:

**streaming abstraction должен быть отделён от CV inference.**

## 11.1 Решение для MVP: как браузер получает видео и рамки

Главная проблема раздельной доставки видео и метаданных — рассинхронизация: рамки приходят не в тот момент, что кадр. Решение для MVP (Уровень 1):

* Fallback-доставка идёт из vision worker (не из API): по WebSocket отправляются бинарные сообщения «JPEG низкого разрешения + JSON с метаданными того же кадра». Кадры кодируются **только для камер, которые сейчас открыты в UI**, и с ограниченным FPS (конфиг). Так кадр и рамки синхронны по построению, а JPEG не кодируется «в никуда».
* Рамки, зоны, линии и track ID рисуются в браузере на canvas поверх изображения (§77), а не вшиваются в картинку.
* Основной путь (Уровень 3): MediaMTX + WebRTC/HLS, метаданные по WebSocket с `frame_id` и `source_timestamp`; рассинхронизацию компенсировать небольшим буфером на frontend. Допустимое расхождение и ограничения описать в `docs/decisions/ADR-005`.
* Любой из путей реализуется за одним frontend-интерфейсом «источник изображения камеры», чтобы смена способа доставки не затрагивала `CameraCard` и редактор зоны.

---

# 12. Computer Vision stack

Базовые технологии:

```text
OpenCV
PyTorch
ONNX Runtime
```

Модель должна загружаться через abstraction:

```text
Detector
```

Например:

```python
class PersonDetector(Protocol):
    def predict(...)
```

Не писать:

```python
from ultralytics import YOLO
```

по всему проекту.

Вызов конкретной ML-библиотеки должен находиться внутри adapter:

```text
inference/
    adapters/
        ultralytics_adapter.py
        onnx_runtime_adapter.py
```

Библиотека Ultralytics распространяется под лицензией AGPL-3.0 (есть отдельная коммерческая лицензия). Для учебного проекта и демонстрации это приемлемо, но если проект пойдёт в production, лицензию нужно пересмотреть. Зафиксируй это в `ADR-006` и сохрани возможность заменить детектор через adapter.

---

# 13. Важное требование к ML runtime

Бизнес-логика НЕ должна знать:

```text
YOLO
Ultralytics
PyTorch
ONNX Runtime
TensorRT
OpenVINO
```

Она должна получать:

```text
Detection
```

например:

```text
Detection
- class_id
- class_name
- confidence
- bbox
- timestamp
```

Это позволит позже заменить:

```text
PyTorch → ONNX Runtime
ONNX Runtime → TensorRT
CUDA → CPU
NVIDIA → Intel
```

не переписывая tracking и event engine.

---

# 14. Inference runtime

Предусмотреть:

```text
CPU fallback
CUDA
```

и возможность:

```text
TensorRT
```

позже.

Сначала добиться правильной работы на обычном inference runtime.

После этого проводить оптимизацию.

Запрещено заранее усложнять проект TensorRT только ради слова «оптимизация».

---

# 15. Person detection

Основной detector обнаруживает:

```text
person
```

Минимальный output:

```text
bbox
confidence
class
timestamp/frame_id
```

Поддерживать batch inference.

---

# 16. Person tracking

Использовать отдельный `PersonTracker`.

Допустимая базовая технология:

```text
ByteTrack
```

или другой хорошо проверенный person-tracking алгоритм.

Но:

**не нужно писать tracker с нуля только ради самостоятельной реализации.**

Если используется готовая реализация, сделать adapter.

---

# 17. Tracker должен корректно работать при отсутствии детекций

Это критическое требование.

На каждом frame tracker должен получать:

```text
detections = []
```

если людей не обнаружено.

То есть нельзя:

```python
if detections:
    tracker.update(...)
```

и ничего не делать при пустом результате.

Должна существовать корректная логика:

```text
frame
 ↓
predict
 ↓
detection matching
 ↓
update
 ↓
age tracks
 ↓
remove expired tracks
```

---

# 18. Tracking semantics

Track ID:

```text
уникален внутри камеры и текущего runtime
```

Не пытаться реализовывать глобальное распознавание одного и того же человека между камерами.

Не реализовывать:

```text
face recognition
person re-identification
biometric identification
```

в текущем MVP.

В будущем должна быть возможность добавить это отдельным модулем.

---

# 19. PersonTrack

Каждый активный track должен содержать примерно:

```text
track_id
camera_id
bbox
center
confidence
first_seen
last_seen
age
state
```

Дополнительно:

```text
velocity
last_zone
current_zone
```

при необходимости.

---

# 20. Domain state человека

Человек не должен представляться просто:

```python
dict
```

Использовать типизированную модель.

Например:

```text
PersonTrack
PersonState
```

Состояния:

```text
NORMAL
IN_DANGER_ZONE
CROSSING_LINE
LOST
```

Но не создавать огромное количество состояний без необходимости.

Состояния должны быть формализованы.

---

# 21. Danger Zone Engine

Danger zone — polygon в координатах изображения.

Лучше хранить координаты нормализованно:

```text
x = 0..1
y = 0..1
```

а не в пикселях.

Это важно, потому что разрешение камеры может измениться:

```text
1920x1080
1280x720
640x360
```

а зона должна остаться на том же месте.

---

# 22. Zone model

Создать типизированную модель:

```text
Zone
```

например:

```text
id
camera_id
name
type
points
enabled
created_at
updated_at
```

`type`:

```text
POLYGON
LINE
```

или разделить сущности Zone и Line.

Предпочтительно не хранить:

```python
list[list[Any]]
```

без validation.

---

# 23. Coordinate system

Всегда явно определять:

```text
normalized coordinates
```

где:

```text
0 <= x <= 1
0 <= y <= 1
```

Backend отвечает за преобразование:

```text
normalized → pixel
```

Frontend визуализирует polygon в координатах canvas.

---

# 24. Danger zone event

Основное событие:

```text
PERSON_ENTERED_DANGER_ZONE
```

Не создавать событие на каждом кадре.

Должен использоваться state transition:

```text
NORMAL
      ↓
inside zone
      ↓
IN_DANGER_ZONE
      ↓
event
```

Если человек остаётся внутри зоны 50 кадров:

```text
НЕ 50 событий.
```

Только одно событие входа.

---

# 25. Exit line

Поддерживать линию:

```text
P1 → P2
```

и определять пересечение траекторией человека.

Точка отсчёта человека:

```text
нижняя центральная точка bbox
```

или другая формально выбранная точка.

Решение по умолчанию — нижний центр bbox; задокументировать.

---

# 26. Line crossing event

Генерировать:

```text
PERSON_CROSSED_LINE
```

только при реальном переходе через линию.

Не создавать повторные события из-за небольших колебаний bounding box.

Использовать hysteresis / state tracking.

---

# 27. Отложено: объекты, перенос груза, pose

В текущей версии НЕ реализовывать и не создавать заглушек для:

```text
object detection (коробки, паллеты, погрузчики и т.п.)
carrying detection (определение, что человек что-то несёт)
pose estimation
```

Это решение об объёме, а не техническое ограничение: сначала система должна надёжно работать только с людьми. Архитектура при этом должна позволять добавить такие возможности позже без переписывания ядра: новая модель подключается через adapter детектора (§12–§13), новое правило — через EventEngine (§39). Пустые классы «на будущее» не создавать (§174).

---

# 28. Loitering

Если человек непрерывно находится в danger zone дольше порога (`LOITERING_THRESHOLD_SECONDS`), генерируется одно событие `PERSON_LOITERING_IN_DANGER_ZONE` на заход. Выход из зоны сбрасывает отсчёт. Время считается по timestamps кадров (§34), правило покрывается unit-тестами с fake timestamps.

---

# 29. Camera architecture

Каждая камера должна быть представлена двумя сущностями.

## Persistent

```text
Camera
```

Хранится в PostgreSQL.

## Runtime

```text
CameraSession
```

Живёт в worker.

Пример:

```text
Camera
 ├── id UUID
 ├── name
 ├── source_type
 ├── source_url
 ├── enabled
 ├── created_at
 └── config

CameraSession
 ├── camera_id
 ├── source
 ├── capture
 ├── latest_frame
 ├── tracker
 ├── metrics
 ├── state
 └── lifecycle
```

---

# 30. Camera ID

Не использовать:

```python
_next_id = 1
```

Камера должна иметь постоянный:

```text
UUID
```

или другой persistent identifier.

После перезапуска:

```text
camera_id НЕ должен измениться.
```

---

# 31. Camera lifecycle

Для каждой камеры реализовать:

```text
CREATED
STARTING
RUNNING
DEGRADED
RECONNECTING
STOPPING
STOPPED
ERROR
```

Минимально достаточно:

```text
starting
online
offline
error
```

но архитектура должна позволять расширение.

---

# 32. Auto reconnect

Если RTSP/source временно пропал:

```text
capture fails
      ↓
camera status = reconnecting
      ↓
backoff
      ↓
reconnect
```

Использовать exponential backoff с верхним пределом.

Не создавать бесконечный tight loop:

```python
while True:
    connect()
```

---

# 33. Frame capture

Каждый camera source должен иметь:

```text
bounded buffer
```

Рекомендуемая политика для live video:

```text
queue size = 1..2
```

При переполнении выбрасывать старый кадр.

Приоритет:

```text
freshness > completeness
```

Система должна лучше обработать свежий кадр с некоторым пропуском кадров, чем накопить latency в 10 секунд.

---

# 34. Frame timestamps

Всегда разделять:

```text
source_timestamp
processing_timestamp
wall_clock_timestamp
```

Нельзя смешивать их в бизнес-логике.

Например:

```text
video time
```

используется для временной логики prerecorded video.

```text
wall clock
```

используется для:

```text
event created_at
cooldowns
logs
monitoring
```

---

# 35. Frame sampling

Настраиваемый:

```text
TARGET_FPS
```

не должен означать искусственное замедление video playback.

Для live stream нужно:

```text
read latest available frame
sample according to target FPS
```

Для prerecorded video допустимо:

```text
frame skipping
```

без изменения реального timestamp видео.

---

# 36. Inference batching

Не вызывать:

```text
model.predict()
```

отдельно для каждой камеры.

Использовать scheduler:

```text
Camera A frame
Camera B frame
Camera C frame
Camera D frame
        ↓
Batch builder
        ↓
PersonDetector(batch)
```

Batch size — конфигурационный параметр.

Scheduler должен учитывать:

```text
max batch size
max wait time
camera priority
target FPS
```

---

# 37. Не блокировать все камеры из-за одной камеры

Ошибка:

```text
Camera A
 ↓
inference
 ↓
crash
 ↓
весь worker умер
```

неприемлема.

Ошибка одной камеры должна приводить к:

```text
Camera A = ERROR
```

а:

```text
Camera B
Camera C
Camera D
```

продолжают работать.

---

# 38. Не блокировать inference storage

Плохое:

```text
detect
 ↓
DB commit
 ↓
detect
```

Хорошее:

```text
detect
 ↓
event
 ↓
event queue
 ↓
storage worker
```

или batching.

---

# 39. Event Engine

Создать отдельный:

```text
EventEngine
```

Он получает:

```text
PersonTrack
SceneState
ZoneState
LineState
```

и возвращает:

```text
DomainEvent
```

Например:

```text
PERSON_ENTERED_DANGER_ZONE
PERSON_CROSSED_LINE
PERSON_LOITERING_IN_DANGER_ZONE
```

---

# 40. DomainEvent

Типизированная модель:

```text
Event
```

Поля:

```text
id
camera_id
track_id
type
severity
timestamp
source_timestamp
message
snapshot_id
metadata
status
created_at
```

Статусы:

```text
NEW
ACKNOWLEDGED
FALSE_POSITIVE
RESOLVED
```

---

# 41. Event cooldown

Cooldown должен существовать отдельно от event generation.

Например:

```text
person enters zone
      ↓
event
      ↓
person remains inside
      ↓
no repeated events
```

После выхода:

```text
enter again
      ↓
new event
```

Cooldown не должен скрывать реально новое событие.

---

# 42. Snapshot

При критическом событии можно сохранять snapshot.

Но:

* snapshot не должен блокировать inference;
* snapshot сохраняется асинхронно;
* хранить физический файл отдельно от metadata;
* в БД хранить path/object key;
* добавить retention policy.

Хранилище должно быть абстрактным:

```text
SnapshotStorage
```

В MVP:

```text
local filesystem
```

В будущем:

```text
S3-compatible storage
MinIO
cloud object storage
```

---

# 43. PostgreSQL schema

Минимальные сущности:

```text
cameras
camera_configs
zones
lines
events
snapshots
track_sessions
track_segments
```

Опционально:

```text
analytics_aggregates
system_settings
```

Периодические данные для графиков (например, число людей раз в секунду) — это агрегат в `analytics_aggregates`, а не покадровая запись.

---

# 44. Database rules

Использовать:

```text
SQLAlchemy 2.x
Alembic
Pydantic schemas
repositories
service layer
```

Не вызывать SQLAlchemy напрямую из frontend API endpoint.

Плохо:

```python
@app.get(...)
async def endpoint():
    db.execute(...)
    detector(...)
    ...
```

Хорошо:

```text
API
 ↓
Application Service
 ↓
Repository
 ↓
Database
```

---

# 45. Repository pattern

Создать минимум:

```text
CameraRepository
EventRepository
TrackRepository
ZoneRepository
```

Не нужно делать enterprise abstraction ради abstraction.

Repositories должны быть тонкими и понятными.

---

# 46. Database writes

Использовать:

```text
transactions
batch inserts
async sessions where appropriate
indexes
```

Не создавать `AsyncSession`, которая используется одновременно несколькими concurrent tasks.

Каждый request/task должен иметь корректно изолированную DB session.

---

# 47. Redis

Использовать Redis только там, где он действительно нужен.

Предназначение:

```text
event bus
worker commands
short-lived state
rate limiting
optional cache
```

Не использовать Redis вместо PostgreSQL для persistent data.

---

# 48. Event bus

Логика:

```text
Vision worker
    ↓
Event bus
    ↓
API / subscriber
    ↓
SSE/WebSocket
    ↓
Frontend
```

Это позволит позже иметь:

```text
worker 1
worker 2
worker 3
```

без тесной связи между ними.

---

# 49. Real-time frontend communication

Использовать:

```text
SSE
```

для серверного потока событий, если bidirectional connection не требуется.

Использовать:

```text
WebSocket
```

для live analytics metadata выбранной камеры.

Не передавать full-resolution video через WebSocket (низкоразрешающий fallback-кадр из §11.1 — осознанное исключение: ограниченный FPS, только для открытых камер).

---

# 50. REST API

Сделать API versioned:

```text
/api/v1
```

Основные endpoints:

```text
GET    /api/v1/cameras
POST   /api/v1/cameras
GET    /api/v1/cameras/{id}
PATCH  /api/v1/cameras/{id}
DELETE /api/v1/cameras/{id}

POST   /api/v1/cameras/{id}/start
POST   /api/v1/cameras/{id}/stop
POST   /api/v1/cameras/{id}/restart

GET    /api/v1/events
GET    /api/v1/events/{id}
PATCH  /api/v1/events/{id}
GET    /api/v1/events/export        (CSV)
POST   /api/v1/uploads              (видеофайл для источника типа file)

GET    /api/v1/analytics/overview
GET    /api/v1/analytics/cameras/{id}

GET    /api/v1/cameras/{id}/config
PUT    /api/v1/cameras/{id}/config
```

Real-time:

```text
GET  /api/v1/events/stream
WS   /api/v1/cameras/{id}/telemetry
```

Названия можно изменить, но API должен быть логично организован.

---

# 51. API schemas

Нельзя использовать один schema object на всё.

Разделить:

```text
CameraCreate
CameraUpdate
CameraRead

CameraConfigRead
CameraConfigUpdate

EventRead
EventUpdate

ZoneRead
ZoneCreate
ZoneUpdate
```

---

# 52. Error handling

Все ошибки должны быть нормальными API errors.

Например:

```text
404 camera not found
409 camera already exists
422 invalid zone
503 camera source unavailable
```

Не:

```text
500
Exception
```

для любой проблемы.

---

# 53. Logging

Использовать структурированное logging.

Каждая ошибка камеры должна содержать:

```text
camera_id
camera_name
error_type
timestamp
```

Inference metrics:

```text
model
batch_size
device
latency_ms
```

Event logs:

```text
camera_id
track_id
event_type
```

Никогда не логировать пароли RTSP URL.

---

# 54. Никакого:

```python
except Exception:
    pass
```

Категорически запрещено.

Если exception восстановим:

```python
logger.exception(...)
recover()
```

Если recover невозможен:

```text
camera status = ERROR
```

Но exception нельзя молча проглатывать.

---

# 55. Configuration

Все настройки должны быть централизованы.

Например:

```text
APP_ENV
DATABASE_URL
REDIS_URL

MODEL_PERSON_PATH

INFERENCE_DEVICE
INFERENCE_BATCH_SIZE
INFERENCE_MAX_WAIT_MS

DETECTION_CONFIDENCE
PERSON_TRACK_MAX_AGE

TARGET_FPS

EVENT_COOLDOWN_SECONDS
ZONE_ENTER_DWELL_SECONDS
LOITERING_THRESHOLD_SECONDS

SNAPSHOT_ENABLED
SNAPSHOT_PATH

MAX_CAMERAS
```

Использовать:

```text
pydantic-settings
```

Конфигурация не должна иметь побочных эффектов при импорте (печать, создание каталогов).

---

# 56. Dead configuration

Каждый configuration parameter должен иметь реальное применение.

Не создавать десятки:

```text
ZONE_...
TRACK_...
MODEL_...
```

которые нигде не используются.

При добавлении параметра:

1. он должен быть применён;
2. иметь default;
3. быть документирован;
4. быть покрыт тестом, если влияет на behaviour.

---

# 57. Frontend architecture

Категорически не делать огромный:

```text
App.vue
```

В `App.vue` не должно находиться:

```text
все API calls
вся SSE логика
canvas logic
camera logic
analytics logic
event logic
configuration logic
```

App.vue должен быть композиционным root компонентом.

---

# 58. Frontend structure

Пример:

```text
frontend/
└── src/
    ├── app/
    │   ├── router/
    │   ├── providers/
    │   └── App.vue
    │
    ├── views/
    │   ├── MonitoringView.vue
    │   ├── EventsView.vue
    │   ├── AnalyticsView.vue
    │   ├── CamerasView.vue
    │   └── SettingsView.vue
    │
    ├── components/
    │   ├── camera/
    │   ├── events/
    │   ├── analytics/
    │   ├── zone-editor/
    │   ├── layout/
    │   └── ui/
    │
    ├── stores/
    ├── composables/
    ├── api/
    ├── types/
    ├── lib/
    └── styles/
```

---

# 59. Frontend visual concept

Интерфейс предназначен не для разработчика, а для оператора.

Главная цель:

```text
что происходит?
где проблема?
на какой камере?
насколько критично?
что сделать?
```

Не перегружать интерфейс техническими деталями.

---

# 60. Основная страница

Основной экран:

```text
┌──────────────────────────────────────────────────────┐
│ Logo     Мониторинг       События       Аналитика    │
├─────────┬────────────────────────────────────────────┤
│         │                                            │
│ Cameras │           Camera grid                     │
│ Events  │                                            │
│ Stats   │     ┌────────────┐ ┌────────────┐         │
│ Settings│     │ Camera 01  │ │ Camera 02  │         │
│         │     │ LIVE       │ │ LIVE       │         │
│         │     └────────────┘ └────────────┘         │
│         │                                            │
│         └────────────────────────────────────────────┤
│                         Alerts                       │
└──────────────────────────────────────────────────────┘
```

Конкретный layout можно сделать современнее, но принцип должен сохраниться.

---

# 61. Camera Card

Каждая camera card:

```text
camera name
online/offline
FPS
persons count
last update
video
danger zone
line
track IDs
```

При тревоге:

```text
subtle red border
event badge
small animation
```

Не использовать:

```text
мигающий экран
агрессивные flashing elements
неон
```

---

# 62. Operator priority

Использовать визуальную иерархию:

### Critical

Красный.

### Warning

Янтарный/orange.

### Normal

Зелёный.

### Neutral

Серый.

Не строить UI на десяти разных цветах.

---

# 63. Theme

По умолчанию:

```text
LIGHT
```

Dark mode:

```text
graphite / charcoal
```

Никакого синего dark theme.

Не использовать дизайн:

```text
blue cyberpunk
purple neon
glassmorphism
```

Нужен визуал серьёзной industrial/security application.

---

# 64. Suggested visual style

Стиль:

```text
industrial
clean
professional
modern
dense but readable
```

Основа:

```text
warm gray
white
charcoal
black
amber
red
green
```

Тёмная тема:

```text
#0F1110
#171A18
#202420
```

примерные значения, не догма.

Не использовать огромные rounded cards на весь экран.

---

# 65. Typography

Использовать:

```text
Inter
```

или хороший system font stack.

Иерархия:

```text
page title
section title
label
body
metadata
```

Не использовать декоративные шрифты.

---

# 66. Icons

Использовать Lucide.

Не смешивать:

```text
emoji
SVG от разных наборов
FontAwesome
random icon packs
```

---

# 67. Motion

Animation должна быть:

```text
120–200 ms
subtle
functional
```

Использовать animation только для:

```text
panel open
event appearance
status change
hover
loading
```

---

# 68. Camera configuration UI

Должна существовать понятная настройка камеры.

Разделы:

```text
General
Video source
Detection
Danger zone
Exit line
Events
Performance
```

Но скрывать технические настройки по умолчанию.

Например:

```text
Основные настройки
```

и:

```text
Дополнительные настройки
```

---

# 69. Zone editor

Пользователь должен видеть кадр.

Поверх него:

```text
polygon
line
person boxes
```

Возможности:

```text
add point
drag point
delete point
reset zone
save
cancel
```

Работа через canvas/SVG overlay.

Не хранить координаты в пикселях.

---

# 70. Event panel

Событие:

```text
[CRITICAL]

Человек вошёл в опасную зону

Камера:
Склад №2

13:42:15

Track #17
```

Действия:

```text
Подтвердить
Ложная тревога
Подробнее
```

---

# 71. Event detail

Показывать:

```text
snapshot
camera
event type
timestamp
track ID
status
zone
confidence
```

В будущем туда можно добавить:

```text
track timeline
related events
```

Но не перегружать MVP.

---

# 72. Dashboard

Analytics page должна содержать:

```text
Total events
Critical events
False positives
Active cameras
Average events per camera
People detected
```

Графики:

```text
events over time
events by camera
events by type
```

Использовать ECharts.

Не рисовать графики вручную на canvas.

---

# 73. Track timeline

Для человека:

```text
00:00 ─────────────── 00:20
normal
              danger zone
```

Реализовать через отдельный component.

Не смешивать эту логику с CameraCard.

---

# 74. Responsive design

Основное разрешение:

```text
desktop 1280+
```

Также поддержать:

```text
tablet
```

Минимальный mobile support для базовой навигации.

Операторский desktop должен быть приоритетным.

---

# 75. Frontend state

Server data:

```text
TanStack Query
```

UI state:

```text
Pinia
```

Real-time telemetry:

```text
composable/store
```

Не создавать глобальный reactive object на 500 полей.

---

# 76. Frontend performance

Не делать:

```text
rerender всего dashboard
```

при изменении:

```text
одного camera telemetry event.
```

Разделять reactive state по камере.

Использовать:

```text
shallowRef
computed
watch
watchEffect
```

только там, где это действительно необходимо.

---

# 77. Video overlay performance

Не перерисовывать огромный DOM для каждого detection.

Предпочтительно:

```text
video element
+
canvas overlay
```

Canvas:

```text
requestAnimationFrame
```

и хранение telemetry отдельно от video state.

---

# 78. Backend architecture directories

Ожидаемая структура:

```text
backend/
├── pyproject.toml
├── migrations/
├── src/
│   └── app/
│       ├── main.py
│       │
│       ├── api/
│       │   └── v1/
│       │       ├── cameras.py
│       │       ├── events.py
│       │       ├── analytics.py
│       │       └── realtime.py
│       │
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   └── lifecycle.py
│       │
│       ├── application/
│       │   ├── camera_service.py
│       │   ├── event_service.py
│       │   └── analytics_service.py
│       │
│       ├── infrastructure/
│       │   ├── database/
│       │   ├── redis/
│       │   ├── storage/
│       │   └── streaming/
│       │
│       └── schemas/
```

**Общий пакет `shared/`.** Backend и vision worker — разные сервисы, но используют одни и те же доменные модели и контракты. Чтобы не копировать их и не импортировать один сервис из другого, домен выносится в отдельный пакет — участник uv workspace:

```text
shared/
├── pyproject.toml
└── src/
    └── ai_detector_core/
        ├── cameras/        # Camera, CameraStatus, CameraConfig
        ├── people/         # PersonTrack, PersonState, Detection
        ├── zones/          # Zone, Line, нормализованные координаты
        ├── events/         # DomainEvent, EventType, EventStatus, Severity
        ├── telemetry/      # DTO телеметрии и событий для Redis/WebSocket/SSE
        └── ports/          # Protocol-интерфейсы: EventBus, SnapshotStorage и т.п.
```

В `shared/` нет FastAPI, SQLAlchemy, Redis, OpenCV, Ultralytics (§81). Backend и worker зависят от `shared`, друг от друга — нет.

---

# 79. Vision worker structure

Отдельный сервис:

```text
vision-worker/
├── pyproject.toml
└── src/
    └── vision_worker/
        ├── main.py
        ├── config.py
        │
        ├── cameras/
        │   ├── manager.py
        │   ├── session.py
        │   ├── source.py
        │   └── reconnect.py
        │
        ├── pipeline/
        │   ├── scheduler.py
        │   ├── frame_buffer.py
        │   ├── pipeline.py
        │   └── results.py
        │
        ├── inference/
        │   ├── detector.py
        │   ├── person_detector.py
        │   ├── runtime.py
        │   └── adapters/
        │
        ├── tracking/
        │   ├── tracker.py
        │   └── bytetrack_adapter.py
        │
        ├── analytics/
        │   ├── zone_engine.py
        │   ├── line_engine.py
        │   ├── state_machine.py
        │   └── event_engine.py
        │
        └── messaging/
            └── event_bus.py
```

---

# 80. Do not create giant files

Ограничения:

```text
никакого CameraManager на 800 строк
никакого App.vue на 1000+ строк
никакого utils.py на 1500 строк
```

Ориентир:

```text
100–300 строк
```

для обычного файла.

Если файл начинает расти сильно выше:

```text
300–400 строк
```

проверь, не смешивает ли он несколько responsibilities.

---

# 81. Dependency inversion

Core/domain code не должен импортировать:

```text
FastAPI
SQLAlchemy
Redis
OpenCV
Ultralytics
```

Например:

```text
domain/events
```

должен знать о:

```text
DomainEvent
```

но не о:

```text
RedisEventBus
```

---

# 82. Dependency graph

Желаемое направление:

```text
shared (domain + ports)
  ↑
application
  ↑
infrastructure

api
  ↓
application

vision worker
  ↓
shared (domain + ports)
```

Infrastructure не должна определять business rules.

---

# 83. Testing

Обязательно создать:

```text
tests/unit
tests/integration
tests/e2e
```

Минимум unit tests:

```text
point in polygon
line crossing
zone transitions
track lifecycle
event cooldown
state machine
camera config validation
coordinate normalization
loitering dwell
```

---

# 84. Не тестировать нейросеть как black box everywhere

Большая часть бизнес-логики должна тестироваться без модели.

Например:

```text
fake detections
+
fake tracker
+
fake timestamps
```

↓

```text
event engine
```

↓

```text
expected events
```

Так тесты будут:

```text
быстрые
детерминированные
```

---

# 85. Integration tests

Проверить:

```text
API
PostgreSQL
Redis
camera lifecycle
event publishing
```

Docker Compose может использоваться для integration environment.

---

# 86. Frontend tests

Использовать:

```text
Vitest
```

для:

```text
composables
state
utility functions
```

и:

```text
Playwright
```

для нескольких критических flows:

```text
open dashboard
add camera
open camera
configure zone
receive event
ack event
```

Не нужно покрывать Playwright весь UI.

---

# 87. Static analysis

Backend:

```text
ruff
mypy или pyright
pytest
```

Frontend:

```text
eslint
prettier
vue-tsc
vitest
```

CI должна запускать все проверки.

---

# 88. CI

Создать:

```text
.github/workflows/
```

Минимум:

```text
backend quality
frontend quality
tests
docker build
```

Не класть секреты в repository.

---

# 89. Docker

Создать:

```text
docker-compose.yml
```

для локальной разработки.

Сервисы:

```text
frontend
api
vision-worker
postgres
redis
mediamtx
```

при необходимости MediaMTX сделать optional profile.

---

# 90. GPU

Создать возможность запуска vision worker с GPU.

Например:

```text
docker compose
+
NVIDIA Container Toolkit
```

Но CPU fallback должен существовать.

Не заставлять разработчика иметь NVIDIA GPU только чтобы запустить frontend/API.

---

# 91. Health endpoints

API:

```text
/health/live
/health/ready
```

Vision worker должен иметь собственный health/status.

Health status должен различать:

```text
process alive
dependencies ready
camera running
model loaded
GPU available
```

---

# 92. Metrics

Предусмотреть Prometheus-compatible metrics.

Минимум:

```text
camera_fps
camera_latency
inference_latency
inference_batch_size
queue_depth
active_tracks
events_total
false_positives_total
camera_reconnects_total
```

Не строить пока полноценную observability platform.

Достаточно заложить основу.

---

# 93. Performance architecture

Главные принципы оптимизации:

### 1.

Не делать inference на каждом доступном кадре любой ценой.

### 2.

Использовать bounded queues.

### 3.

Использовать batching.

### 4.

Разделять capture и inference.

### 5.

Разделять inference и storage.

### 6.

Использовать latest-frame policy.

### 7.

Не кодировать JPEG без необходимости.

### 8.

Не писать каждый кадр в DB.

### 9.

Любые дополнительные тяжёлые модели (если появятся) запускать условно, а не на каждом кадре.

### 10.

Не делать Python loops там, где можно использовать векторизацию/OpenCV/Numpy.

---

# 94. Оптимизация модели

Создать отдельный pipeline:

```text
training
    ↓
evaluation
    ↓
export
    ↓
benchmark
    ↓
production model
```

Поддерживать:

```text
PyTorch
ONNX
```

и возможность:

```text
TensorRT
```

в дальнейшем.

---

# 95. Не оптимизировать вслепую

Перед каждой optimization change измерять:

```text
accuracy
precision
recall
mAP
latency
throughput
VRAM
CPU
RAM
```

Нельзя принимать:

```text
FPS increased
```

как единственную метрику.

---

# 96. Benchmark

Создать:

```text
benchmarks/
```

и сценарий:

```text
1 camera
4 cameras
8 cameras
```

с различным:

```text
FPS
batch size
resolution
device
```

И фиксировать:

```text
capture FPS
inference FPS
end-to-end latency
GPU utilization
CPU utilization
memory
```

Результаты всегда сопровождать описанием оборудования, на котором они получены. Если GPU недоступен, измерять на CPU и прямо писать об этом. Сценарии 4 и 8 камер можно запускать на нескольких копиях одного mp4.

---

# 97. Model registry

Даже в MVP создать каталог:

```text
models/
```

с manifest:

```yaml
name:
version:
task:
format:
classes:
input_size:
created_at:
metrics:
```

Не использовать:

```text
best_final_final2.pt
```

---

# 98. ML training structure

Отдельно:

```text
ml/
├── datasets/
├── preprocessing/
├── training/
├── evaluation/
├── export/
├── benchmarks/
└── configs/
```

Training pipeline не должен импортировать весь backend.

---

# 99. Dataset versioning

Минимально иметь:

```text
dataset version
model version
training config
evaluation report
```

Например:

```text
person-detector
dataset 0.2
model 0.3
```

---

# 100. Dataset rules

Не смешивать разные dataset classes без явного mapping.

Каждый mapping должен находиться в config:

```yaml
source_class:
target_class:
reason:
```

Сохранять информацию о том, какие исходные классы были объединены.

---

# 101. Negative samples

Не удалять изображения только потому, что после remapping они не содержат target objects.

Поддерживать negative samples.

Это особенно важно для уменьшения false positives.

---

# 102. Model configuration

Не hardcode:

```text
confidence = 0.4
```

в коде.

Все threshold:

```text
config
```

но не превращать config в огромный мусор.

---

# 103. Event confidence

Разделять:

```text
detector confidence
event confidence
```

Например:

```text
person confidence = 0.86
```

не означает:

```text
danger event confidence = 0.86
```

Event confidence может учитывать:

```text
track stability
zone geometry
duration
detection confidence
```

---

# 104. False positive workflow

Frontend должен позволять:

```text
NEW
 ↓
ACKNOWLEDGED
```

или:

```text
NEW
 ↓
FALSE_POSITIVE
```

Это должно сохраняться.

В будущем эти labels смогут использоваться для ML evaluation.

---

# 105. Analytics architecture

Не считать всё динамически на каждом запросе.

Простые агрегаты можно считать SQL.

Тяжёлые метрики — заранее агрегировать.

Предусмотреть:

```text
hourly
daily
camera-level
event-type-level
```

но не реализовывать всё сразу.

---

# 106. Local development

Одна команда должна позволять стартовать проект:

```text
docker compose up
```

или:

```text
make dev
```

После запуска должны быть:

```text
frontend
API
database
redis
```

Vision worker может запускаться с mock camera source, если реальной камеры нет.

Для Windows см. §0.6: должен существовать и путь запуска без Docker для приложений.

---

# 107. Mock mode

Очень важная функция.

Создать:

```text
MOCK_CAMERA=true
```

или mock frame source.

Это позволит разработчикам:

```text
запустить проект
без реальной камеры
```

и получать:

```text
synthetic/test frames
```

или prerecorded video.

---

# 108. Example camera

В repository должен быть пример:

```text
sample video
```

или инструкции, как подключить локальный:

```text
.mp4
```

Но большие бинарные видео не должны попадать в git.

---

# 109. Seed data

Создать dev seed:

```text
2–3 test cameras
sample zones
sample events
```

чтобы frontend не был пустым после запуска.

---

# 110. API documentation

FastAPI OpenAPI должно автоматически генерировать документацию.

Дополнительно:

```text
docs/api.md
```

с примерами.

---

# 111. Architecture documentation

Создать:

```text
docs/
├── architecture.md
├── data-flow.md
├── database.md
├── behavior.md
├── api.md
├── deployment.md
├── performance.md
├── ml.md
├── development.md
└── decisions/
```

---

# 112. ADR

Для важных решений создать короткие ADR:

```text
ADR-001 Backend architecture
ADR-002 Vision worker separation
ADR-003 Person tracking
ADR-004 Event bus
ADR-005 Video streaming
ADR-006 Inference runtime
```

---

# 113. Git hygiene

`.gitignore` должен исключать:

```text
node_modules
__pycache__
.pytest_cache
.env
*.db
*.log
dist
build
.idea
.vscode
*.pt
*.onnx
```

если модели не должны храниться в Git.

Если модели нужно хранить — использовать отдельное artifact/model storage или Git LFS.

---

# 114. Secrets

Никогда:

```text
API_KEY = "..."
PASSWORD = "..."
RTSP_PASSWORD = "..."
```

в коде.

Использовать:

```text
.env
secret manager
environment variables
```

Не выводить credentials в logs.

Если пользователь передаёт URL:

```text
rtsp://user:password@camera
```

логировать:

```text
rtsp://***:***@camera
```

или только host.

---

# 115. Security basics

Даже без полноценной auth системы:

* validate camera URLs;
* ограничить поддерживаемые protocols;
* не разрешать произвольные опасные filesystem paths;
* не выполнять shell commands от пользовательского ввода;
* не логировать secrets;
* корректно валидировать upload/config values;
* для загрузки видео ограничить размер и расширения, сохранять файл под сгенерированным именем;
* настроить CORS на конкретные origin'ы из конфигурации, не `*`;
* подготовить API к authentication middleware в будущем.

---

# 116. Authentication

Полную систему пользователей сейчас не реализовывать, если это не требуется для текущего MVP.

Но API architecture должна позволять позже добавить:

```text
JWT / OAuth2 / SSO
```

без изменения domain layer.

---

# 117. Internationalization

Основной язык интерфейса:

```text
Russian
```

Но все пользовательские строки не должны быть разбросаны по сотням компонентов.

Создать abstraction:

```text
i18n
```

Даже если на первом этапе существует только `ru`.

---

# 118. Accessibility

Поддерживать:

```text
keyboard navigation
focus states
semantic buttons
ARIA where needed
color contrast
```

Не использовать цвет как единственный способ показать состояние.

---

# 119. UX rule

Каждая критическая операция должна давать feedback:

```text
loading
success
error
```

Не оставлять кнопку в состоянии:

```text
ничего не произошло
```

после клика.

---

# 120. Error UX

Если камера offline:

Не:

```text
500 Internal Server Error
```

а:

```text
Камера недоступна

Последняя попытка подключения:
13:42

Повторное подключение...
```

---

# 121. Loading UX

Использовать:

```text
skeleton
spinner
empty states
```

но не перегружать анимациями.

---

# 122. Empty states

Например:

```text
Камер пока нет

Добавьте первую камеру,
чтобы начать мониторинг.
```

Events:

```text
Новых событий нет.
```

Analytics:

```text
Недостаточно данных для статистики.
```

---

# 123. Frontend routing

Минимально:

```text
/monitoring
/events
/analytics
/cameras
/settings
```

Главный экран:

```text
/monitoring
```

---

# 124. Camera focus page

При клике на camera card:

```text
/cameras/{cameraId}
```

Показывать:

```text
large live view
people
danger zone
line
events
FPS
status
configuration shortcut
```

---

# 125. Camera add flow

Минимальный wizard:

```text
Camera name
Source type
Source URL / загрузка видеофайла
Test connection
Save
```

Не требовать от оператора технических знаний.

---

# 126. Camera status

Карточка должна визуально показывать:

```text
LIVE
CONNECTING
OFFLINE
ERROR
```

и:

```text
last frame
FPS
persons
```

---

# 127. Real-time telemetry schema

Не отправлять на frontend весь Python object graph.

Сделать компактный DTO:

```json
{
  "camera_id": "...",
  "timestamp": "...",
  "frame_id": 1234,
  "persons": [
    {
      "track_id": 17,
      "bbox": [0.32, 0.18, 0.47, 0.72],
      "confidence": 0.91,
      "state": "IN_DANGER_ZONE"
    }
  ]
}
```

Coordinates preferably normalized.

---

# 128. Event delivery

Frontend должен получать только необходимые данные.

Например:

```json
{
  "id": "...",
  "camera_id": "...",
  "type": "PERSON_ENTERED_DANGER_ZONE",
  "severity": "critical",
  "track_id": 17,
  "timestamp": "...",
  "snapshot_url": "..."
}
```

---

# 129. Do not serialize internal objects directly

Не делать:

```python
return vars(camera)
```

или:

```python
return internal_model.__dict__
```

Создавать explicit schemas.

---

# 130. Performance budgets

Добавить документ:

```text
docs/performance.md
```

с target values.

Начальные ориентиры:

```text
API ordinary request < 200 ms
event delivery < 300 ms
operator UI remains responsive
camera pipeline should not accumulate unlimited backlog
```

CV metrics должны зависеть от hardware.

Не обещать:

```text
30 FPS for any GPU
```

---

# 131. Memory safety

Следить за:

```text
unbounded queues
frame copies
large numpy arrays
JPEG accumulation
worker leaks
```

Любой buffer:

```text
bounded
```

если он связан с live video.

---

# 132. Numpy/OpenCV

Использовать:

```text
numpy arrays
```

разумно.

Не создавать множество дополнительных copies:

```python
frame.copy()
frame.copy()
frame.copy()
```

без необходимости.

Benchmark memory allocations на critical path.

---

# 133. GPU memory

Модели должны загружаться один раз на worker.

Не делать:

```text
load model
predict
delete model
```

на каждый запрос/кадр.

---

# 134. Model lifecycle

При запуске worker:

```text
load model
warmup
health check
ready
```

При смене модели:

```text
load new model
validate
warmup
switch
```

не разрушая весь worker заранее.

---

# 135. Worker architecture

Worker должен иметь:

```text
Supervisor
```

который отвечает за:

```text
camera sessions
inference scheduler
event bus
storage writer
health
```

Но Supervisor не должен содержать всю бизнес-логику.

---

# 136. State machine

Для камер и людей использовать явные transitions.

Не:

```python
if a:
    state = "x"
if b:
    state = "y"
if c:
    state = "x"
```

когда можно формализовать state transitions.

---

# 137. Time-based rules

Все event rules должны иметь:

```text
dwell time
cooldown
grace period
```

конфигурируемыми параметрами.

Например:

```text
zone enter confirmation = 300 ms
event cooldown = 5 sec
```

Значения — default, но не hardcode.

---

# 138. Noise suppression

Для зоны и линии предусмотреть:

```text
minimum track age
minimum detection confidence
temporal smoothing
hysteresis
```

Чтобы человек, находящийся ровно на границе зоны, не создавал:

```text
enter
exit
enter
exit
```

20 раз в секунду.

---

# 139. Event deduplication

Добавить:

```text
event fingerprint
```

или другую защиту от duplicate events.

Например:

```text
camera
+
track
+
event type
+
time window
```

---

# 140. Snapshot strategy

Snapshot делать:

```text
event-triggered
```

а не:

```text
every frame
```

Можно дополнительно хранить:

```text
before event
event
after event
```

позже.

Сейчас достаточно event snapshot.

---

# 141. Scalability target

Архитектура должна быть рассчитана минимум на:

```text
1–8 cameras
```

на одной машине для MVP.

Но не кодировать:

```text
MAX_CAMERAS = 4
```

как архитектурное ограничение.

---

# 142. Horizontal scaling

В будущем:

```text
API x N
Vision Worker x N
PostgreSQL
Redis
Media gateway
```

должно быть возможным.

То есть FastAPI не должен хранить critical runtime state в memory.

---

# 143. GPU scaling

При нескольких GPU:

```text
worker-gpu-0
worker-gpu-1
```

каждый worker может обрабатывать собственный набор камер.

В будущем может появиться:

```text
camera assignment
```

без изменения domain model.

---

# 144. Camera assignment

Не реализовывать сложный scheduler в MVP.

Но заложить:

```text
worker_id / assignment
```

в будущем.

---

# 145. Queue overload strategy

Если inference overload:

```text
не увеличивать очередь бесконечно.
```

Вместо:

```text
latency = 10 sec
```

использовать:

```text
drop old frames
```

и отображать:

```text
degraded performance
```

в system health.

---

# 146. Graceful shutdown

При shutdown:

```text
stop accepting commands
stop new frames
flush events
save runtime state if needed
stop camera sources
close DB
close Redis
shutdown
```

Не бросать все daemon threads без cleanup.

---

# 147. No hidden magic

Не использовать:

```text
global mutable dictionaries
```

в качестве скрытой базы данных.

Например не:

```python
CAMERAS = {}
EVENTS = {}
TRACKS = {}
```

как central architecture.

---

# 148. No magical global singleton

Singleton допустим только там, где он действительно нужен, и лучше через dependency injection/lifecycle.

Не делать:

```python
global manager
global detector
global db
global event_bus
```

без объяснения.

---

# 149. Dependency injection

FastAPI DI использовать для:

```text
DB session
services
repositories
event publishing
```

Vision worker использовать explicit dependency construction.

Не применять dependency injection как самоцель.

---

# 150. Code style

Python:

```text
PEP 8
type hints
ruff
docstrings for public APIs
```

Предпочтительно:

```python
class
    clear names
```

а не:

```python
do()
process()
run()
handle()
```

без контекста.

---

# 151. Any

Не злоупотреблять:

```python
Any
```

Если используется:

```text
обосновать
```

---

# 152. Dictionaries

Не передавать между слоями:

```python
Dict[str, Any]
```

везде.

Использовать:

```text
Pydantic models
dataclasses
TypedDict
Enums
```

по назначению.

---

# 153. Frontend TypeScript

Не использовать:

```ts
any
```

по умолчанию.

Типы API должны соответствовать backend schemas.

Можно генерировать frontend API types из OpenAPI, если это не создаёт излишней сложности.

Предпочтительно иметь единый contract.

---

# 154. API contract

Создать:

```text
OpenAPI schema
```

и использовать его как contract.

Frontend API client не должен вручную дублировать десятки incompatible interfaces.

---

# 155. Date/time

Backend:

```text
UTC
```

Frontend:

```text
local display timezone
```

Все database timestamps — timezone-aware.

---

# 156. IDs

Использовать UUID:

```text
camera_id
event_id
zone_id
snapshot_id
```

Track ID:

```text
integer
```

или UUID в пределах camera session.

Для UI обычно удобно:

```text
Track #17
```

---

# 157. Auditability

Для событий сохранять:

```text
created_at
status
acknowledged_at
false_positive_at
```

и при необходимости:

```text
operator_id
```

после появления authentication.

---

# 158. What NOT to implement now

Не пытаться одновременно реализовать:

```text
face recognition
person re-identification
multi-camera identity
complex RBAC
mobile app
cloud deployment
Kubernetes
microservices for every class
Kafka
feature store
LLM agent
fully automatic model retraining
object detection (коробки, паллеты и т.п.)
carrying detection
pose estimation
object tracking
```

Это архитектурно возможно в будущем, но сейчас не нужно.

---

# 159. Не делать microservices ради microservices

Сервисы должны быть:

```text
api
vision-worker
frontend
database
redis
media gateway
```

Этого достаточно.

Не создавать отдельный service для:

```text
zone engine
tracking
events
analytics
```

если для этого нет реальной необходимости.

Внутри vision worker они являются модулями.

---

# 160. MVP vertical slice

Сначала добиться полностью работающего минимального vertical slice:

```text
camera
 ↓
frame
 ↓
person detection
 ↓
person tracking
 ↓
danger zone
 ↓
event
 ↓
database
 ↓
realtime
 ↓
frontend notification
```

Это должно работать end-to-end.

Только после этого добавлять:

```text
line
snapshot
analytics
loitering
```

---

# 161. Milestone 1 — architecture

Перед большим объёмом кода создать:

```text
docs/behavior.md
docs/architecture.md
docs/data-flow.md
docs/database.md
```

и структуру каталогов.

Не писать 5000 строк кода до проверки архитектуры. После этого milestone — остановка и показ человеку (§0.7).

---

# 162. Milestone 2 — infrastructure

Поднять:

```text
PostgreSQL
Redis
FastAPI
Frontend
Vision worker
```

Проверить:

```text
health
DB connection
Redis connection
API
frontend
```

---

# 163. Milestone 3 — camera

Реализовать:

```text
local mp4
camera create
camera start
camera stop
camera status
```

Добавить mock/sample source.

---

# 164. Milestone 4 — person detection

Подключить detector.

Результат:

```text
person detections
```

Добавить visualization.

---

# 165. Milestone 5 — person tracking

Добавить:

```text
PersonTracker
```

И проверить:

```text
stable track IDs
temporary missed detection
track expiration
```

Unit tests обязательны.

---

# 166. Milestone 6 — danger zone

Добавить:

```text
zone
normalized coordinates
state transition
event generation
```

---

# 167. Milestone 7 — real-time

Добавить:

```text
Redis event bus
SSE
WebSocket telemetry
```

и frontend live update.

---

# 168. Milestone 8 — snapshots

Добавить:

```text
snapshot storage
event snapshot
frontend event detail
```

---

# 169. Milestone 9 — line

Добавить:

```text
line
crossing detection
event
```

---

# 170. Milestone 10 — dashboard

Добавить:

```text
event statistics
camera statistics
timeline
```

---

# 171. Milestone 11 — loitering и экспорт

После стабильной основной pipeline:

```text
loitering
экспорт событий в CSV
```

---

# 172. Milestone 12 — optimization

Только после функциональной стабильности.

Измерить:

```text
latency
FPS
GPU
CPU
RAM
queue depth
```

Затем оптимизировать.

---

# 173. Agent workflow

Работай следующим образом:

```text
1. Inspect
2. Design
3. Implement
4. Run
5. Test
6. Measure
7. Refactor
8. Document
```

После каждого milestone:

```text
run tests
run linters
run build
```

Если обнаружил ошибку — исправляй её, а не продолжай строить новые функции поверх сломанной базы.

---

# 174. Important rule

Не генерируй фиктивный код ради закрытия TODO.

Плохо:

```python
def process_camera():
    pass
```

Плохо:

```python
return {"status": "ok"}
```

если функциональность реально ещё не реализована.

Если функция не нужна сейчас:

```text
не создавать её.
```

Если abstraction нужна архитектурно:

```text
создать минимальный реальный interface
```

---

# 175. Important rule

Не создавать 30 абстракций до появления первой работающей функции.

Архитектура должна быть:

```text
modular
but practical
```

---

# 176. Important rule

Не переписывать одну проблему в другую.

Например:

```text
CameraManager 800 lines
```

нельзя исправлять созданием:

```text
MegaCameraService 900 lines
```

---

# 177. Important rule

Не использовать нейросеть как замену архитектуре.

Если есть сложный subsystem:

```text
tracking
event processing
camera lifecycle
```

сначала спроектировать interface и data flow, затем кодировать.

---

# 178. Important rule

Каждый subsystem должен иметь собственную ответственность.

Например:

```text
CameraSource
```

не должен знать про:

```text
danger zones
```

`DangerZoneEngine` не должен знать про:

```text
PostgreSQL
```

`EventRepository` не должен знать про:

```text
YOLO
```

---

# 179. Error recovery

Система должна быть resilient.

Например:

### Detector crash

Не валить API.

### Camera disconnect

Не валить worker.

### Redis unavailable

Система должна корректно сигнализировать degraded mode.

### PostgreSQL unavailable

API сообщает unavailable; runtime не должен сразу уничтожать inference process, если можно безопасно продолжить и позднее отправить данные.

---

# 180. Offline mode

Для MVP предусмотреть:

```text
video file
```

как полноценный source.

Это необходимо для:

```text
testing
demo
training
benchmark
debugging
```

---

# 181. Deterministic test mode

Нужен режим:

```text
TEST_MODE
```

с фиксированными:

```text
timestamps
sample detections
```

чтобы event engine тестировался детерминированно.

---

# 182. Developer experience

Команда должна понимать проект после открытия repository.

README должен содержать:

```text
What is this?
Architecture
Quick start
Environment
Run
Testing
Camera setup
Models
Development workflow
```

---

# 183. No huge generated comments

Не писать в каждый файл:

```text
# This file was generated by AI...
```

или длинные объяснения очевидных строк.

Комментарии объясняют:

```text
why
```

а не:

```text
what
```

---

# 184. No fake enterprise terminology

Не использовать классы:

```text
EnterpriseVisionOrchestratorManagerFactory
```

если они ничего не дают.

Названия должны быть короткими:

```text
CameraSession
PersonTracker
EventEngine
ZoneEngine
```

---

# 185. Expected final repository

В результате должен получиться примерно такой repository:

```text
ai-detector/
│
├── backend/
├── vision-worker/
├── frontend/
├── shared/
├── ml/
├── models/
├── tests/
├── docs/
├── docker/
├── benchmarks/
│
├── docker-compose.yml
├── pyproject.toml       # uv workspace: backend, vision-worker, shared
├── .env.example
├── .gitignore
├── Makefile
├── PROGRESS.md
└── README.md
```

---

# 186. Completion criteria

Проект считается успешно собранным, когда:

```text
✓ backend starts
✓ frontend starts
✓ database starts
✓ redis starts
✓ worker starts
✓ sample video starts
✓ person detection works
✓ person tracking works
✓ danger zone works
✓ event is generated
✓ event reaches frontend
✓ event is persisted
✓ snapshot can be stored
✓ camera can stop/restart
✓ tests pass
✓ frontend builds
✓ backend lint passes
✓ frontend typecheck passes
```

---

# 187. Quality gate

Перед завершением каждого milestone:

```text
pytest
ruff
mypy/pyright
npm run lint
npm run typecheck
npm run build
```

Ошибки исправить.

Не писать:

```text
"tests skipped because environment..."
```

если можно устранить проблему.

---

# 188. Performance gate

Перед объявлением системы «оптимизированной»:

собрать benchmark:

```text
1 camera
4 cameras
8 cameras
```

Для каждой конфигурации записать:

```text
input FPS
processed FPS
end-to-end latency
inference latency
batch size
GPU utilization
VRAM
CPU
RAM
queue depth
```

На том оборудовании, которое реально доступно (§0.6). Если GPU нет, в отчёте GPU-столбцы помечаются как «не измерялось», а не заполняются оценками.

---

# 189. Architecture gate

Перед завершением проверить:

```text
Can FastAPI run with multiple workers?
Can vision worker run separately?
Can person detector be replaced?
Can tracker be replaced?
Can PostgreSQL be replaced?
Can local snapshot storage be replaced?
Can video source be replaced?
Can another frontend consume API?
```

Если ответ «нет» из-за искусственной связанности — исправить архитектуру.

---

# 190. Scalability gate

Проверить:

```text
1 camera
4 cameras
8 cameras
```

и убедиться, что добавление камеры не требует:

```text
new code branch
new global variable
new hardcoded ID
```

---

# 191. Code review gate

Перед завершением провести самостоятельный code review.

Проверить:

```text
monolithic files
duplicate logic
dead code
unused settings
global state
swallowed exceptions
unbounded queues
blocking DB calls
blocking inference
race conditions
incorrect timestamps
resource leaks
```

---

# 192. Architecture red flags

Если увидишь:

```text
Manager
Utils
Helpers
Service
```

файл на:

```text
800+ lines
```

с большим количеством unrelated methods — остановись и раздели его.

---

# 193. Особое внимание к concurrency

У проекта одновременно работают:

```text
camera capture
inference
tracking
storage
API
real-time notifications
frontend
```

Проверять:

```text
race conditions
locks
queues
thread safety
async boundaries
```

---

# 194. Async rule

Не использовать async только ради моды.

CPU/GPU-heavy функции:

```text
sync
thread/process/worker
```

I/O:

```text
async
```

Разделить.

---

# 195. Process architecture

Для production-like запуска:

```text
API process
Vision worker process(es)
```

Web API workers можно масштабировать отдельно.

Inference не должен дублироваться при простом масштабировании API processes.

---

# 196. Model loading

Критически важно:

Если запустить:

```text
4 FastAPI workers
```

не должно получиться:

```text
4 copies of YOLO model
```

только потому, что модель была загружена при import.

Модель живёт в vision worker.

---

# 197. Browser data separation

Frontend должен разделять:

```text
video state
analytics state
event state
camera config state
```

Не хранить всё одним giant object.

---

# 198. Operator-first design rule

Всегда спрашивай про UI:

```text
Может ли оператор понять это за 1–2 секунды?
```

Если нет — упростить.

---

# 199. Technical-first design rule

Всегда спрашивай про backend:

```text
Можно ли заменить этот компонент без переписывания соседних компонентов?
```

Если нет — добавить abstraction на boundary.

---

# 200. Product boundary

Текущая версия должна быть:

```text
MVP+
```

не полноценным enterprise SaaS.

Она должна содержать:

```text
рабочую основную функцию
+
чистую архитектуру
+
основу масштабирования
```

но не 50 недоделанных функций.

---

# 201. Целевой набор функций

Система должна обеспечивать:

```text
✓ несколько камер одновременно
✓ person detection
✓ person tracking
✓ danger zone
✓ exit line
✓ события: вход в зону, пересечение линии, долгое нахождение в зоне
✓ snapshots
✓ подтверждение события (ACK)
✓ ложная тревога
✓ dashboard (показатели камеры, временной ряд, track timeline)
✓ analytics
✓ экспорт событий в CSV
✓ batch inference
✓ operator-oriented UI
```

Поведение и значения по умолчанию описаны в §0.3.

---

# 202. First implementation

Начни с:

```text
repository structure
pyproject (uv workspace)
frontend project
docker-compose
database
redis
API
worker
```

После этого:

```text
health check
sample camera
person detection
person tracking
zone
event
frontend
```

---

# 203. Final instruction to the agent

Не пытайся впечатлить количеством кода.

Мне нужен проект, в котором через несколько месяцев другой разработчик сможет открыть:

```text
camera.py
tracker.py
zone_engine.py
event_engine.py
```

и понять код без чтения всего repository.

Мне нужен проект, где:

```text
new camera source
```

добавляется через:

```text
FrameSource
```

а не через переписывание `CameraManager`.

Мне нужен проект, где:

```text
new detection model
```

добавляется через:

```text
Detector adapter
```

а не через изменение десяти файлов.

Мне нужен проект, где:

```text
new event type
```

добавляется через:

```text
EventEngine + rule
```

а не через изменение capture/inference/storage/UI одновременно.

Мне нужен проект, который сначала **корректный**, потом **поддерживаемый**, и только после этого **максимально быстрый**.

Не оптимизируй то, что ещё не измерено.

Не усложняй то, что пока не требует сложности.

Не создавай код, который выглядит профессионально, но невозможно понять.

Создай реально работающую основу для дальнейшего развития проекта.

---

# 204. Отчёт по завершении этапа

В конце каждого milestone (и в конце всей работы) выдай короткий отчёт:

```text
что сделано
что запущено и проверено (команды и результат)
что НЕ проверялось и почему
принятые решения (со ссылками на docs/decisions/)
известные проблемы
следующий шаг
```

Не пиши «всё работает», если проверка не запускалась.
