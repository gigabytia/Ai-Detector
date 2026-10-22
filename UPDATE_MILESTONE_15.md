# Обновление M14 → M15: закреплённый NVIDIA-профиль

База ca55552 (M14), оригинальная Git-история сохранена. Новый выбор CPU/CUDA в едином uv.lock, preflight пары/реальных kernels, сохраняемый локальный профиль. Новых миграций нет: b6b7cfcd87c5.

1. Остановите API/worker/UI. Сохраните свой `.env`, uploads/snapshots и backup PostgreSQL/Redis. Не удаляйте Docker volumes. Собственные Git-коммиты/изменения сохраняйте отдельно, не заменяйте свою .git вслепую.
2. Распакуйте обновление. В новой папке перенесите свой `.env` и нужные файлы/пути; БД/видео/JPEG ZIP не содержит. Старые package pins frontend не менялись.
3. Проверьте `uv --version` (>=0.13.5), Node и Docker Desktop. Драйвер должен видеть NVIDIA GPU. Дополнительный CUDA Toolkit не требуется для готовых PyTorch wheels.
4. Для RTX3060 выполните из корня ` .\start.cmd --profile cuda `, **без --skip-install**. Затем просто `.\start.cmd`. Подробнее GPU_WINDOWS.md. Для CPU — ` .\start.cmd --profile cpu `.
5. Существующий `.env` не изменяется. Выбор сохраняется отдельно в `.runtime-profile.json` только после успешного полного setup/readiness; этот локальный файл не включён в ZIP. Новый каталог без него по умолчанию CPU.
6. Проверьте Accelerator PASS, READY и YOLO file/RTSP-камеру, nvidia-smi во время обработки. DEMO/mock не создаёт GPU-инференс. Не публикуйте полный .env.

CPU остаётся стандартным профилем для plain uv/CI/Compose; launcher передаёт сохранённую GPU-группу явно. Независимый ручной uv sync без выбора вернёт CPU — следующий обычный launcher снова установит сохранённый CUDA-профиль. --skip-install несовпадение отвергает. Не редактируйте lock и не используйте ручной pip-overlay.

M15 не заявляет проверенную скорость/точность/VRAM на физической RTX3060, native Windows/контейнерную GPU-сертификацию или закрытие M13 production gates. Доказательства и ограничения — docs/qa/m15/README.md. M13/M14 QA исторические, не повторно заявленные GPU-бенчмарки.
