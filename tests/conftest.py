"""Pytest fixtures.

Each test gets an isolated app instance backed by a fresh temp data directory,
the file storage backend, and no AI/email keys (so the AI step exercises its
fallback and emails are skipped — no network calls during tests).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    def _make(**env) -> TestClient:
        # Isolate filesystem + config from the developer's real .env.
        monkeypatch.chdir(tmp_path)  # no .env here → settings come from env vars only
        monkeypatch.setenv("STORAGE_BACKEND", "file")
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", env.pop("RATE_LIMIT_MAX_REQUESTS", "100"))
        monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", env.pop("RATE_LIMIT_WINDOW_SECONDS", "60"))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        # Reset cached singletons so the new env is picked up.
        from app.config import get_settings
        from app.repositories.factory import get_store

        get_settings.cache_clear()
        get_store.cache_clear()

        from app.main import create_app

        return TestClient(create_app())

    return _make


VALID_PAYLOAD = {
    "name": "Малик Юлдашев",
    "email": "malik@example.com",
    "phone": "+998 90 123 45 67",
    "comment": "Здравствуйте! Хотим обсудить разработку backend-сервиса.",
}
