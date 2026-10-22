"""Bound multipart bodies before Starlette spools them to temporary disk.

The file-specific limit still lives in LocalUploadStorage. This outer cap also
bounds ignored parts and works without Content-Length (chunked requests).
MultiPartException deliberately lets Starlette close every partial spool file.
"""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_ALLOWANCE_BYTES = 1024 * 1024


class UploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_file_bytes: int) -> None:
        self.app = app
        self.limit = max_file_bytes + MULTIPART_ALLOWANCE_BYTES

    @staticmethod
    def rejection() -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "UPLOAD_TOO_LARGE", "message": "Upload request body is too large"}},
            status_code=413,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/api/v1/uploads"
        ):
            await self.app(scope, receive, send)
            return
        for key, value in scope["headers"]:
            if key.lower() == b"content-length":
                try:
                    length = int(value)
                except ValueError:
                    length = -1
                if length < 0:
                    await JSONResponse(
                        {"error": {"code": "HTTP_ERROR", "message": "Invalid Content-Length"}},
                        status_code=400,
                    )(scope, receive, send)
                    return
                if length > self.limit:
                    await self.rejection()(scope, receive, send)
                    return
        received = 0
        rejected = False

        async def bounded_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    rejected = True
                    raise MultiPartException("Upload body exceeds the configured limit")
            return message

        async def bounded_send(message: Message) -> None:
            if rejected:
                if message["type"] == "http.response.start":
                    await self.rejection()(scope, receive, send)
                return
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
