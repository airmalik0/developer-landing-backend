"""Storage abstraction (the Repository layer).

A single :class:`Store` interface hides where logs, statistics and rate-limit
counters live. Two implementations exist — :class:`FileStore` (local default)
and :class:`RedisStore` (Upstash, serverless). The rest of the app depends only
on this interface, which is what lets the same code run locally on disk and on
Vercel against Redis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass

# Canonical metric counter keys (kept in one place so file & redis agree).
METRIC_KEYS: tuple[str, ...] = (
    "total",
    "sentiment_positive",
    "sentiment_neutral",
    "sentiment_negative",
    "priority_low",
    "priority_medium",
    "priority_high",
    "ai_ok",
    "ai_fallback",
    "email_owner_sent",
    "email_user_sent",
    "email_failed",
    "rate_limited",
)


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class Store(ABC):
    """Persistence + rate-limiting contract."""

    backend: str = "base"

    @abstractmethod
    def save_contact(self, record: Mapping[str, object]) -> None:
        """Append a contact submission to the request log."""

    @abstractmethod
    def increment(self, counters: Mapping[str, int]) -> None:
        """Atomically add to the named metric counters."""

    @abstractmethod
    def metrics_snapshot(self) -> dict[str, int]:
        """Return the current value of every metric counter."""

    @abstractmethod
    def rate_limit(self, ip: str, max_requests: int, window_seconds: int) -> RateLimitResult:
        """Register a hit for ``ip`` and report whether it is allowed."""

    def health(self) -> bool:
        """Best-effort check that the backend is reachable."""
        return True
