"""Operational endpoints: health, readiness, and the outbox-backlog metrics."""

from __future__ import annotations

from sqlalchemy import select

from app.modules.training.models import TrainingSession


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_metrics_reports_outbox_backlog(client, db):
    # A public registration enqueues an (unprocessed) verification email in the outbox.
    sid = db.scalar(select(TrainingSession)).id
    client.post(f"/api/public/sessions/{sid}/register", json={"name": "A", "email": "a@x.org"})
    m = client.get("/api/metrics").json()
    assert m["outbox_pending"] >= 1
    assert m["outbox_stuck"] == 0
    assert "outbox_oldest_pending_age_seconds" in m


def test_ready_reports_database_reachable(client):
    r = client.get("/api/ready")
    # DB is reachable; Redis may be down in the test env (→ 503). Either way the DB check
    # must be true.
    body = r.json()
    checks = body.get("checks") or (body.get("detail") or {}).get("checks") or {}
    assert checks.get("database") is True
