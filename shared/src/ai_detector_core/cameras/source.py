"""Camera source references: validation and credential masking.

A source is stored as one URL string:
  rtsp://user:pass@host:554/path   live camera
  upload://<32 hex>.<ext>         uploaded video file (ADR-012)
  mock://<scenario>               synthetic frames (ADR-016)
"""

import re
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit

MAX_SOURCE_URL_LENGTH = 2048
UPLOAD_REF_PATTERN = re.compile(r"^[0-9a-f]{32}\.(mp4|mov|mkv|avi)$")
MOCK_SCENARIO_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

UPLOAD_SCHEME = "upload://"
MOCK_SCHEME = "mock://"
RTSP_SCHEMES = frozenset({"rtsp", "rtsps"})


class SourceType(StrEnum):
    FILE = "file"
    RTSP = "rtsp"
    MOCK = "mock"


class InvalidSourceError(ValueError):
    """The source URL does not match its source type."""


def validate_source_url(source_type: SourceType, url: str) -> str:
    """Return the URL unchanged if it is valid for the type, raise InvalidSourceError otherwise."""
    if not url or len(url) > MAX_SOURCE_URL_LENGTH:
        raise InvalidSourceError("source URL is empty or too long")
    match source_type:
        case SourceType.FILE:
            upload_ref(url)
        case SourceType.MOCK:
            mock_scenario(url)
        case SourceType.RTSP:
            _validate_rtsp(url)
    return url


def upload_ref(url: str) -> str:
    """Extract the generated file name from upload://<ref>. No paths are accepted."""
    ref = url.removeprefix(UPLOAD_SCHEME) if url.startswith(UPLOAD_SCHEME) else ""
    if not UPLOAD_REF_PATTERN.fullmatch(ref):
        raise InvalidSourceError("file source must be upload://<generated name> from /uploads")
    return ref


def mock_scenario(url: str) -> str:
    name = url.removeprefix(MOCK_SCHEME) if url.startswith(MOCK_SCHEME) else ""
    if not MOCK_SCENARIO_PATTERN.fullmatch(name):
        raise InvalidSourceError("mock source must be mock://<scenario name>")
    return name


def _validate_rtsp(url: str) -> None:
    parts = _split(url)
    if parts.scheme not in RTSP_SCHEMES:
        raise InvalidSourceError("only rtsp:// and rtsps:// URLs are supported")
    if not parts.hostname:
        raise InvalidSourceError("RTSP URL must contain a host")
    if any(ch.isspace() for ch in url):
        raise InvalidSourceError("RTSP URL must not contain whitespace")


def _split(url: str) -> SplitResult:
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises on a non-numeric port
    except ValueError as exc:
        raise InvalidSourceError("malformed URL") from exc
    return parts


def mask_source_url(url: str) -> str:
    """Hide credentials: rtsp://user:pass@host/x -> rtsp://***:***@host/x."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid url>"
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rpartition("@")[2]  # keeps the port and IPv6 brackets as written
    return parts._replace(netloc=f"***:***@{host}").geturl()
