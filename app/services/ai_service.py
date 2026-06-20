"""AI enrichment of a contact message (the mandatory AI integration).

A single Anthropic Claude Haiku call, constrained with *forced tool use*, returns
strict JSON containing the sentiment, request category, priority, a one-line
summary and a ready-to-send draft reply — three of the brief's AI use-cases in
one request.

Graceful fallback: if no API key is configured, or the model call times out or
errors, the service returns a safe heuristic result (``source="fallback"``) and
the request keeps flowing. The AI step can never break the contact form.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.contact import AIAnalysis

logger = get_logger("ai")

_TOOL = {
    "name": "record_analysis",
    "description": "Record the structured analysis of an inbound contact-form message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["positive", "neutral", "negative"],
                "description": "Overall tone of the message.",
            },
            "category": {
                "type": "string",
                "description": (
                    "Type of request, e.g. 'Сотрудничество', 'Найм/вакансия', "
                    "'Техническая поддержка', 'Вопрос по проекту', 'Спам', 'Прочее'."
                ),
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "How urgently the owner should respond.",
            },
            "summary": {
                "type": "string",
                "description": "One short sentence summarising the message.",
            },
            "suggested_reply": {
                "type": "string",
                "description": (
                    "A polite, ready-to-send draft reply in the same language as "
                    "the message. 2-4 sentences."
                ),
            },
        },
        "required": ["sentiment", "category", "priority", "summary", "suggested_reply"],
    },
}

_SYSTEM = (
    "You are an assistant for a software developer's website. You triage inbound "
    "contact-form messages. Always answer by calling the record_analysis tool. "
    "Write the summary and suggested_reply in the same language as the message."
)


class AIService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def analyze(self, name: str, comment: str) -> AIAnalysis:
        if not self._settings.ai_configured:
            logger.info("ai disabled (no API key) → fallback")
            return self._fallback(name, comment)

        try:
            return self._analyze_with_model(name, comment)
        except Exception as exc:  # noqa: BLE001 - any failure must degrade gracefully
            logger.warning("ai call failed (%s) → fallback", exc)
            return self._fallback(name, comment)

    # ── Anthropic call ───────────────────────────────────────────────────────
    def _analyze_with_model(self, name: str, comment: str) -> AIAnalysis:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self._settings.anthropic_api_key,
            timeout=self._settings.ai_timeout_seconds,
            max_retries=1,
        )
        message = client.messages.create(
            model=self._settings.anthropic_model,
            max_tokens=512,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_analysis"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Sender name: {name}\n"
                        f"Message:\n\"\"\"\n{comment}\n\"\"\""
                    ),
                }
            ],
        )
        payload = self._extract_tool_input(message)
        return AIAnalysis(source="ai", **payload)

    @staticmethod
    def _extract_tool_input(message: object) -> dict:
        for block in getattr(message, "content", []):
            if getattr(block, "type", None) == "tool_use":
                data = block.input
                if isinstance(data, dict):
                    return data
        raise ValueError("model returned no tool_use block")

    # ── Fallback ─────────────────────────────────────────────────────────────
    @staticmethod
    def _fallback(name: str, comment: str) -> AIAnalysis:
        summary = comment.strip().replace("\n", " ")
        if len(summary) > 120:
            summary = summary[:117] + "..."
        greeting = name.split()[0] if name.strip() else "там"
        reply = (
            f"Здравствуйте, {greeting}! Спасибо за обращение — мы получили ваше "
            "сообщение и свяжемся с вами в ближайшее время."
        )
        return AIAnalysis(
            sentiment="neutral",
            category="Прочее",
            priority="medium",
            summary=summary or "Новое обращение с сайта.",
            suggested_reply=reply,
            source="fallback",
        )
