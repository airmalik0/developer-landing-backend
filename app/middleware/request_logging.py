"""Request-logging middleware.

Logs every request with a correlation id, client IP, status code and latency —
satisfying the "log all requests" requirement — and echoes the id back in the
``X-Request-ID`` response header.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger("request")


def get_client_ip(request: Request) -> str:
    """Resolve the real client IP, honouring the proxy header set by Vercel."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(
                "rid=%s %s %s ip=%s -> 500 (%.1fms)",
                request_id,
                request.method,
                request.url.path,
                get_client_ip(request),
                elapsed,
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "rid=%s %s %s ip=%s -> %s (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            get_client_ip(request),
            response.status_code,
            elapsed,
        )
        response.headers["X-Request-ID"] = request_id
        return response
