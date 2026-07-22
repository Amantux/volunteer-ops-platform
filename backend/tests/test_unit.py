"""Unit tests: deterministic capacity/waitlist, verification tokens, agent risk, permissions."""

from __future__ import annotations

from sqlalchemy import select

from app.core.authz import Principal, has_permission
from app.modules.agents.risk import RiskLevel, classify_action
from app.modules.identity.models import Person
from app.modules.org.models import Organization
from app.modules.training.models import RegistrationStatus, TrainingSession
from app.modules.training.service import TrainingError, register_guest, verify_email


def _org(db):
    return db.scalar(select(Organization))


def _session(db):
    return db.scalar(select(TrainingSession))


def test_capacity_and_waitlist_are_deterministic(db):
    org, session = _org(db), _session(db)
    session.capacity = 1
    db.flush()
    r1 = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    r2 = register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")
    assert r1.waitlisted is False
    assert r2.waitlisted is True
    assert r2.registration.waitlist_position == 1
    db.refresh(session)
    assert session.occupied_count == 1  # only the provisional/confirmed seat counts


def test_verification_token_is_single_use_and_confirms(db):
    org, session = _org(db), _session(db)
    result = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    db.commit()
    reg = verify_email(db, token=result.verification_token)
    assert reg.status == RegistrationStatus.confirmed
    person = db.scalar(select(Person).where(Person.email == "a@x.org"))
    assert person.email_verified is True
    # Reusing the token fails.
    try:
        verify_email(db, token=result.verification_token)
        raise AssertionError("token should be single-use")
    except TrainingError:
        pass


def test_duplicate_registration_rejected(db):
    org, session = _org(db), _session(db)
    register_guest(db, org_id=org.id, session_id=session.id, name="A", email="dup@x.org")
    try:
        register_guest(db, org_id=org.id, session_id=session.id, name="A", email="dup@x.org")
        raise AssertionError("duplicate registration should be rejected")
    except TrainingError:
        pass


def test_agent_risk_classification():
    assert classify_action("comms.send_bulk") == RiskLevel.r4_prohibited
    assert classify_action("record.delete") == RiskLevel.r4_prohibited
    assert classify_action("promote_waitlist") == RiskLevel.r3_approval
    assert classify_action("comms.draft") == RiskLevel.r1_draft
    assert classify_action("training_read_metrics") == RiskLevel.r0_read
    # Unknown actions fail safe to approval-required, never silent execute.
    assert classify_action("something.unknown") == RiskLevel.r3_approval


def test_permissions_resolve_per_role(db, admin_user):
    org = _org(db)
    p = Principal(user_id=admin_user.id, org_id=org.id)
    assert has_permission(db, p, "training.manage_course")
    assert not has_permission(db, p, "donation.refund")  # not granted
