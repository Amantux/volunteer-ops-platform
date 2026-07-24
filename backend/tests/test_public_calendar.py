"""Public opportunities + unified calendar: only published, upcoming items are exposed."""

from __future__ import annotations

from datetime import timedelta

from app.core.db import utcnow
from app.modules.scheduling import service


def test_opportunities_lists_seeded_public_event(client):
    opps = client.get("/api/public/opportunities").json()
    assert any(o["title"] == "Community Garden Workday" for o in opps)
    garden = next(o for o in opps if o["title"] == "Community Garden Workday")
    assert garden["shift_count"] >= 1
    assert garden["shifts"][0]["open_roles"] >= 1
    # No volunteer PII leaks into the public payload.
    assert "signups" not in garden and "volunteer" not in str(garden)


def test_non_public_event_is_hidden_from_public_surfaces(client, db, org):
    ev = service.create_event(db, org_id=org.id, title="Internal Staff Meeting",
                              is_public=False)
    start = utcnow() + timedelta(days=3)
    sh = service.create_shift(db, org_id=org.id, event_id=ev.id, starts_at=start,
                              ends_at=start + timedelta(hours=1), location="HQ")
    service.add_role(db, org_id=org.id, shift_id=sh.id, name="Attendee", capacity=5)
    db.commit()

    opps = client.get("/api/public/opportunities").json()
    assert all(o["title"] != "Internal Staff Meeting" for o in opps)
    cal = client.get("/api/public/calendar").json()
    assert all(item["title"] != "Internal Staff Meeting" for item in cal)


def test_calendar_merges_training_and_opportunities_sorted(client):
    cal = client.get("/api/public/calendar").json()
    types = {item["type"] for item in cal}
    assert "opportunity" in types  # seeded garden workday shifts
    assert "training" in types     # seeded dated orientation session
    starts = [item["starts_at"] for item in cal]
    assert starts == sorted(starts)


def test_past_shifts_are_excluded(client, db, org):
    ev = service.create_event(db, org_id=org.id, title="Past Cleanup", is_public=True)
    past = utcnow() - timedelta(days=2)
    sh = service.create_shift(db, org_id=org.id, event_id=ev.id, starts_at=past,
                              ends_at=past + timedelta(hours=1), location="Park")
    service.add_role(db, org_id=org.id, shift_id=sh.id, name="Helper", capacity=3)
    db.commit()

    opps = client.get("/api/public/opportunities").json()
    assert all(o["title"] != "Past Cleanup" for o in opps)
    cal = client.get("/api/public/calendar").json()
    assert all(item["title"] != "Past Cleanup" for item in cal)


def test_past_training_session_is_excluded_from_calendar(client, db, org):
    # `is_open` is a manual flag (not time-derived): a stale-but-open past session must not
    # linger on the public calendar.
    from app.modules.training.models import Course, TrainingSession

    course = Course(org_id=org.id, title="Old Orientation", is_public=True)
    db.add(course)
    db.flush()
    past = utcnow() - timedelta(days=5)
    db.add(TrainingSession(org_id=org.id, course_id=course.id, capacity=10,
                           location="Old Hall", starts_at=past, ends_at=past + timedelta(hours=2)))
    db.commit()

    cal = client.get("/api/public/calendar").json()
    assert all(item["title"] != "Old Orientation" for item in cal)
    # sanity: the check above isn't vacuous — the calendar still has upcoming items.
    assert len(cal) >= 1
