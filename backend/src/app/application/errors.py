"""Expected application errors. The API layer maps them to HTTP responses."""


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class UnprocessableError(AppError):
    status_code = 422
    code = "UNPROCESSABLE"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class CameraNotFoundError(NotFoundError):
    code = "CAMERA_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Camera not found")


class CameraNameConflictError(ConflictError):
    code = "CAMERA_ALREADY_EXISTS"

    def __init__(self) -> None:
        super().__init__("Camera with this name already exists")


class CameraLimitReachedError(UnprocessableError):
    code = "CAMERA_LIMIT_REACHED"

    def __init__(self, limit: int) -> None:
        super().__init__(f"Camera limit reached ({limit})")


class InvalidCameraSourceError(UnprocessableError):
    code = "INVALID_CAMERA_SOURCE"


class UploadRejectedError(UnprocessableError):
    code = "UPLOAD_REJECTED"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "UPLOAD_TOO_LARGE"
