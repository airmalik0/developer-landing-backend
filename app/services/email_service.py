"""Email notifications via Resend.

Sends two messages per submission (as the brief requires):
  * a notification to the site owner, enriched with the AI analysis + draft reply;
  * a confirmation copy to the user who filled in the form.

Delivery is best-effort: failures are caught and reported per-recipient in the
response, and never abort the request. Without ``RESEND_API_KEY`` the emails are
written to the log instead (graceful degradation).
"""

from __future__ import annotations

from html import escape

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.contact import AIAnalysis, ContactRequest, EmailStatus

logger = get_logger("email")


class EmailService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def send_notifications(
        self,
        contact: ContactRequest,
        analysis: AIAnalysis,
        *,
        send_user_copy: bool = True,
    ) -> EmailStatus:
        if not self._settings.email_configured:
            logger.info(
                "email disabled (no key/owner) → owner=%s user=%s [logged only]",
                self._settings.owner_email,
                contact.email,
            )
            return EmailStatus(owner="skipped", user="skipped")

        owner = self._safe_send(
            to=self._settings.owner_email,
            subject=f"📨 Новое обращение: {analysis.category} ({analysis.priority})",
            html=self._owner_html(contact, analysis),
            who="owner",
        )
        # The confirmation copy goes to a user-supplied, unverified address; the
        # caller gates it with a per-recipient limit so it can't be abused as a
        # spam/phishing relay. The comment is HTML-escaped in the body.
        if send_user_copy:
            user = self._safe_send(
                to=str(contact.email),
                subject="Мы получили ваше обращение",
                html=self._user_html(contact, analysis),
                who="user",
            )
        else:
            logger.info("user copy suppressed by recipient rate limit: %s", contact.email)
            user = "skipped"
        return EmailStatus(owner=owner, user=user)

    # ── transport ────────────────────────────────────────────────────────────
    def _safe_send(self, *, to: str, subject: str, html: str, who: str) -> str:
        try:
            import resend

            resend.api_key = self._settings.resend_api_key
            resend.Emails.send(
                {
                    "from": self._settings.from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
            )
            logger.info("email sent to %s (%s)", to, who)
            return "sent"
        except Exception as exc:  # noqa: BLE001 - report, never raise
            logger.warning("email to %s (%s) failed: %s", to, who, exc)
            return "failed"

    # ── bodies ───────────────────────────────────────────────────────────────
    @staticmethod
    def _owner_html(contact: ContactRequest, analysis: AIAnalysis) -> str:
        return f"""
        <h2>Новое обращение с сайта</h2>
        <table cellpadding="6" style="border-collapse:collapse">
          <tr><td><b>Имя</b></td><td>{escape(contact.name)}</td></tr>
          <tr><td><b>Email</b></td><td>{escape(str(contact.email))}</td></tr>
          <tr><td><b>Телефон</b></td><td>{escape(contact.phone)}</td></tr>
          <tr><td><b>Сообщение</b></td><td>{escape(contact.comment)}</td></tr>
        </table>
        <h3>🤖 AI-анализ</h3>
        <ul>
          <li><b>Тональность:</b> {escape(analysis.sentiment)}</li>
          <li><b>Категория:</b> {escape(analysis.category)}</li>
          <li><b>Приоритет:</b> {escape(analysis.priority)}</li>
          <li><b>Кратко:</b> {escape(analysis.summary)}</li>
        </ul>
        <h3>✍️ Предлагаемый ответ</h3>
        <blockquote style="border-left:3px solid #ccc;padding-left:12px;color:#444">
          {escape(analysis.suggested_reply)}
        </blockquote>
        <p style="color:#888;font-size:12px">AI source: {escape(analysis.source)}</p>
        """

    @staticmethod
    def _user_html(contact: ContactRequest, analysis: AIAnalysis) -> str:
        return f"""
        <h2>Спасибо за обращение!</h2>
        <p>Здравствуйте, {escape(contact.name)}!</p>
        <p>Мы получили ваше сообщение и свяжемся с вами в ближайшее время.</p>
        <p style="color:#555">Ваше сообщение:</p>
        <blockquote style="border-left:3px solid #ccc;padding-left:12px;color:#444">
          {escape(contact.comment)}
        </blockquote>
        """
