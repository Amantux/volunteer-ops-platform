"""Integration: guest→volunteer conversion (no duplicate Person), qualification grant, audit."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.core.db import utcnow
from app.core.security import generate_token, hash_token
from app.modules.identity.models import Person, TokenPurpose, User, VerificationToken
from app.modules.people.models import VolunteerProfile, VolunteerQualification
from app.modules.training.models import TrainingSession
from app.modules.training.service import register_guest, verify_email


def _activation_token(db, org_id, person_id) -> str:
    token = generate_token()
    db.add(VerificationToken(org_id=org_id, person_id=person_id,
                             purpose=TokenPurpose.account_activation, token_hash=hash_token(token),
                             expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    return token


def test_guest_becomes_volunteer_without_duplicate_person(client, db, org):
    session = db.scalar(select(TrainingSession))
    r = register_guest(db, org_id=org.id, session_id=session.id, name="Ada", email="ada@x.org")
    verify_email(db, token=r.verification_token)
    db.commit()
    person = db.scalar(select(Person).where(Person.email == "ada@x.org"))
    people_before = db.scalar(select(func.count()).select_from(Person))

    token = _activation_token(db, org.id, person.id)
    resp = client.post("/api/auth/activate", json={"token": token, "password": "s3cret-pass"})
    assert resp.status_code == 200 and resp.json()["token"]

    # Same Person (no duplicate); now has a User + VolunteerProfile.
    assert db.scalar(select(func.count()).select_from(Person)) == people_before
    assert db.scalar(select(User).where(User.person_id == person.id)) is not None
    assert db.scalar(select(VolunteerProfile).where(VolunteerProfile.person_id == person.id))


def test_completion_grants_qualification_on_activation(client, db, org, admin_headers):
    session = db.scalar(select(TrainingSession))  # its course grants "orientation"
    r = register_guest(db, org_id=org.id, session_id=session.id, name="Bo", email="bo@x.org")
    verify_email(db, token=r.verification_token)
    db.commit()
    reg_id = r.registration.id
    client.post(f"/api/trainer/registrations/{reg_id}/checkin", headers=admin_headers)
    client.post(f"/api/trainer/registrations/{reg_id}/complete", headers=admin_headers)

    person = db.scalar(select(Person).where(Person.email == "bo@x.org"))
    # Not a volunteer yet → qualification deferred.
    assert db.scalar(select(func.count()).select_from(VolunteerQualification)) == 0
    token = _activation_token(db, org.id, person.id)
    client.post("/api/auth/activate", json={"token": token})
    # Activation grants the completed course's qualification.
    assert db.scalar(select(func.count()).select_from(VolunteerQualification)) == 1


def test_sensitive_actions_are_audited(client, db, org, admin_headers):
    # create session (admin) → check-in → completion each emit audit events.
    course_id = db.scalar(select(TrainingSession)).course_id
    client.post("/api/admin/sessions", headers=admin_headers,
                json={"course_id": course_id, "capacity": 5})
    session = db.scalar(select(TrainingSession).order_by(TrainingSession.id.desc()))
    r = register_guest(db, org_id=org.id, session_id=session.id, name="C", email="c@x.org")
    verify_email(db, token=r.verification_token)
    db.commit()
    client.post(f"/api/trainer/registrations/{r.registration.id}/checkin", headers=admin_headers)
    client.post(f"/api/trainer/registrations/{r.registration.id}/complete", headers=admin_headers)

    actions = {e.action for e in db.scalars(select(AuditEvent))}
    assert {"training.create_session", "training.checkin", "training.completion"} <= actions


def test_admin_endpoints_require_auth_and_permission(client, db):
    # No token → 401.
    assert client.post("/api/admin/courses", json={"title": "X"}).status_code == 401
    # Valid session but a user with no roles → 403 (permission denied, audited).
    org_id = db.scalar(select(TrainingSession)).org_id
    person = Person(org_id=org_id, name="Nobody", email="nobody@x.org", email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org_id, person_id=person.id)
    db.add(user)
    db.commit()
    from app.core.session import make_session_token
    headers = {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org_id)}"}
    resp = client.post("/api/admin/courses", headers=headers, json={"title": "X"})
    assert resp.status_code == 403
