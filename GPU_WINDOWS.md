# NVIDIA GPU: Windows, M15

## Переключение с M14 CPU на RTX 3060

Драйвер NVIDIA должен видеть карту через `nvidia-smi`. Для RTX 3060 12 ГБ и сообщённого драйвера616.92 выбран **PyTorch2.14.1+cu130 / torchvision0.29.1+cu130 (CUDA runtime13.0)**. Это закреплённая пара из официального индекса PyTorch, не установка случайного latest. CUDA13.4 в nvidia-smi не означает, что Python-пакет обязан иметь тот же номер. Дополнительный CUDA Toolkit для готовых wheels не нужен; драйвер NVIDIA нужен.

Нужны **uv>=0.13.5**, Node из START_WINDOWS.md и запущенный Docker Desktop для PostgreSQL/Redis. Проверка uv: `uv --version`. Старый uv обновите тем же способом, которым он установлен (standalone: `uv self update`; pip: `python -m pip install --upgrade uv`). Из корня проекта:

```powershell
.\start.cmd --profile cuda
```

Первый переход загружает большие CUDA-пакеты (несколько ГБ, нужны сеть и свободный диск). CPU-сборка заменяется в локальном `.venv`, не устанавливайте поверх неё torch вручную. До успешного завершения не запускайте второй экземпляр установки.

После успешного запуска/`--setup-only` выбор сохраняется в **`.runtime-profile.json`**, и дальше достаточно:

```powershell
.\start.cmd
```

Отсутствующий профиль по умолчанию CPU — это не автоопределение. При распаковке в новую папку снова один раз выберите `--profile cuda` либо перенесите свой исправный `.runtime-profile.json`. Файл не содержит паролей и не входит в архив. Повреждённый файл не вызывает тихий fallback: задайте профиль явно.

## Что проверяется

- `uv sync --frozen --no-group cpu --group cuda`: единый versioned lock содержит CPU/CUDA группы, они взаимоисключающие. Нет runtime-подмены lock-файла или pip-overlay.
- Точные версии torch/torchvision и обе метки `+cu130`, runtime13.0.
- `torch.cuda.is_available()`, имя GPU, compute capability и VRAM.
- Настоящие малые matmul и torchvision NMS на `cuda:0`, затем synchronize: обнаруживают ошибки kernels/драйвера/несогласованной пары. После этого обычный worker прогревает YOLO до readiness.
- При неуспехе **нет автоматического CPU fallback**, миграции/Compose up/приложения ещё не запускаются; установленные зависимости могут уже измениться. Последний успешно выбранный профиль сохраняется.
- Профиль задаёт `INFERENCE_DEVICE=cuda` только дочерним процессам launcher. Старый `INFERENCE_DEVICE=cpu/auto` в `.env` не мешает: файл и системные переменные не переписываются. Для прямого ручного запуска worker вне launcher управляйте настройкой сами.

Успешная строка похожа на `Accelerator PASS: cuda | torch 2.14.1+cu130 | torchvision 0.29.1+cu130 | CUDA runtime 13.0 | NVIDIA GeForce RTX 3060 ... | matmul/NMS PASS`.

## Проверка на своём компьютере

После установки, в другом PowerShell из корня (без uv run, который по умолчанию выбирает CPU):

```powershell
.\.venv\Scripts\python.exe scripts\check_accelerator.py --profile cuda
nvidia-smi -l 1
```

Запустите **реальную file/RTSP-камеру с YOLO**, не только mock DEMO-камеру: mock не выполняет нейросеть. В логах/readiness worker должно быть устройство cuda. В Windows Task Manager смотрите график CUDA/Compute, не только3D; WDDM может не показывать память отдельного процесса в nvidia-smi. Низкая средняя загрузка при малой модели/одном потоке/target FPS допустима. Цель — корректная ускоренная обработка, не100%GPU.

GPU ускоряет YOLO; декодирование OpenCV, CPU ByteTrack/scene rules, API/БД/JPEG остаются на CPU. NVDEC, FP16, TensorRT и увеличение batch/FPS в M15 не добавляются. Сначала измерьте реальные FPS/latency/CPU/VRAM; прежние CPU-результаты4/8 камер нельзя переносить на вашу GPU как обещание.

## Возврат на CPU / диагностика

```powershell
.\start.cmd --profile cpu
```

Это устанавливает закреплённые CPU wheels и сохраняет выбор. Существующие `.env`, камеры/события/файлы не удаляются. Перед обновлением всё равно сделайте backup по UPDATE_MILESTONE_15.md.

`--skip-install` **не** отключает accelerator preflight. Для первого переключения его не используйте. Если версии/тип сборки не совпадают, повторите обычную установку нужного профиля.

Ручное `uv sync`/`uv run` без GPU-групп по умолчанию выбирает CPU. Для GPU ручных команд нужны `--no-group cpu --group cuda`; предпочтительно используйте launcher, который помнит выбор. `--all-groups` запрещён взаимным конфликтом. Не используйте `--force`/`--legacy-peer-deps` или независимый pip-install torch как способ обойти lock.

GPU unavailable: проверьте `nvidia-smi`, не скрывает ли GPU переменная CUDA_VISIBLE_DEVICES, перезапуск после обновления драйвера; CPU wheel/другая версия: переустановка профиля. Ошибки DLL/driver/kernel/NMS не игнорируются: сохраните диагностическую строку и worker.log без секретов. Не нужно скачивать сторонние CUDA DLL и копировать их в проект.

## Граница проверки

Здесь нет NVIDIA GPU или Windows. На Linux проверяются реальная CPU-установка/операции/регрессии, отдельная CUDA-установка и корректный отказ без GPU; Windows wheels и хеши присутствуют в lock, план Windows sync проверяется без исполнения Windows-кода. CUDA-ветки оркестрации дополнительно unit-tested с fakes, это не доказательство физической GPU-обработки. Пользовательский запуск M14 на Windows подтверждён пользователем; M15 на RTX3060 нужно подтвердить командами выше. GPU внутри Docker/WSL не настраивается: worker работает нативно на Windows, Docker нужен только БД. Production gates M13 остаются открытыми.
