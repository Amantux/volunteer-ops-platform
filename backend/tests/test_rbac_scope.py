"""Scope-aware RBAC: a program-scoped role must not grant authority in another program."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.authz import Principal, authorize
from app.core.db import utcnow
from app.core.session import make_session_token
from app.modules.identity.models import Person, Role, RoleScopeType, User, UserRoleAssignment
from app.modules.org.models import Program


def _program(db, org, key):
    p = Program(org_id=org.id, key=key, name=key.title())
    db.add(p)
    db.commit()  # release the write lock so API requests (separate session) can proceed
    return p


def _coordinator_scoped_to(db, org, email, program_id):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == "coordinator"))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id,
                              scope_type=RoleScopeType.program, scope_id=program_id))
    db.commit()
    headers = {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}
    return user, headers


def test_authorize_honors_program_scope(db, org):
    p1, p2 = _program(db, org, "p1"), _program(db, org, "p2")
    user, _ = _coordinator_scoped_to(db, org, "coord@x.org", p1.id)
    principal = Principal(user_id=user.id, org_id=org.id)
    # Holds shift.manage only within program 1.
    assert authorize(db, principal, "shift.manage", program_id=p1.id) is True
    assert authorize(db, principal, "shift.manage", program_id=p2.id) is False
    # And NOT org-wide (program-scoped grant does not cover org-level resources).
    assert authorize(db, principal, "shift.manage", program_id=None) is False


def test_program_coordinator_cannot_manage_another_program_via_api(client, db, org, admin_headers):
    p1, p2 = _program(db, org, "p1"), _program(db, org, "p2")
    # Org admin (org-scoped) creates an event in each program.
    ev1 = client.post("/api/coordinator/events", headers=admin_headers,
                      json={"title": "P1 event", "program_id": p1.id}).json()["id"]
    ev2 = client.post("/api/coordinator/events", headers=admin_headers,
                      json={"title": "P2 event", "program_id": p2.id}).json()["id"]

    _, coord = _coordinator_scoped_to(db, org, "c1@x.org", p1.id)
    start = (utcnow() + timedelta(days=1)).isoformat()
    end = (utcnow() + timedelta(days=1, hours=2)).isoformat()
    # Allowed in their own program...
    ok = client.post("/api/coordinator/shifts", headers=coord,
                     json={"event_id": ev1, "starts_at": start, "ends_at": end})
    assert ok.status_code == 201, ok.text
    # ...denied in another program.
    denied = client.post("/api/coordinator/shifts", headers=coord,
                         json={"event_id": ev2, "starts_at": start, "ends_at": end})
    assert denied.status_code == 403


def test_org_admin_scope_covers_all_programs(client, db, org, admin_headers):
    p1 = _program(db, org, "p1")
    ev = client.post("/api/coordinator/events", headers=admin_headers,
                     json={"title": "E", "program_id": p1.id})
    assert ev.status_code == 201  # org-scoped admin covers any program
