"""Local object storage. Only stdlib; no user paths or image codecs here."""

import os
import re
import stat
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID

KEY = re.compile(r"^snapshots/([0-9a-f-]{36})/(\d{4})/(\d{2})/(\d{2})/([0-9a-f-]{36})\.jpg$")


def snapshot_key(camera_id: UUID, occurred_at: datetime, snapshot_id: UUID) -> str:
    at = occurred_at.astimezone(UTC)
    return f"snapshots/{camera_id}/{at:%Y/%m/%d}/{snapshot_id}.jpg"


def validate_key(key: str) -> None:
    match = KEY.fullmatch(key)
    if match is None:
        raise ValueError("Invalid snapshot object key")
    camera, year, month, day, snapshot = match.groups()
    if str(UUID(camera)) != camera or str(UUID(snapshot)) != snapshot:
        raise ValueError("Noncanonical snapshot UUID")
    date(int(year), int(month), int(day))


class SnapshotStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalSnapshotStorage:
    """Private root shared by API and worker; object keys retain a namespace prefix.

    The logical `snapshots/` prefix maps to root, not root/snapshots. All path
    components are validated and symlinks rejected. The root must not be writable
    by untrusted users; this is not an adversarial shared filesystem sandbox.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = self.root.joinpath(*key.split("/")[1:])
        current = self.root
        for component in path.relative_to(self.root).parts:
            current = current / component
            if current.is_symlink():
                raise ValueError("Symlinks are not allowed in snapshot storage")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Snapshot key escapes storage root")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._path(key)  # recheck after mkdir
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".snapshot-", suffix=".part", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Snapshot is not a regular file")
            return os.fdopen(fd, "rb")
        except BaseException:
            os.close(fd)
            raise

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def expired_keys(self, cutoff: datetime) -> Iterator[str]:
        """Streaming orphan candidate scan, bounded in batches by the API janitor."""
        for path in self.root.rglob("*.jpg"):
            key = "snapshots/" + path.relative_to(self.root).as_posix()
            try:
                safe = self._path(key)
                if safe.is_file() and safe.stat().st_mtime < cutoff.timestamp():
                    yield key
            except (OSError, ValueError):
                continue

    def prune_temporary(self, cutoff: datetime) -> int:
        removed = 0
        for path in self.root.rglob(".snapshot-*.part"):
            try:
                if (
                    not path.is_symlink()
                    and path.resolve().is_relative_to(self.root)
                    and path.is_file()
                    and path.stat().st_mtime < cutoff.timestamp()
                ):
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed
