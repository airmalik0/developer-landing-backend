"""Selects the storage backend from configuration (``STORAGE_BACKEND``)."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.core.logging import get_logger
from app.repositories.base import Store

logger = get_logger("store.factory")


@lru_cache
def get_store() -> Store:
    backend = get_settings().storage_backend.lower()
    if backend == "redis":
        from app.repositories.redis_store import RedisStore

        logger.info("using redis storage backend")
        return RedisStore()

    from app.repositories.file_store import FileStore

    logger.info("using file storage backend")
    return FileStore()
