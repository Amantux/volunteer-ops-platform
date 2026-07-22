"""Communications: provider-abstracted email, template rendering, outbox handler.

Email is never sent in the request path — services enqueue an ``email.send`` outbox
event; the relay (worker/tests) renders + sends and records the message. Handlers are
idempotent via the outbox idempotency key.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.outbox import OutboxEvent, enqueue, handler

from .models import EmailMessage, EmailTemplate, InboxMessage


class EmailAdapter(Protocol):
    name: str

    def send(self, *, to_email: str, subject: str, body_text: str, org_id: int) -> None: ...


class ConsoleAdapter:
    name = "console"

    def send(self, *, to_email: str, subject: str, body_text: str, org_id: int) -> None:
        print(f"[email:console] to={to_email} subject={subject!r}\n{body_text}\n")


class InboxAdapter:
    """Dev adapter — persists to a table so tests and local dev can read 'sent' mail."""

    name = "inbox"

    def __init__(self, db: Session) -> None:
        self.db = db

    def send(self, *, to_email: str, subject: str, body_text: str, org_id: int) -> None:
        self.db.add(
            InboxMessage(org_id=org_id, to_email=to_email, subject=subject, body_text=body_text)
        )


class SmtpAdapter:
    """Real provider adapter — works with Postmark/SES/any SMTP relay."""

    name = "smtp"

    def send(self, *, to_email: str, subject: str, body_text: str, org_id: int) -> None:
        msg = MimeMessage()
        msg["From"] = settings.email_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body_text)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_starttls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)


def get_adapter(db: Session) -> EmailAdapter:
    provider = settings.email_provider
    if provider == "smtp":
        return SmtpAdapter()
    if provider == "console":
        return ConsoleAdapter()
    return InboxAdapter(db)  # default dev sink


def render_template(db: Session, *, org_id: int, key: str, context: dict) -> tuple[str, str]:
    template = db.scalar(
        select(EmailTemplate).where(EmailTemplate.org_id == org_id, EmailTemplate.key == key)
    )
    if template is None:
        raise ValueError(f"email template not found: {key}")
    return _apply(template.subject, context), _apply(template.body_text, context)


def _apply(text: str, context: dict) -> str:
    for name, value in context.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def queue_email(
    db: Session,
    *,
    org_id: int,
    idempotency_key: str,
    to_email: str,
    template_key: str,
    context: dict,
) -> OutboxEvent | None:
    """Enqueue a transactional email through the outbox (commit with the caller's tx)."""
    return enqueue(
        db,
        org_id=org_id,
        event_type="email.send",
        idempotency_key=idempotency_key,
        payload={
            "to_email": to_email,
            "template_key": template_key,
            "context": context,
        },
    )


@handler("email.send")
def handle_email_send(db: Session, event: OutboxEvent) -> None:
    payload = event.payload
    subject, body = render_template(
        db, org_id=event.org_id, key=payload["template_key"], context=payload.get("context", {})
    )
    message = EmailMessage(
        org_id=event.org_id,
        to_email=payload["to_email"],
        subject=subject,
        body_text=body,
        template_key=payload["template_key"],
        status="queued",
    )
    db.add(message)
    db.flush()
    adapter = get_adapter(db)
    adapter.send(to_email=message.to_email, subject=subject, body_text=body, org_id=event.org_id)
    message.status = "sent"
    message.provider = adapter.name
    message.sent_at = utcnow()
