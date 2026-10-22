"""CPU kernels are real; CUDA branches here use explicit fakes, not hardware certification."""

import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import torch
import torchvision

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "accelerator_guard_test", ROOT / "scripts/check_accelerator.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pair(*, runtime: str | None = "13.0", available: bool = True) -> tuple[Any, Any]:
    return SimpleNamespace(
        __version__="2.14.1+cu130",
        version=SimpleNamespace(cuda=runtime),
        cuda=SimpleNamespace(is_available=lambda: available),
    ), SimpleNamespace(__version__="0.29.1+cu130")


def test_real_cpu_pair_matmul_nms(guard: ModuleType) -> None:
    assert "CPU (explicit)" in guard.check("cpu", torch, torchvision)


@pytest.mark.parametrize("profile", ["cpu", "cuda"])
def test_rejects_version_drift(guard: ModuleType, profile: str) -> None:
    t, v = pair()
    v.__version__ = "0.28.0+cu130"
    with pytest.raises(ValueError, match="pair differs"):
        guard.check(profile, t, v)


def test_cpu_build_is_not_a_cuda_profile(guard: ModuleType) -> None:
    with pytest.raises(ValueError, match="requires the locked cu130"):
        guard.check("cuda", torch, torchvision)


def test_no_gpu_is_fail_closed(guard: ModuleType) -> None:
    t, v = pair(available=False)
    with pytest.raises(ValueError, match="no usable NVIDIA GPU"):
        guard.check("cuda", t, v)


def test_cuda_build_is_not_cpu_profile(guard: ModuleType) -> None:
    t, v = pair()
    with pytest.raises(ValueError, match="CPU profile requires CPU"):
        guard.check("cpu", t, v, platform="win32")


@pytest.mark.parametrize("platform", ["darwin", "freebsd"])
def test_cuda_on_unsupported_platform(guard: ModuleType, platform: str) -> None:
    t, v = pair()
    with pytest.raises(ValueError, match="Windows/Linux"):
        guard.check("cuda", t, v, platform=platform)


def test_wrong_cuda_runtime(guard: ModuleType) -> None:
    t, v = pair(runtime="12.6")
    with pytest.raises(ValueError, match="cu130"):
        guard.check("cuda", t, v)


def test_available_but_kernel_failure_not_accepted(guard: ModuleType) -> None:
    t, v = pair()
    t.cuda.get_device_name = lambda _: "fake GPU"
    t.cuda.get_device_capability = lambda _: (8, 6)
    t.cuda.get_device_properties = lambda _: SimpleNamespace(total_memory=12 * 1024**3)
    t.inference_mode = torch.inference_mode

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("no kernel image available")

    t.ones = broken
    with pytest.raises(RuntimeError, match="kernel image"):
        guard.check("cuda", t, v)


def test_uv_default_cpu_and_exclusive_cuda_groups() -> None:
    p = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert p["tool"]["uv"]["default-groups"] == ["dev", "cpu"]
    assert p["tool"]["uv"]["conflicts"] == [[{"group": "cpu"}, {"group": "cuda"}]]
    for group in ["cpu", "cuda"]:
        assert p["dependency-groups"][group] == ["torch==2.14.1", "torchvision==0.29.1"]
    for name in ["torch", "torchvision"]:
        assert {x["group"] for x in p["tool"]["uv"]["sources"][name]} == {"cpu", "cuda"}
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    for name, version in [("torch", "2.14.1+cu130"), ("torchvision", "0.29.1+cu130")]:
        pkg = next(x for x in lock["package"] if x["name"] == name and x["version"] == version)
        assert pkg["source"]["registry"] == "https://download.pytorch.org/whl/cu130"
        assert any("cp312-cp312-win_amd64" in x["url"] for x in pkg["wheels"])
        assert all("hash" in x for x in pkg["wheels"])


def test_worker_cpu_container_explicit_group() -> None:
    text = (ROOT / "docker/worker.Dockerfile").read_text()
    syncs = [line for line in text.splitlines() if line.startswith("RUN uv sync")]
    assert len(syncs) == 2
    assert all("--group cpu" in line for line in syncs)
    assert "astral-sh/uv:0.13.5" in text


def test_cuda_success_reporting_and_device_routing_with_explicit_fakes(guard: ModuleType) -> None:
    t, v = pair()
    routed: list[str] = []
    synced: list[bool] = []
    t.cuda.get_device_name = lambda _: "FAKE RTX 3060 (not physical)"
    t.cuda.get_device_capability = lambda _: (8, 6)
    t.cuda.get_device_properties = lambda _: SimpleNamespace(total_memory=12 * 1024**3)
    t.cuda.synchronize = lambda: synced.append(True)
    t.inference_mode = torch.inference_mode

    def ones(shape: tuple[int, int], *, device: str) -> torch.Tensor:
        routed.append(device)
        return torch.ones(shape)

    def tensor(data: list[Any], *, device: str) -> torch.Tensor:
        routed.append(device)
        return torch.tensor(data)

    t.ones, t.tensor = ones, tensor
    v.ops = torchvision.ops
    result = guard.check("cuda", t, v, platform="win32")
    assert "FAKE RTX 3060" in result and "12.0 GiB" in result
    assert routed == ["cuda:0", "cuda:0", "cuda:0"]
    assert synced == [True]
