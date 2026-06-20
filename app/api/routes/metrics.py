"""GET /api/metrics — aggregated submission statistics."""

from __future__ import annotations

from fastapi import APIRouter

from app.repositories.factory import get_store

router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Aggregated contact statistics")
def metrics() -> dict:
    store = get_store()
    snapshot = store.metrics_snapshot()
    return {
        "storage_backend": store.backend,
        "totals": snapshot,
        "by_sentiment": {
            "positive": snapshot["sentiment_positive"],
            "neutral": snapshot["sentiment_neutral"],
            "negative": snapshot["sentiment_negative"],
        },
        "by_priority": {
            "low": snapshot["priority_low"],
            "medium": snapshot["priority_medium"],
            "high": snapshot["priority_high"],
        },
        "ai": {"ok": snapshot["ai_ok"], "fallback": snapshot["ai_fallback"]},
        "email": {
            "owner_sent": snapshot["email_owner_sent"],
            "user_sent": snapshot["email_user_sent"],
            "failed": snapshot["email_failed"],
        },
        "rate_limited": snapshot["rate_limited"],
    }
