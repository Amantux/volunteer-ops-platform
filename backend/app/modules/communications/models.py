"""Communications: templates, sent-message snapshots, delivery events, dev inbox."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class EmailTemplate(Base, TimestampMixin):
    __tablename__ = "email_template"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_email_template_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "training_confirmation"
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)  # {{variable}} placeholders


class EmailMessage(Base, TimestampMixin):
    """An individual message: the rendered content snapshot + delivery status."""

    __tablename__ = "email_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)  # queued|sent|failed
    provider: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class EmailDeliveryEvent(Base, TimestampMixin):
    """Provider callbacks: delivered/bounce/complaint (open/click are opt-in per org)."""

    __tablename__ = "email_delivery_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("email_message.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class InboxMessage(Base, TimestampMixin):
    """Dev email adapter sink — lets tests and local dev 'read' sent mail."""

    __tablename__ = "dev_inbox_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
