"""MCP tool governance: authorization + audit enforced inside the tool, org-scoped."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.audit import AuditEvent
from app.core.authz import Principal
from app.mcp.tools import ToolError, invoke_tool
from app.modules.identity.models import Person, User
from app.modules.org.models import Organization
from app.modules.training.models import TrainingSession


def _principal_without_roles(db, org_id) -> Principal:
    person = Person(org_id=org_id, name="Svc", email="svc@x.org", email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org_id, person_id=person.id)
    db.add(user)
    db.commit()
    return Principal(user_id=user.id, org_id=org_id)


def test_tool_denies_without_permission_and_audits(db, org):
    principal = _principal_without_roles(db, org.id)
    session = db.scalar(select(TrainingSession))
    with pytest.raises(ToolError):
        invoke_tool(db, principal, "register_training_guest",
                    {"session_id": session.id, "name": "X", "email": "x@x.org"})
    assert any(e.action == "mcp.denied" for e in db.scalars(select(AuditEvent)))


def test_tool_registers_guest_with_permission_and_audits(db, org, admin_user):
    principal = Principal(user_id=admin_user.id, org_id=org.id)
    session = db.scalar(select(TrainingSession))
    result = invoke_tool(db, principal, "register_training_guest",
                         {"session_id": session.id, "name": "Ada", "email": "ada@x.org"})
    assert result["registration_id"] and result["status"] == "registered"
    assert any(e.action == "mcp.register_training_guest" for e in db.scalars(select(AuditEvent)))


def test_promote_tool_requires_approval_by_default(db, org, admin_user):
    from app.modules.training.service import cancel_registration, register_guest, verify_email

    session = db.scalar(select(TrainingSession))
    session.capacity = 1
    db.flush()
    a = register_guest(db, org_id=org.id, session_id=session.id, name="A", email="a@x.org")
    verify_email(db, token=a.verification_token)
    register_guest(db, org_id=org.id, session_id=session.id, name="B", email="b@x.org")
    cancel_registration(db, org_id=org.id, registration_id=a.registration.id)
    db.commit()

    principal = Principal(user_id=admin_user.id, org_id=org.id)
    result = invoke_tool(db, principal, "promote_waitlist_candidate", {"session_id": session.id})
    # A proposal exists but is not executed without approval.
    assert result.get("proposal_id") and result["executed"] is False


def test_tool_is_org_scoped(db, org, admin_user):
    """A principal cannot act on another org's session through the tool."""
    other = Organization(name="Other Org", slug="other")
    db.add(other)
    db.flush()
    db.commit()
    session = db.scalar(select(TrainingSession))  # session in `org`
    # A principal whose org is `other` trying to reach org's session must fail.
    other_principal = Principal(user_id=admin_user.id, org_id=other.id)
    with pytest.raises(ToolError):
        invoke_tool(db, other_principal, "register_training_guest",
                    {"session_id": session.id, "name": "X", "email": "x2@x.org"})
