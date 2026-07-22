"""Regression tests for adversarial-review findings (must stay fixed)."""

from __future__ import annotations

import pytest
from conftest import relay
from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.core.authz import Principal
from app.mcp.tools import ToolContract, ToolError, invoke_tool, tool
from app.modules.agents.risk import RiskLevel
from app.modules.communications.models import EmailMessage
from app.modules.identity.models import Person, Role, User, UserRoleAssignment
from app.modules.training.models import RegistrationStatus, TrainingRegistration, TrainingSession
from app.modules.training.service import (
    approve_promotion,
    cancel_registration,
    create_session,
    register_guest,
    verify_email,
)


def _session(db):
    return db.scalar(select(TrainingSession))


def test_approval_does_not_overfill_capacity(db, org, admin_headers, client):
    """BLOCKER 1: a seat freed by a cancel can be taken before approval — approving must
    re-check availability and refuse, never over-fill."""
    session = _session(db)
    session.capacity = 1
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    verify_email(db, token=a.verification_token)  # A confirmed (seat taken)
    register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")  # waitlist
    proposal = cancel_registration(db, org_id=org.id, registration_id=a.registration.id)
    db.commit()
    # C grabs the freed seat (as a provisional 'registered' hold) before B is approved.
    c = register_guest(db, org_id=org.id, session_id=session.id, name="C", email="c@x.org")
    db.commit()
    assert c.waitlisted is False
    assert c.registration.status == RegistrationStatus.registered  # occupies the freed seat

    # Approving B must now fail — no seat available.
    with pytest.raises(Exception):
        approve_promotion(db, org_id=org.id, proposal_id=proposal.id, decided_by_user_id=1)
    db.rollback()
    # Occupancy never exceeds capacity.
    occupied = db.scalar(select(func.count()).select_from(TrainingRegistration).where(
        TrainingRegistration.session_id == session.id,
        TrainingRegistration.status.in_(TrainingSession.OCCUPYING)))
    assert occupied == 1


def test_verify_confirms_the_tokens_own_registration(db, org):
    """BLOCKER 2: verifying one session's token must confirm THAT registration, not the
    newest one."""
    s1 = _session(db)
    s2 = create_session(db, org_id=org.id, course_id=s1.course_id, capacity=10)
    db.flush()
    r1 = register_guest(db, org_id=org.id, session_id=s1.id, name="Ada", email="ada@x.org")
    r2 = register_guest(db, org_id=org.id, session_id=s2.id, name="Ada", email="ada@x.org")
    db.commit()
    # Verify session 1's token → session 1 confirmed, session 2 untouched.
    verify_email(db, token=r1.verification_token)
    db.refresh(r1.registration)
    db.refresh(r2.registration)
    assert r1.registration.status == RegistrationStatus.confirmed
    assert r2.registration.status == RegistrationStatus.registered
    # Then session 2's token confirms session 2.
    verify_email(db, token=r2.verification_token)
    db.refresh(r2.registration)
    assert r2.registration.status == RegistrationStatus.confirmed


def test_outbox_failure_leaves_no_orphan_message(db, org, client, monkeypatch):
    """Should-fix: a failing email handler must roll back its partial EmailMessage."""
    sid = _session(db).id
    client.post(f"/api/public/sessions/{sid}/register", json={"name": "A", "email": "a@x.org"})

    from app.modules.communications import service as comms
    monkeypatch.setattr(comms.InboxAdapter, "send",
                        lambda self, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert relay(db) == 0
    # No half-written message row survived the failure.
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0

    monkeypatch.undo()
    assert relay(db) == 1
    msgs = db.scalars(select(EmailMessage)).all()
    assert len(msgs) == 1 and msgs[0].status == "sent"


def test_trainer_cannot_act_on_another_trainers_session(db, org, client):
    """Should-fix: object-level scoping — a trainer may only act on sessions they run."""
    # A session owned by a different trainer (user id that isn't ours).
    session = _session(db)
    other_owner = User(org_id=org.id, person_id=db.scalar(select(Person)).id)  # any user id
    session.trainer_user_id = 999999  # not our trainer
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    verify_email(db, token=a.verification_token)
    reg_id = a.registration.id

    # Create a trainer (has record_attendance but NOT manage_any_session).
    person = Person(org_id=org.id, name="Trainer", email="tr@x.org", email_verified=True)
    db.add(person)
    db.flush()
    tuser = User(org_id=org.id, person_id=person.id)
    db.add(tuser)
    db.flush()
    trole = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == "trainer"))
    db.add(UserRoleAssignment(org_id=org.id, user_id=tuser.id, role_id=trole.id))
    db.commit()

    from app.core.session import make_session_token
    headers = {"Authorization": f"Bearer {make_session_token(user_id=tuser.id, org_id=org.id)}"}
    resp = client.post(f"/api/trainer/registrations/{reg_id}/checkin", headers=headers)
    assert resp.status_code == 403
    del other_owner  # (only constructed to show intent; not persisted)


def test_prohibited_mcp_tool_never_executes(db, org, admin_user):
    """Should-fix: MCP governance blocks R4 (prohibited) tools regardless of permission."""

    @tool(ToolContract(
        name="_danger_delete_all", permission="training.register_guest",
        risk=RiskLevel.r4_prohibited, approval_required=True, reversible=False, idempotent=False,
        audit_action="mcp._danger", data_classification="Restricted",
    ))
    def _danger(db, principal, args):  # pragma: no cover - must never run
        raise AssertionError("prohibited tool executed!")

    principal = Principal(user_id=admin_user.id, org_id=org.id)
    with pytest.raises(ToolError):
        invoke_tool(db, principal, "_danger_delete_all", {})
    assert any(e.action == "mcp.prohibited" for e in db.scalars(select(AuditEvent)))
