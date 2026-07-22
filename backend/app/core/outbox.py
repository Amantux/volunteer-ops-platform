"""Transactional outbox: durable domain events committed in the same tx as state.

A service writes state + an OutboxEvent in one transaction. The relay (called by the
Celery worker, or synchronously in tests) processes unprocessed events exactly once and
performs side effects (send email, etc.). Handlers must be idempotent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, TimestampMixin, utcnow


class OutboxEvent(Base, TimestampMixin):
    __tablename__ = "outbox_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Natural idempotency key for the *effect* (e.g. "confirmation:reg:42").
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(String(500), default="", nullable=False)


def enqueue(
    db: Session,
    *,
    org_id: int,
    event_type: str,
    idempotency_key: str,
    payload: dict,
) -> OutboxEvent | None:
    """Add an event to the outbox. Returns None if the idempotency key already exists."""
    existing = db.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return None
    event = OutboxEvent(
        org_id=org_id, event_type=event_type, idempotency_key=idempotency_key, payload=payload
    )
    db.add(event)
    db.flush()
    return event


# event_type -> handler(db, event). Registered by modules at import time.
_HANDLERS: dict[str, Callable[[Session, OutboxEvent], None]] = {}


def handler(event_type: str) -> Callable[[Callable[[Session, OutboxEvent], None]], Callable]:
    def register(fn: Callable[[Session, OutboxEvent], None]):
        _HANDLERS[event_type] = fn
        return fn

    return register


def relay_pending(db: Session, *, limit: int = 100) -> int:
    """Process unprocessed outbox events. Idempotent + safe to run repeatedly.

    Returns the number of events processed. Failures are recorded and left for retry.
    """
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(limit)
    )
    # On Postgres, lock rows so concurrent workers don't double-process.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    events = db.scalars(stmt).all()
    processed = 0
    for event in events:
        fn = _HANDLERS.get(event.event_type)
        event.attempts += 1
        try:
            if fn is not None:
                fn(db, event)
            event.processed_at = utcnow()
            event.last_error = ""
            processed += 1
        except Exception as exc:  # noqa: BLE001 - record + leave for retry
            event.last_error = str(exc)[:500]
        db.flush()
    db.commit()
    return processed
