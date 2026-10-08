# ADR-006. Inference runtime

Статус: принято (Milestone 1)

Детектор — за интерфейсом `PersonDetector`; конкретные библиотеки только в `inference/adapters/` (`ultralytics_adapter`, `onnx_runtime_adapter`, `scripted_adapter`). По умолчанию — Ultralytics YOLO класса nano на CPU (`INFERENCE_DEVICE=auto` выбирает CUDA при наличии), только класс person. Ultralytics распространяется под AGPL-3.0: для учебного проекта и демонстрации это приемлемо, для production лицензию нужно пересмотреть или перейти на ONNX-модель с другой лицензией через тот же интерфейс. TensorRT — только после измерений (Milestone 12).

**Почему:** Бизнес-логика не знает о библиотеке; смена модели или runtime затрагивает один adapter.
