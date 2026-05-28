# training/scripts/download_datasets.py
import os
import sys

try:
    from roboflow import Roboflow
except ImportError:
    print("Установи roboflow: pip install roboflow")
    sys.exit(1)

# ══════════════════════════════════════════════════════════
# ВСТАВЬ СВОЙ API KEY СЮДА
API_KEY = "qdu7MT4KAgcLlJTp3jAX"
# ══════════════════════════════════════════════════════════

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

rf = Roboflow(api_key=API_KEY)

# ══════════════════════════════════════════════════════════
# Список датасетов для скачивания
# Формат: (workspace, project, version, описание)
#
# ВАЖНО: version нужно уточнить на странице датасета!
# Зайди на страницу → "Versions" tab → посмотри какая последняя
# Или нажми "Download Dataset" → "Show download code" →
# там будет написано project.version(N)
# ══════════════════════════════════════════════════════════

DATASETS = [
    {
        "workspace":   "test2-ilbvs",
        "project":     "warehouse-nmztp",
        "version":     2,          # ← уточни на странице!
        "description": "Warehouse objects (boxes, pallets, shelves)",
    },
    {
        "workspace":   "getafix-technologies",
        "project":     "pallet-detection-atgxn",
        "version":     2,          # ← уточни на странице!
        "description": "Pallet detection",
    },
    {
        "workspace":   "railway-wheels-quqpp",
        "project":     "forklift-onmnx",
        "version":     1,          # ← уточни на странице!
        "description": "Forklift detection",
    },
    {
        "workspace":   "nicholas-nge",
        "project":     "carrying",
        "version":     7,          # ← уточни на странице!
        "description": "People carrying objects",
    },
]


def download_all():
    print(f"API Key: {API_KEY[:8]}...")
    print(f"Output:  {os.path.abspath(OUTPUT_DIR)}")
    print()

    success = 0
    failed  = 0

    for ds in DATASETS:
        ws   = ds["workspace"]
        proj = ds["project"]
        ver  = ds["version"]
        desc = ds["description"]

        print(f"{'='*60}")
        print(f"Датасет: {desc}")
        print(f"  {ws}/{proj} v{ver}")
        print(f"{'='*60}")

        save_dir = os.path.join(OUTPUT_DIR, proj)

        try:
            project = rf.workspace(ws).project(proj)

            # покажем доступные версии
            print(f"  Проект найден: {project.name}")
            print(f"  Тип: {project.type}")

            dataset = project.version(ver).download(
                model_format="yolov8",
                location=save_dir,
                overwrite=False,
            )

            print(f"Скачано в: {save_dir}")
            success += 1

        except Exception as e:
            error_msg = str(e)
            print(f"Ошибка: {error_msg}")

            if "404" in error_msg or "not found" in error_msg.lower():
                print()
                print(f"  ╔══════════════════════════════════════════╗")
                print(f"  ║  Версия {ver} не найдена!                ║")
                print(f"  ║  Попробуй другой номер версии.          ║")
                print(f"  ║                                          ║")
                print(f"  ║  Как узнать правильную версию:           ║")
                print(f"  ║  1. Зайди на страницу датасета           ║")
                print(f"  ║  2. Нажми 'Download Dataset'             ║")
                print(f"  ║  3. Выбери 'YOLOv8'                      ║")
                print(f"  ║  4. Нажми 'Show download code'           ║")
                print(f"  ║  5. Посмотри project.version(N)          ║")
                print(f"  ╚══════════════════════════════════════════╝")
                print()

                # пробуем найти доступные версии
                print(f"  Пробую найти доступные версии...")
                for try_ver in [1, 2, 3, 4, 5]:
                    try:
                        project.version(try_ver)
                        print(f"Версия {try_ver} существует!")
                    except Exception:
                        pass

            failed += 1

        print()

    print(f"{'='*60}")
    print(f"Итого: {success} скачано, {failed} ошибок")
    print(f"{'='*60}")

    if failed > 0:
        print()
        print("Для датасетов с ошибками:")
        print("  1. Зайди на страницу датасета в браузере")
        print("  2. Нажми 'Download Dataset' → 'YOLOv8'")
        print("  3. 'Show download code' → скопируй номер версии")
        print("  4. Исправь version в этом скрипте")
        print("  5. Запусти снова")


if __name__ == "__main__":
    download_all()