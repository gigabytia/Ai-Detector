"""ASGI body guard runs before multipart spooling, even for chunked requests."""

import json

import pytest
from starlette.formparsers import MultiPartException
from starlette.types import Message, Receive, Scope, Send

from app.middleware.upload_limit import MULTIPART_ALLOWANCE_BYTES, UploadBodyLimitMiddleware


@pytest.mark.parametrize("announced", [True, False])
async def test_upload_body_is_bounded_before_downstream_reads(announced: bool) -> None:
    consumed = 0
    sends: list[Message] = []
    limit = 10 + MULTIPART_ALLOWANCE_BYTES
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/uploads",
        "headers": [(b"content-length", str(limit + 1).encode())] if announced else [],
    }

    async def receive() -> Message:
        nonlocal consumed
        consumed += 1
        return {"type": "http.request", "body": b"x" * (limit // 2 + 1), "more_body": True}

    async def send(message: Message) -> None:
        sends.append(message)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            for _ in range(5):
                await receive()
        except MultiPartException:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"parser error"})

    await UploadBodyLimitMiddleware(app, 10)(scope, receive, send)
    assert consumed == (0 if announced else 2)
    assert sends[0]["status"] == 413
    assert json.loads(sends[1]["body"])["error"]["code"] == "UPLOAD_TOO_LARGE"


async def test_chunked_multipart_overflow_closes_spooled_files_and_keeps_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile
    from collections.abc import AsyncIterator
    from typing import BinaryIO

    import httpx
    from starlette import formparsers

    from app.core.config import Settings
    from app.main import create_app

    files: list[BinaryIO] = []
    original = tempfile.SpooledTemporaryFile

    def spool(*args: object, **kwargs: object) -> BinaryIO:
        from typing import cast

        file = cast(BinaryIO, original(max_size=1024))
        files.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", spool)
    app = create_app(Settings(_env_file=None, upload_max_bytes=1024))

    async def body() -> AsyncIterator[bytes]:
        yield b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.mp4"\r\n\r\n'
        yield b"x" * (1024 * 1024)
        yield b"x" * 2048
        raise AssertionError("Body must stop being consumed at the cap")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/api/v1/uploads",
            content=body(),
            headers={
                "Content-Type": "multipart/form-data; boundary=test",
                "Origin": "http://localhost:5173",
            },
        )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert files and all(file.closed for file in files)
