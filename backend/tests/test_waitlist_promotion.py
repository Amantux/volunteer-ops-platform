"""Integration: cancellation → waitlist promotion (approval path and narrow auto policy)."""

from __future__ import annotations

from conftest import inbox, relay
from sqlalchemy import select

from app.modules.agents.models import AgentProposal, ProposalStatus
from app.modules.org.models import OrganizationSetting
from app.modules.training.models import RegistrationStatus, TrainingSession
from app.modules.training.service import (
    cancel_registration,
    register_guest,
    verify_email,
)


def _full_session_with_waitlist(db, org):
    session = db.scalar(select(TrainingSession))
    session.capacity = 1
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    verify_email(db, token=a.verification_token)  # A confirmed, holds the seat
    b = register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")
    assert b.waitlisted is True
    db.commit()
    return session, a, b


def test_cancel_creates_approval_proposal_then_admin_approves(client, db, org, admin_headers):
    session, a, b = _full_session_with_waitlist(db, org)
    # Cancel A → a promotion proposal is created but NOT auto-executed (no policy).
    proposal = cancel_registration(db, org_id=org.id, registration_id=a.registration.id)
    db.commit()
    assert proposal is not None and proposal.status == ProposalStatus.proposed
    # B is still waitlisted until a human approves.
    assert b.registration.status == RegistrationStatus.waitlisted

    resp = client.post(f"/api/admin/proposals/{proposal.id}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert b.registration.status == RegistrationStatus.confirmed
    relay(db)
    assert any("A spot opened up" in m.subject for m in inbox(db, org.id))


def test_narrow_auto_promote_policy_executes_without_approval(db, org):
    db.add(OrganizationSetting(org_id=org.id, key="training.auto_promote",
                               value={"enabled": True}))
    session, a, b = _full_session_with_waitlist(db, org)
    proposal = cancel_registration(db, org_id=org.id, registration_id=a.registration.id)
    db.commit()
    assert proposal.status == ProposalStatus.auto_executed
    db.expire_all()
    assert b.registration.status == RegistrationStatus.confirmed
    relay(db)
    assert any("A spot opened up" in m.subject for m in inbox(db, org.id))


def test_no_promotion_when_no_seat_free(db, org):
    session = db.scalar(select(TrainingSession))
    session.capacity = 2
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    db.commit()
    # Cancelling with no one waitlisted yields no proposal.
    proposal = cancel_registration(db, org_id=org.id, registration_id=a.registration.id)
    assert proposal is None
    assert db.scalar(select(AgentProposal)) is None
