"""Scheduling: eligibility, conflict detection, waitlist, hours, metrics, and the API."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.db import utcnow
from app.core.session import make_session_token
from app.modules.identity.models import Person, Role, User, UserRoleAssignment
from app.modules.people.models import QualificationType, VolunteerProfile, VolunteerQualification
from app.modules.scheduling import service
from app.modules.scheduling.models import ShiftSignup, SignupStatus


def _volunteer(db, org, email, *, qual_type_id=None, expired=False):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    profile = VolunteerProfile(org_id=org.id, person_id=person.id)
    db.add(profile)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == "volunteer"))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    if qual_type_id is not None:
        db.add(VolunteerQualification(
            org_id=org.id, profile_id=profile.id, qualification_type_id=qual_type_id,
            granted_at=utcnow(),
            expires_at=(utcnow() - timedelta(days=1)) if expired else None, source="test"))
    db.commit()
    headers = {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}
    return profile, headers


def _shift(db, org, *, start_offset_h=24, dur_h=2, capacity=1, qual_type_id=None):
    ev = service.create_event(db, org_id=org.id, title="Cleanup")
    s = service.create_shift(db, org_id=org.id, event_id=ev.id,
                             starts_at=utcnow() + timedelta(hours=start_offset_h),
                             ends_at=utcnow() + timedelta(hours=start_offset_h + dur_h),
                             location="Park")
    role = service.add_role(db, org_id=org.id, shift_id=s.id, name="Helper", capacity=capacity,
                            required_qualification_type_id=qual_type_id)
    db.commit()
    return s, role


def test_eligibility_requires_valid_qualification(db, org):
    qt = QualificationType(org_id=org.id, key="first_aid", label="First Aid")
    db.add(qt)
    db.flush()
    _, role = _shift(db, org, qual_type_id=qt.id)
    no_qual, _ = _volunteer(db, org, "a@x.org")
    has_qual, _ = _volunteer(db, org, "b@x.org", qual_type_id=qt.id)
    expired, _ = _volunteer(db, org, "c@x.org", qual_type_id=qt.id, expired=True)

    assert service.check_eligibility(db, org_id=org.id, profile_id=no_qual.id, role=role).eligible is False
    assert service.check_eligibility(db, org_id=org.id, profile_id=has_qual.id, role=role).eligible is True
    assert service.check_eligibility(db, org_id=org.id, profile_id=expired.id, role=role).eligible is False


def test_capacity_waitlist_and_promotion_on_cancel(db, org):
    _, role = _shift(db, org, capacity=1)
    a, _ = _volunteer(db, org, "a@x.org")
    b, _ = _volunteer(db, org, "b@x.org")
    s_a = service.signup_for_shift(db, org_id=org.id, profile_id=a.id, role_id=role.id)
    s_b = service.signup_for_shift(db, org_id=org.id, profile_id=b.id, role_id=role.id)
    assert s_a.status == SignupStatus.confirmed
    assert s_b.status == SignupStatus.waitlisted
    # A cancels → B is deterministically promoted.
    service.cancel_signup(db, org_id=org.id, signup_id=s_a.id, actor_id=a.id)
    db.refresh(s_b)
    assert s_b.status == SignupStatus.confirmed


def test_time_conflict_is_rejected(db, org):
    _, role1 = _shift(db, org, start_offset_h=24, dur_h=2)
    _, role2 = _shift(db, org, start_offset_h=25, dur_h=2)  # overlaps role1
    v, _ = _volunteer(db, org, "a@x.org")
    service.signup_for_shift(db, org_id=org.id, profile_id=v.id, role_id=role1.id)
    try:
        service.signup_for_shift(db, org_id=org.id, profile_id=v.id, role_id=role2.id)
        raise AssertionError("overlapping signup should be rejected")
    except service.SchedulingError as exc:
        assert "overlap" in str(exc)


def test_checkin_hours_and_approval(db, org, admin_user):
    _, role = _shift(db, org, capacity=2)
    v, _ = _volunteer(db, org, "a@x.org")
    s = service.signup_for_shift(db, org_id=org.id, profile_id=v.id, role_id=role.id)
    service.check_in(db, org_id=org.id, signup_id=s.id, actor_id=admin_user.id)
    entry = service.record_hours(db, org_id=org.id, signup_id=s.id, hours=2.5, actor_id=admin_user.id)
    assert entry.approved is False
    service.approve_hours(db, org_id=org.id, entry_id=entry.id, actor_user_id=admin_user.id)
    db.refresh(entry)
    assert entry.approved is True and entry.hours == 2.5


def test_staffing_metrics(db, org):
    _, role = _shift(db, org, capacity=2)
    a, _ = _volunteer(db, org, "a@x.org")
    service.signup_for_shift(db, org_id=org.id, profile_id=a.id, role_id=role.id)
    m = service.staffing_metrics(db, org_id=org.id)
    # Seed-independent: assert on the role this test created, not org-wide totals
    # (the demo seed also contributes an opportunity + roles).
    assert m["filled"] >= 1 and m["capacity"] >= 2
    under = {u["role_id"]: u for u in m["understaffed"]}
    assert role.id in under and under[role.id]["filled"] == 1 and under[role.id]["capacity"] == 2


def test_volunteer_signup_and_cancel_via_api(client, db, org):
    _, role = _shift(db, org, capacity=1)
    _, headers = _volunteer(db, org, "vol@x.org")
    resp = client.post("/api/shifts/signup", headers=headers, json={"role_id": role.id})
    assert resp.status_code == 200 and resp.json()["status"] == "confirmed"
    signup_id = db.scalar(select(ShiftSignup)).id
    # Another volunteer cannot cancel someone else's signup.
    _, other = _volunteer(db, org, "other@x.org")
    assert client.post(f"/api/shifts/signups/{signup_id}/cancel", headers=other).status_code == 404
    # The owner can.
    assert client.post(f"/api/shifts/signups/{signup_id}/cancel", headers=headers).status_code == 200


def test_eligible_roles_and_ics_feed(client, db, org):
    _, role = _shift(db, org, capacity=2)
    _, headers = _volunteer(db, org, "vol@x.org")
    elig = client.get("/api/shifts/eligible", headers=headers).json()
    assert any(r["role_id"] == role.id for r in elig)
    client.post("/api/shifts/signup", headers=headers, json={"role_id": role.id})
    ics = client.get("/api/shifts/calendar.ics", headers=headers)
    assert ics.status_code == 200 and "BEGIN:VCALENDAR" in ics.text and "Cleanup" in ics.text


def test_coordinator_creates_and_sees_staffing_via_api(client, admin_headers, db, org):
    ev = client.post("/api/coordinator/events", headers=admin_headers, json={"title": "Fair"})
    assert ev.status_code == 201
    start = (utcnow() + timedelta(days=1)).isoformat()
    end = (utcnow() + timedelta(days=1, hours=3)).isoformat()
    sh = client.post("/api/coordinator/shifts", headers=admin_headers,
                     json={"event_id": ev.json()["id"], "starts_at": start, "ends_at": end})
    assert sh.status_code == 201
    client.post("/api/coordinator/roles", headers=admin_headers,
                json={"shift_id": sh.json()["id"], "name": "Setup", "capacity": 3})
    metrics = client.get("/api/coordinator/metrics/staffing", headers=admin_headers)
    assert metrics.status_code == 200 and metrics.json()["capacity"] >= 3
