"""Integration: public registration → verification → confirmation email via the outbox,
plus outbox idempotency and provider-down retry behavior."""

from __future__ import annotations

from conftest import inbox, relay
from sqlalchemy import select

from app.core.outbox import OutboxEvent
from app.modules.training.models import RegistrationStatus, TrainingRegistration, TrainingSession


def _session_id(db):
    return db.scalar(select(TrainingSession)).id


def test_public_registration_sends_verification_then_confirmation(client, db, org):
    sid = _session_id(db)
    resp = client.post(f"/api/public/sessions/{sid}/register",
                       json={"name": "Ada", "email": "ada@example.org"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "registered"

    # Email is NOT sent synchronously — it's in the outbox until the worker relays it.
    relay(db)
    msgs = inbox(db, org.id)
    assert any("Confirm your email" in m.subject for m in msgs), "verification email queued"

    # Verify the email → confirmation email is produced through the outbox.
    token = _latest_verify_token(db)
    v = client.post("/api/public/verify", json={"token": token})
    assert v.status_code == 200 and v.json()["status"] == "confirmed"
    relay(db)
    msgs = inbox(db, org.id)
    assert any("You're registered" in m.subject for m in msgs), "confirmation email sent"


def test_outbox_enqueue_is_idempotent(client, db, org):
    sid = _session_id(db)
    client.post(f"/api/public/sessions/{sid}/register", json={"name": "A", "email": "a@x.org"})
    # A second identical outbox key must not create a duplicate event.
    from app.core.outbox import enqueue
    ev1 = enqueue(db, org_id=org.id, event_type="email.send",
                  idempotency_key="verify:reg:1", payload={})
    assert ev1 is None  # key already exists from registration


def test_provider_down_leaves_event_for_retry(client, db, org, monkeypatch):
    sid = _session_id(db)
    client.post(f"/api/public/sessions/{sid}/register", json={"name": "A", "email": "a@x.org"})

    # Simulate the email provider being unavailable.
    from app.modules.communications import service as comms
    original = comms.InboxAdapter.send

    def boom(self, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(comms.InboxAdapter, "send", boom)
    processed = relay(db)
    assert processed == 0
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.send"))
    assert event.processed_at is None and event.attempts >= 1 and event.last_error

    # Provider recovers → the same event is relayed exactly once (no double send).
    monkeypatch.setattr(comms.InboxAdapter, "send", original)
    assert relay(db) == 1
    assert relay(db) == 0  # nothing left / no re-send


def _latest_verify_token(db):
    """Reach the plaintext token via the dev inbox link (tests only)."""
    msgs = inbox(db, db.scalar(select(TrainingSession)).org_id)
    verify = [m for m in msgs if "verify?token=" in m.body_text][-1]
    return verify.body_text.split("verify?token=")[1].split("\n")[0].strip()


def test_registration_status_flows(client, db):
    sid = _session_id(db)
    client.post(f"/api/public/sessions/{sid}/register", json={"name": "A", "email": "flow@x.org"})
    relay(db)
    token = _latest_verify_token(db)
    client.post("/api/public/verify", json={"token": token})
    reg = db.scalars(select(TrainingRegistration)).all()[-1]
    assert reg.status == RegistrationStatus.confirmed
