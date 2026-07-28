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


def test_approval_only_path_never_auto_executes(db, org):
    """The assistant path passes allow_auto_execute=False: even with the auto-promote policy ON,
    it must file a `proposed` record and change nothing / send nothing."""
    from app.modules.training.service import propose_waitlist_promotion
    db.add(OrganizationSetting(org_id=org.id, key="training.auto_promote", value={"enabled": True}))
    session, a, b = _full_session_with_waitlist(db, org)
    session.capacity = 2  # free a seat while B is still waitlisted
    db.commit()
    relay(db)  # flush registration emails so the baseline reflects only what the proposal sends
    before = len(inbox(db, org.id))
    proposal = propose_waitlist_promotion(db, org_id=org.id, session_id=session.id,
                                          requested_by_user_id=None, allow_auto_execute=False)
    db.commit()
    assert proposal is not None and proposal.status == ProposalStatus.proposed
    db.expire_all()
    assert b.registration.status == RegistrationStatus.waitlisted  # unchanged
    relay(db)
    assert len(inbox(db, org.id)) == before  # no email sent by the approval-only path
