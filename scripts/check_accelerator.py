"""Validate the installed, locked PyTorch pair before touching local databases."""

from __future__ import annotations

import argparse
import sys
from typing import Any

TORCH_VERSION = "2.14.1"
TORCHVISION_VERSION = "0.29.1"
CUDA_RUNTIME = "13.0"
CUDA_BUILD = "cu130"


def check(profile: str, torch: Any, vision: Any, *, platform: str = sys.platform) -> str:
    """Small real op proves usable kernels; GPU availability alone is not enough."""
    if profile not in {"cpu", "cuda"}:
        raise ValueError("Unknown accelerator profile.")
    if profile == "cuda" and platform not in {"win32", "linux"}:
        raise ValueError("This CUDA profile supports NVIDIA on Windows/Linux only.")
    tv, vv = str(torch.__version__), str(vision.__version__)
    if tv.split("+")[0] != TORCH_VERSION or vv.split("+")[0] != TORCHVISION_VERSION:
        raise ValueError(
            "PyTorch/torchvision pair differs from the lock; rerun without --skip-install."
        )
    if profile == "cuda":
        if (
            torch.version.cuda != CUDA_RUNTIME
            or not tv.endswith("+" + CUDA_BUILD)
            or not vv.endswith("+" + CUDA_BUILD)
        ):
            raise ValueError("CUDA profile requires the locked cu130 builds, not CPU/other builds.")
        if not torch.cuda.is_available():
            raise ValueError(
                "CUDA build is installed but no usable NVIDIA GPU is available. "
                "Check nvidia-smi/driver and CUDA_VISIBLE_DEVICES; CPU fallback is disabled."
            )
        name = str(torch.cuda.get_device_name(0))
        capability = torch.cuda.get_device_capability(0)
        info = torch.cuda.get_device_properties(0)
        details = (
            f"{name}, compute {capability[0]}.{capability[1]}, "
            f"VRAM {info.total_memory / 1024**3:.1f} GiB"
        )
        device = "cuda:0"
    else:
        if platform in {"win32", "linux"} and (
            torch.version.cuda is not None or not tv.endswith("+cpu") or not vv.endswith("+cpu")
        ):
            raise ValueError("CPU profile requires CPU wheels; rerun without --skip-install.")
        details, device = "CPU (explicit)", "cpu"
    with torch.inference_mode():
        a = torch.ones((16, 16), device=device)
        if float((a @ a)[0, 0].item()) != 16.0:
            raise ValueError("PyTorch matrix smoke check failed.")
        boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 9.0, 9.0]], device=device)
        scores = torch.tensor([0.9, 0.8], device=device)
        if vision.ops.nms(boxes, scores, 0.5).tolist() != [0]:
            raise ValueError("torchvision NMS smoke check failed.")
        if profile == "cuda":
            torch.cuda.synchronize()
    return (
        f"Accelerator PASS: {profile} | torch {tv} | torchvision {vv} | "
        f"CUDA runtime {torch.version.cuda} | {details} | matmul/NMS PASS"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=["cpu", "cuda"])
    args = parser.parse_args()
    try:
        import torch
        import torchvision

        print(check(args.profile, torch, torchvision), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 -- fail closed before infra/apps; no configuration dump
        reason = str(exc) if type(exc) is ValueError else f"{type(exc).__name__}: {str(exc)[:600]}"
        print(
            f"ACCELERATOR STOPPED: {reason} "
            "See GPU_WINDOWS.md. No CPU fallback; .env was not rewritten.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
