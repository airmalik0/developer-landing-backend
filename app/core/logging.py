"""Logging configuration.

Always logs to stdout (captured by Vercel Runtime Logs). When running on a
writable filesystem (local dev) it additionally writes a rotating file at
``<LOG_DIR>/requests.log`` — exactly the "log every request to a file"
requirement from the brief. On serverless the file handler targets ``/tmp``.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import get_settings

_CONFIGURED = False
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging() -> None:
    """Idempotently configure the application logger."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger("app")
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(_FMT)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    log_dir = "/tmp" if settings.is_serverless else settings.log_dir
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "requests.log"),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Read-only FS — stdout logging still works.
        root.warning("file logging unavailable, using stdout only")

    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str = "app") -> logging.Logger:
    if not name.startswith("app"):
        name = f"app.{name}"
    return logging.getLogger(name)
