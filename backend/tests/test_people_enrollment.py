"""Program enrollment (long-term assignment) + background-check status: lifecycle, the
eligibility gate, and the invariant that background-check data never reaches a volunteer caller."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.db import utcnow
from app.core.session import make_session_token
from app.modules.identity.models import Person, Role, User, UserRoleAssignment
from app.modules.org.models import Program
from app.modules.people import service as people
from app.modules.people.models import ProgramEnrollment, VolunteerProfile
from app.modules.scheduling import service as sched


def _program(db, org, key="service_dog", name="Service Dog"):
    p = Program(org_id=org.id, key=key, name=name)
    db.add(p)
    db.commit()
    return p


def _volunteer(db, org, email):
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
    db.commit()
    headers = {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}
    return profile, headers


# --- Enrollment lifecycle --------------------------------------------------- #

def test_enroll_is_idempotent_and_transitions(db, org, client, admin_headers):
    prog = _program(db, org)
    _volunteer(db, org, "raiser@x.org")

    body = {"volunteer_email": "raiser@x.org", "program_id": prog.id, "role": "puppy_raiser"}
    first = client.post("/api/coordinator/enrollments", headers=admin_headers, json=body)
    assert first.status_code == 201
    eid = first.json()["id"]
    # Idempotent: a second enrol in the same role returns the same active enrollment.
    again = client.post("/api/coordinator/enrollments", headers=admin_headers, json=body)
    assert again.json()["id"] == eid

    listing = client.get("/api/coordinator/enrollments", headers=admin_headers).json()
    assert [e for e in listing if e["id"] == eid][0]["status"] == "active"

    client.post(f"/api/coordinator/enrollments/{eid}/status", headers=admin_headers,
                json={"status": "paused"})
    client.post(f"/api/coordinator/enrollments/{eid}/status", headers=admin_headers,
                json={"status": "completed"})
    db.expire_all()
    enr = db.get(ProgramEnrollment, eid)
    assert enr.status == "completed"
    assert enr.ended_at is not None  # terminal status stamps an end date


def test_enroll_unknown_volunteer_is_400(db, org, client, admin_headers):
    prog = _program(db, org)
    r = client.post("/api/coordinator/enrollments", headers=admin_headers,
                    json={"volunteer_email": "ghost@x.org", "program_id": prog.id,
                          "role": "puppy_raiser"})
    assert r.status_code == 400
    assert "no volunteer" in r.json()["detail"]


def test_completed_role_can_be_re_enrolled(db, org, client, admin_headers):
    """A finished commitment shouldn't block a fresh one in the same role."""
    prog = _program(db, org)
    _volunteer(db, org, "again@x.org")
    body = {"volunteer_email": "again@x.org", "program_id": prog.id, "role": "puppy_raiser"}
    e1 = client.post("/api/coordinator/enrollments", headers=admin_headers, json=body).json()["id"]
    client.post(f"/api/coordinator/enrollments/{e1}/status", headers=admin_headers,
                json={"status": "completed"})
    e2 = client.post("/api/coordinator/enrollments", headers=admin_headers, json=body).json()["id"]
    assert e2 != e1


# --- Background-check gate --------------------------------------------------- #

def test_background_check_gates_a_slot(db, org, client, admin_headers):
    prog = _program(db, org)
    profile, vol_headers = _volunteer(db, org, "sitter@x.org")
    ev = sched.create_event(db, org_id=org.id, title="Respite care", program_id=prog.id)
    s = sched.create_shift(db, org_id=org.id, event_id=ev.id,
                           starts_at=utcnow() + timedelta(hours=24),
                           ends_at=utcnow() + timedelta(hours=26), location="Home")
    role = sched.add_role(db, org_id=org.id, shift_id=s.id, name="Sitter", capacity=1,
                          requires_background_check=True)
    db.commit()

    # No cleared background check → not eligible, and hidden from the volunteer's open roles.
    assert sched.check_eligibility(db, org_id=org.id, profile_id=profile.id,
                                   role=role).eligible is False
    open_role_ids = [r["role_id"] for r in client.get(
        "/api/shifts/eligible", headers=vol_headers).json()]
    assert role.id not in open_role_ids

    # Clear it via the privileged endpoint → now eligible.
    client.post("/api/coordinator/background-check", headers=admin_headers,
                json={"volunteer_email": "sitter@x.org", "status": "cleared"})
    db.expire_all()
    role = db.get(type(role), role.id)
    assert sched.check_eligibility(db, org_id=org.id, profile_id=profile.id,
                                   role=role).eligible is True


def test_expired_background_check_does_not_qualify(db, org, client, admin_headers):
    prog = _program(db, org)
    profile, _ = _volunteer(db, org, "lapsed@x.org")
    ev = sched.create_event(db, org_id=org.id, title="Care", program_id=prog.id)
    s = sched.create_shift(db, org_id=org.id, event_id=ev.id,
                           starts_at=utcnow() + timedelta(hours=24),
                           ends_at=utcnow() + timedelta(hours=26), location="Home")
    role = sched.add_role(db, org_id=org.id, shift_id=s.id, name="Sitter",
                          requires_background_check=True)
    people.set_background_check(db, org_id=org.id, volunteer_email="lapsed@x.org",
                               status="cleared", expires_at=utcnow() - timedelta(days=1))
    db.commit()
    assert sched.check_eligibility(db, org_id=org.id, profile_id=profile.id,
                                   role=role).eligible is False


# --- Invariant: background-check data is internal-only ---------------------- #

def test_background_check_never_serialized_to_a_volunteer(db, org, client, admin_headers):
    _, vol_headers = _volunteer(db, org, "priv@x.org")
    client.post("/api/coordinator/background-check", headers=admin_headers,
                json={"volunteer_email": "priv@x.org", "status": "cleared"})

    me = client.get("/api/auth/me", headers=vol_headers)
    assert me.status_code == 200
    assert "background_check" not in me.text.lower()

    for path in ("/api/shifts/eligible", "/api/shifts/mine"):
        body = client.get(path, headers=vol_headers).text.lower()
        assert "background_check" not in body


def test_background_check_requires_permission(db, org, client):
    _, vol_headers = _volunteer(db, org, "nobody@x.org")
    r = client.post("/api/coordinator/background-check", headers=vol_headers,
                    json={"volunteer_email": "nobody@x.org", "status": "cleared"})
    assert r.status_code == 403
