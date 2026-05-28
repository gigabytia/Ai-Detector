Установка зависимостей:

PyTorch (GPU CUDA 11.8) - если есть NVIDIA:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

PyTorch (CPU) - если без GPU:
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

BACKEND (Можно прямо в pycharm или anaconda prompt)
1) cd C:\[ПУТЬ]\ai-detector\backend

2) python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
или: uvicorn main:app --reload --host 127.0.0.1 --port 8000


FRONTEND (терминал 2)
1) cd C:\[ПУТЬ]\ai-detector\frontend
2) npm run dev

Открыть:
Backend docs: http://127.0.0.1:8000/docs
UI:          http://127.0.0.1:5173