"""GET /api/health — liveness and configured-capability report."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.repositories.factory import get_store

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service health check")
def health() -> dict:
    settings = get_settings()
    store = get_store()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
        "storage_backend": store.backend,
        "storage_healthy": store.health(),
        "ai_configured": settings.ai_configured,
        "email_configured": settings.email_configured,
    }
