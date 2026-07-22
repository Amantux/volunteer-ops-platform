"""Tests for the unverified-hold reaper, rate limiter, and bot-check."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core import botcheck, ratelimit
from app.core.db import utcnow
from app.modules.agents.models import AgentProposal
from app.modules.training.models import RegistrationStatus, TrainingSession
from app.modules.training.service import (
    expire_unconfirmed_holds,
    register_guest,
    verify_email,
)


def _session(db):
    return db.scalar(select(TrainingSession))


def test_reaper_expires_only_stale_unverified_holds(db, org):
    session = _session(db)
    # A: stale unverified hold. B: fresh unverified hold. C: verified/confirmed.
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    b = register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")
    c = register_guest(db, org_id=org.id, session_id=session.id, name="C", email="c@x.org")
    verify_email(db, token=c.verification_token)  # C confirmed
    a.registration.created_at = utcnow() - timedelta(days=2)  # make A stale
    db.commit()

    expired = expire_unconfirmed_holds(db, ttl_min=60 * 24)
    assert expired == 1
    db.refresh(a.registration)
    db.refresh(b.registration)
    db.refresh(c.registration)
    assert a.registration.status == RegistrationStatus.expired
    assert b.registration.status == RegistrationStatus.registered  # too fresh
    assert c.registration.status == RegistrationStatus.confirmed   # verified, kept


def test_reaper_frees_seat_and_proposes_promotion(db, org):
    session = _session(db)
    session.capacity = 1
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    b = register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")
    assert b.waitlisted is True
    a.registration.created_at = utcnow() - timedelta(days=2)
    db.commit()

    expire_unconfirmed_holds(db, ttl_min=60 * 24)
    # A's seat is freed and a promotion proposal exists for B.
    assert db.scalar(select(AgentProposal)) is not None


def test_memory_rate_limiter_blocks_after_limit():
    key = "test:memory:unique-key-1"
    allowed = [ratelimit.allow(key, limit=3, window_seconds=60) for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_botcheck_disabled_passes(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "botcheck_provider", "none")
    assert botcheck.verify(None) is True
    assert botcheck.is_enabled() is False


def test_botcheck_enabled_requires_token(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "botcheck_provider", "turnstile")
    monkeypatch.setattr(settings, "turnstile_secret", "secret")
    assert botcheck.is_enabled() is True
    assert botcheck.verify(None) is False  # missing token rejected without a network call
