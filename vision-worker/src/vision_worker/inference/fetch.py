"""Explicit weight download command. Verifies a temporary file before atomic publication."""

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

import httpx

from vision_worker.inference.manifest import read_manifest, weights_path


def fetch(path: Path) -> Path:
    manifest = read_manifest(path)
    target = weights_path(path, manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, suffix=".download")
    temporary = Path(name)
    try:
        digest = hashlib.sha256()
        with (
            os.fdopen(descriptor, "wb") as output,
            httpx.stream(
                "GET", manifest.download_url, follow_redirects=True, timeout=120
            ) as response,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes():
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != manifest.sha256:
            raise ValueError("downloaded weights sha256 mismatch")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def run() -> None:
    parser = argparse.ArgumentParser(description="Download and verify person model weights")
    parser.add_argument(
        "manifest", nargs="?", type=Path, default=Path("models/person-detector/manifest.yaml")
    )
    print(fetch(parser.parse_args().manifest))


if __name__ == "__main__":
    run()
