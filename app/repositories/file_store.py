"""File-system storage backend.

Implements the brief's "file storage" option literally:
  * request log   → ``contacts.jsonl`` (one JSON object per submission)
  * statistics    → ``metrics.json``
  * rate limiting  → ``ratelimit.json`` (sliding window of timestamps per IP)

All writes are guarded by a process-level lock and use atomic ``os.replace`` so
a crash mid-write can never corrupt a file. Great for local development; on
serverless prefer :class:`RedisStore` (see the design doc).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Mapping

from app.config import get_settings
from app.core.logging import get_logger
from app.repositories.base import METRIC_KEYS, RateLimitResult, Store

logger = get_logger("store.file")


class FileStore(Store):
    backend = "file"

    def __init__(self) -> None:
        settings = get_settings()
        base = "/tmp/data" if settings.is_serverless else settings.data_dir
        os.makedirs(base, exist_ok=True)
        self._contacts_path = os.path.join(base, "contacts.jsonl")
        self._metrics_path = os.path.join(base, "metrics.json")
        self._ratelimit_path = os.path.join(base, "ratelimit.json")
        self._lock = threading.Lock()

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _read_json(path: str, default: object) -> object:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def _atomic_write_json(path: str, data: object) -> None:
        directory = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    # ── Store API ────────────────────────────────────────────────────────────
    def save_contact(self, record: Mapping[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self._contacts_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def increment(self, counters: Mapping[str, int]) -> None:
        with self._lock:
            metrics = self._read_json(self._metrics_path, {})
            if not isinstance(metrics, dict):
                metrics = {}
            for key, delta in counters.items():
                metrics[key] = int(metrics.get(key, 0)) + int(delta)
            self._atomic_write_json(self._metrics_path, metrics)

    def metrics_snapshot(self) -> dict[str, int]:
        metrics = self._read_json(self._metrics_path, {})
        if not isinstance(metrics, dict):
            metrics = {}
        return {key: int(metrics.get(key, 0)) for key in METRIC_KEYS}

    def rate_limit(self, ip: str, max_requests: int, window_seconds: int) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            store = self._read_json(self._ratelimit_path, {})
            if not isinstance(store, dict):
                store = {}

            hits = [t for t in store.get(ip, []) if isinstance(t, (int, float)) and t > cutoff]

            if len(hits) >= max_requests:
                retry_after = max(1, int(hits[0] + window_seconds - now))
                store[ip] = hits
                self._prune_and_write(store, cutoff)
                return RateLimitResult(allowed=False, remaining=0, retry_after=retry_after)

            hits.append(now)
            store[ip] = hits
            self._prune_and_write(store, cutoff)
            return RateLimitResult(
                allowed=True,
                remaining=max_requests - len(hits),
                retry_after=0,
            )

    def _prune_and_write(self, store: dict, cutoff: float) -> None:
        # Drop stale entries so the file does not grow without bound.
        pruned = {
            key: [t for t in times if t > cutoff]
            for key, times in store.items()
        }
        pruned = {key: times for key, times in pruned.items() if times}
        self._atomic_write_json(self._ratelimit_path, pruned)
