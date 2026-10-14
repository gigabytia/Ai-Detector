"""Validated model manifest and weight integrity. No network on worker startup."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ModelManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    backend: Literal["ultralytics"]
    weights: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    download_url: str = Field(pattern=r"^https://")
    input_size: int = Field(ge=32, le=2048, multiple_of=32)
    person_class_id: int = Field(ge=0)
    license: str


def read_manifest(path: Path) -> ModelManifest:
    return ModelManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def weights_path(path: Path, manifest: ModelManifest) -> Path:
    root = path.resolve().parent
    weights = (root / manifest.weights).resolve()
    if not weights.is_relative_to(root):
        raise ValueError("weights must be inside the model directory")
    return weights


def verify_weights(path: Path, manifest: ModelManifest) -> Path:
    weights = weights_path(path, manifest)
    with weights.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest.sha256:
        raise ValueError("model weights sha256 mismatch")
    return weights
