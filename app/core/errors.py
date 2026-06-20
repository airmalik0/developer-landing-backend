"""Custom exceptions and the global error handlers.

Every error leaves the API as a consistent JSON envelope:

    {"error": {"type": "...", "message": "...", "details": ...}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("errors")


class AppError(Exception):
    """Base class for application-level errors with an HTTP status code."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "app_error"

    def __init__(self, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class RateLimitExceeded(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limit_exceeded"

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "Too many requests. Please slow down.",
            details={"retry_after_seconds": retry_after},
        )
        self.retry_after = retry_after


def _envelope(error_type: str, message: str, details: object | None = None) -> dict:
    body: dict = {"error": {"type": error_type, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.error_type, exc.message, exc.details),
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("app error: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.error_type, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                "validation_error",
                "Request validation failed.",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Full traceback to the log; safe generic message to the client.
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "Internal server error."),
        )
