"""Uploaded video files live under UPLOAD_PATH with generated names only (ADR-012)."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from app.application.errors import UploadRejectedError, UploadTooLargeError


class LocalUploadStorage:
    def __init__(self, root: Path, max_bytes: int, allowed_extensions: list[str]) -> None:
        self._root = root
        self._max_bytes = max_bytes
        self._allowed = frozenset(allowed_extensions)

    def exists(self, ref: str) -> bool:
        # `ref` is already validated against UPLOAD_REF_PATTERN, so it cannot escape root.
        return (self._root / ref).is_file()

    async def save(self, original_name: str, chunks: AsyncIterator[bytes]) -> tuple[str, int]:
        """Stream the upload to disk; return (generated ref, size). Partial files are removed."""
        extension = Path(original_name).suffix.lower()
        if extension not in self._allowed:
            raise UploadRejectedError(f"File type {extension or '(none)'} is not allowed")
        self._root.mkdir(parents=True, exist_ok=True)
        ref = f"{uuid.uuid4().hex}{extension}"
        target = self._root / ref
        partial = target.with_suffix(target.suffix + ".part")
        size = 0
        try:
            async with await anyio.open_file(partial, "wb") as file:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise UploadTooLargeError(f"File is larger than {self._max_bytes} bytes")
                    await file.write(chunk)
            if size == 0:
                raise UploadRejectedError("File is empty")
            await anyio.Path(partial).rename(target)
        except BaseException:
            await anyio.Path(partial).unlink(missing_ok=True)
            raise
        return ref, size
