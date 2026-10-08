"""Uniform error envelope: {"error": {"code": ..., "message": ..., "details": ...}}."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, object]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Base class for expected application errors mapped to HTTP responses."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"


def _response(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(mode="json", exclude_none=True),
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _response(exc.status_code, ErrorBody(code=exc.code, message=exc.message))


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"loc": list(item.get("loc", ())), "msg": str(item.get("msg", ""))} for item in exc.errors()
    ]
    return _response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorBody(code="VALIDATION_ERROR", message="Request validation failed", details=details),
    )


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return _response(exc.status_code, ErrorBody(code="HTTP_ERROR", message=str(exc.detail)))


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled error", extra={"path": request.url.path, "error_type": type(exc).__name__}
    )
    return _response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorBody(code="INTERNAL_ERROR", message="Internal server error"),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
