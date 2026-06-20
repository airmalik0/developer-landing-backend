"""Upstash Redis storage backend (serverless-friendly).

Uses Upstash's HTTP Redis client — no persistent connection, which is exactly
what serverless functions need. Rate limiting uses a fixed-window counter
(``INCR`` + ``EXPIRE``); metrics use a hash; the request log is a capped list.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping

from app.config import get_settings
from app.core.logging import get_logger
from app.repositories.base import METRIC_KEYS, RateLimitResult, Store

logger = get_logger("store.redis")

_METRICS_HASH = "metrics"
_CONTACTS_LIST = "contacts"
_CONTACTS_CAP = 500


class RedisStore(Store):
    backend = "redis"

    def __init__(self) -> None:
        from upstash_redis import Redis  # imported lazily so `file` mode needs no dep

        settings = get_settings()
        if not (settings.redis_url and settings.redis_token):
            raise RuntimeError(
                "STORAGE_BACKEND=redis requires UPSTASH_REDIS_REST_URL and "
                "UPSTASH_REDIS_REST_TOKEN (or the KV_* aliases)."
            )
        self._redis = Redis(url=settings.redis_url, token=settings.redis_token)

    def save_contact(self, record: Mapping[str, object]) -> None:
        self._redis.rpush(_CONTACTS_LIST, json.dumps(record, ensure_ascii=False))
        # Keep only the most recent submissions.
        self._redis.ltrim(_CONTACTS_LIST, -_CONTACTS_CAP, -1)

    def increment(self, counters: Mapping[str, int]) -> None:
        for key, delta in counters.items():
            self._redis.hincrby(_METRICS_HASH, key, int(delta))

    def metrics_snapshot(self) -> dict[str, int]:
        raw = self._redis.hgetall(_METRICS_HASH) or {}
        return {key: int(raw.get(key, 0)) for key in METRIC_KEYS}

    def rate_limit(self, ip: str, max_requests: int, window_seconds: int) -> RateLimitResult:
        key = f"rl:{ip}"
        count = int(self._redis.incr(key))
        if count == 1:
            self._redis.expire(key, window_seconds)

        if count > max_requests:
            ttl = int(self._redis.ttl(key))
            retry_after = ttl if ttl > 0 else window_seconds
            return RateLimitResult(allowed=False, remaining=0, retry_after=retry_after)

        return RateLimitResult(
            allowed=True,
            remaining=max_requests - count,
            retry_after=0,
        )

    def health(self) -> bool:
        try:
            self._redis.set("health:ping", str(int(time.time())))
            return True
        except Exception as exc:  # noqa: BLE001 - report unreachable backend
            logger.warning("redis health check failed: %s", exc)
            return False
