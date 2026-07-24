"""Communications: templates, sent-message snapshots, delivery events, dev inbox."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # The outbox event that produced this message — makes send idempotent per event.
    outbox_event_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
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


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    sending = "sending"
    sent = "sent"
    cancelled = "cancelled"


class AudienceDefinition(Base, TimestampMixin):
    """An explicit, previewable audience — a first-class record, never implicit.

    ``rule`` is a small, validated filter (e.g. {"segment": "volunteers"}). The audience is
    resolved to concrete recipients (minus suppressions) at preview and at send time.
    """

    __tablename__ = "email_audience_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class EmailCampaign(Base, TimestampMixin):
    __tablename__ = "email_campaign"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    audience_id: Mapped[int] = mapped_column(
        ForeignKey("email_audience_definition.id"), nullable=False
    )
    status: Mapped[CampaignStatus] = mapped_column(default=CampaignStatus.draft, nullable=False)
    # Recipient count captured at approval/send time (what the approver signed off on).
    approved_recipient_count: Mapped[int | None] = mapped_column(Integer)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class Suppression(Base, TimestampMixin):
    """Do-not-email list: unsubscribes, hard bounces, complaints."""

    __tablename__ = "email_suppression"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_suppression_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(40), default="unsubscribe", nullable=False)
