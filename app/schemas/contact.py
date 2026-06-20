"""Pydantic models for the contact-form API (request + response shapes)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# Permissive international phone pattern: digits, spaces, +, -, parentheses.
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")

Sentiment = Literal["positive", "neutral", "negative"]
Priority = Literal["low", "medium", "high"]


class ContactRequest(BaseModel):
    """Incoming contact-form payload. Validation happens here automatically."""

    name: str = Field(..., min_length=2, max_length=100, examples=["Малик Юлдашев"])
    email: EmailStr = Field(..., examples=["malik@example.com"])
    phone: str = Field(..., min_length=7, max_length=20, examples=["+998 90 123 45 67"])
    comment: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        examples=["Здравствуйте! Хотим обсудить разработку backend-сервиса."],
    )

    @field_validator("name", "comment")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not _PHONE_RE.match(v):
            raise ValueError("invalid phone number format")
        return v


class AIAnalysis(BaseModel):
    """Structured enrichment produced by the AI service (or its fallback)."""

    sentiment: Sentiment = Field(..., description="Tone of the comment")
    category: str = Field(..., description="Type of the request")
    priority: Priority = Field(..., description="Suggested handling priority")
    summary: str = Field(..., description="One-line summary of the message")
    suggested_reply: str = Field(..., description="Draft reply the owner can send")
    source: Literal["ai", "fallback"] = Field(
        ..., description="'ai' if the model answered, 'fallback' if degraded"
    )


class EmailStatus(BaseModel):
    """Per-recipient delivery outcome (best-effort, never fails the request)."""

    owner: str = Field(..., description="sent | failed | skipped")
    user: str = Field(..., description="sent | failed | skipped")


class ContactResponse(BaseModel):
    """Response returned after a contact submission is fully processed."""

    id: str
    received_at: str
    name: str
    email: EmailStr
    analysis: AIAnalysis
    email_status: EmailStatus
    message: str = "Спасибо! Ваше обращение принято."
