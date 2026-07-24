"""Audit trail for privileged and sensitive actions."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, TimestampMixin

# Fields that must never be written into audit metadata (log redaction).
_REDACT = {"password", "password_hash", "token", "secret", "authorization"}


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    # Actor: a user, a service, or an agent. Exactly one identity attribution.
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user|service|agent
    actor_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)      # e.g. "training.checkin"
    target_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


def _redacted(meta: dict) -> dict:
    return {k: ("***" if k.lower() in _REDACT else v) for k, v in (meta or {}).items()}


def emit(
    db: Session,
    *,
    org_id: int,
    action: str,
    actor_type: str = "user",
    actor_id: str | int = "",
    target_type: str = "",
    target_id: str | int = "",
    meta: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        org_id=org_id,
        actor_type=actor_type,
        actor_id=str(actor_id),
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        meta=_redacted(meta or {}),
    )
    db.add(event)
    db.flush()
    return event
