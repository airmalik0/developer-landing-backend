"""FastAPI application factory.

Wires together middleware (CORS + request logging), the global error handlers,
the API routers (under ``/api``), the auto-generated Swagger docs, and the static
landing page — all served by this single ASGI app (one Vercel function).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import contact, health, metrics
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"

DESCRIPTION = (
    "Backend service for a developer's landing presentation.\n\n"
    "Full cycle: **validation → rate-limit → AI enrichment → email → response**.\n"
    "AI runs on Anthropic Claude Haiku with a graceful fallback."
)


def create_app() -> FastAPI:
    setup_logging()
    logger = get_logger("main")
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Middleware — added first runs innermost; CORS added last → outermost.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)

    # API routers
    app.include_router(health.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    app.include_router(contact.router, prefix="/api")

    _mount_frontend(app)

    logger.info(
        "app ready: backend=%s ai=%s email=%s",
        settings.storage_backend,
        settings.ai_configured,
        settings.email_configured,
    )
    return app


def _mount_frontend(app: FastAPI) -> None:
    static_dir = FRONTEND_DIR / "static"
    index_file = FRONTEND_DIR / "index.html"

    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    def landing() -> FileResponse | JSONResponse:
        if index_file.is_file():
            return FileResponse(str(index_file))
        return JSONResponse(
            {
                "service": "Developer Landing Backend",
                "version": __version__,
                "docs": "/docs",
                "endpoints": ["/api/contact", "/api/health", "/api/metrics"],
            }
        )


app = create_app()
