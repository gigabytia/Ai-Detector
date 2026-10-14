# ADR-030. CPU PyTorch и единственная headless-сборка OpenCV

Статус: принято (Milestone 4).

В `uv` для Linux/Windows `torch` и `torchvision` берутся из explicit CPU-индекса PyTorch. Это избавляет CPU-стенд от лишних CUDA-библиотек. Для macOS применяется обычный индекс. CUDA-сборка и GPU-контейнер — будущий этап; запрос `INFERENCE_DEVICE=cuda` без CUDA завершается ошибкой, не маскируется CPU fallback.

Ultralytics требует `opencv-python`, а worker — `opencv-python-headless`; оба пакета публикуют модуль `cv2`. В корневом `override-dependencies` GUI-пакет исключён недостижимым платформенным маркером. Используется один headless `cv2`, без `imshow`. `INFERENCE_THREADS=2` ограничивает CPU-пул PyTorch. `YOLO_CONFIG_DIR=/tmp` позволяет непривилегированному Docker-пользователю записать настройки Ultralytics.
