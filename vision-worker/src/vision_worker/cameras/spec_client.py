"""Reads camera specs from the internal API (ADR-002). The worker never touches PostgreSQL."""

import uuid

import httpx
from pydantic import TypeAdapter, ValidationError

from ai_detector_core.cameras.spec import CameraSpec

_SPEC_LIST = TypeAdapter(list[CameraSpec])


class SpecUnavailableError(Exception):
    """API unreachable or answered with an unexpected response."""


class CameraSpecClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def list_enabled(self) -> list[CameraSpec]:
        response = await self._get("/api/v1/internal/worker/cameras")
        try:
            return _SPEC_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise SpecUnavailableError("invalid camera list from API") from exc

    async def get(self, camera_id: uuid.UUID) -> CameraSpec | None:
        """None when the camera no longer exists (deleted)."""
        response = await self._get(f"/api/v1/internal/worker/cameras/{camera_id}", allow_404=True)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        try:
            return CameraSpec.model_validate_json(response.content)
        except ValidationError as exc:
            raise SpecUnavailableError("invalid camera spec from API") from exc

    async def _get(self, path: str, allow_404: bool = False) -> httpx.Response:
        try:
            response = await self._http.get(path)
        except httpx.HTTPError as exc:
            raise SpecUnavailableError(f"API request failed: {type(exc).__name__}") from exc
        if response.is_success or (allow_404 and response.status_code == httpx.codes.NOT_FOUND):
            return response
        raise SpecUnavailableError(f"API answered {response.status_code} for {path}")


def create_api_http_client(base_url: str, token: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(base_url=base_url, headers=headers, timeout=5.0)
