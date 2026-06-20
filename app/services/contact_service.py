"""Orchestrates the full contact lifecycle (the business-logic layer).

    rate-limit → AI enrichment → email notifications → persist + metrics → response

This is the single place that wires the services and the store together; the
controller stays thin and just hands off the validated payload.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.core.errors import RateLimitExceeded
from app.core.logging import get_logger
from app.repositories.base import Store
from app.repositories.factory import get_store
from app.schemas.contact import AIAnalysis, ContactRequest, ContactResponse, EmailStatus
from app.services.ai_service import AIService
from app.services.email_service import EmailService

logger = get_logger("contact")


class ContactService:
    def __init__(
        self,
        store: Store | None = None,
        ai: AIService | None = None,
        email: EmailService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or get_store()
        self._ai = ai or AIService(self._settings)
        self._email = email or EmailService(self._settings)

    def handle(self, contact: ContactRequest, ip: str) -> ContactResponse:
        # 1. Rate limit (anti-spam) — fails fast before doing any real work.
        decision = self._store.rate_limit(
            ip,
            self._settings.rate_limit_max_requests,
            self._settings.rate_limit_window_seconds,
        )
        if not decision.allowed:
            self._store.increment({"rate_limited": 1})
            logger.info("rate limited ip=%s retry_after=%s", ip, decision.retry_after)
            raise RateLimitExceeded(decision.retry_after)

        # 2. AI enrichment (with built-in graceful fallback).
        analysis = self._ai.analyze(contact.name, contact.comment)

        # 3. Email notifications (best-effort, reported back). The confirmation
        #    copy is additionally capped per recipient so the form cannot be used
        #    to flood an arbitrary address with mail.
        recipient_ok = self._store.rate_limit(
            f"email:{str(contact.email).lower()}",
            self._settings.email_recipient_max,
            self._settings.email_recipient_window_seconds,
        ).allowed
        email_status = self._email.send_notifications(
            contact, analysis, send_user_copy=recipient_ok
        )

        # 4. Persist the request + update statistics.
        record_id = uuid.uuid4().hex
        received_at = datetime.now(timezone.utc).isoformat()
        self._store.save_contact(
            {
                "id": record_id,
                "received_at": received_at,
                "ip": ip,
                "name": contact.name,
                "email": str(contact.email),
                "phone": contact.phone,
                "comment": contact.comment,
                "analysis": analysis.model_dump(),
                "email_status": email_status.model_dump(),
            }
        )
        self._store.increment(self._counters(analysis, email_status))

        logger.info(
            "contact processed id=%s sentiment=%s priority=%s ai=%s",
            record_id,
            analysis.sentiment,
            analysis.priority,
            analysis.source,
        )

        return ContactResponse(
            id=record_id,
            received_at=received_at,
            name=contact.name,
            email=contact.email,
            analysis=analysis,
            email_status=email_status,
        )

    @staticmethod
    def _counters(analysis: AIAnalysis, email_status: EmailStatus) -> dict[str, int]:
        counters: dict[str, int] = {
            "total": 1,
            f"sentiment_{analysis.sentiment}": 1,
            f"priority_{analysis.priority}": 1,
            "ai_ok" if analysis.source == "ai" else "ai_fallback": 1,
        }
        if email_status.owner == "sent":
            counters["email_owner_sent"] = 1
        if email_status.user == "sent":
            counters["email_user_sent"] = 1
        failed = sum(1 for s in (email_status.owner, email_status.user) if s == "failed")
        if failed:
            counters["email_failed"] = failed
        return counters
