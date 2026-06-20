"""Application configuration loaded from environment variables / .env.

Centralises every tunable knob so the rest of the codebase never reads
``os.environ`` directly. Access through :func:`get_settings` (cached).
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "Developer Landing Backend"
    environment: str = "development"
    log_level: str = "INFO"

    # CORS: kept as a raw string to avoid pydantic's JSON-list env parsing.
    cors_origins: str = "*"

    # ── Storage backend ──────────────────────────────────────────────────────
    storage_backend: str = "file"  # "file" | "redis"
    data_dir: str = "data"
    log_dir: str = "logs"

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_max_requests: int = 5
    rate_limit_window_seconds: int = 60

    # ── AI (Anthropic) ───────────────────────────────────────────────────────
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5"
    ai_timeout_seconds: float = 12.0

    # ── Email (Resend) ───────────────────────────────────────────────────────
    resend_api_key: str | None = None
    owner_email: str | None = None
    from_email: str = "onboarding@resend.dev"

    # ── Upstash Redis (serverless storage) ───────────────────────────────────
    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "redis_url",
            "UPSTASH_REDIS_REST_URL",
            "KV_REST_API_URL",
        ),
    )
    redis_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "redis_token",
            "UPSTASH_REDIS_REST_TOKEN",
            "KV_REST_API_TOKEN",
        ),
    )

    # ── Derived helpers ──────────────────────────────────────────────────────
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_serverless(self) -> bool:
        """True when running on Vercel (read-only FS except /tmp)."""
        return bool(os.environ.get("VERCEL"))

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def email_configured(self) -> bool:
        return bool(self.resend_api_key and self.owner_email)


@lru_cache
def get_settings() -> Settings:
    return Settings()
