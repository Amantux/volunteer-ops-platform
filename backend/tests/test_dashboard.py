"""Executive overview endpoint: cross-domain metrics, permission-gated, with donation figures
withheld from a non-finance (coordinator) viewer."""

from __future__ import annotations

from sqlalchemy import select

from app.core.session import make_session_token
from app.modules.identity.models import Person, Role, User, UserRoleAssignment


def _user_with_role(db, org, email, role_key):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == role_key))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


def test_overview_requires_permission(db, org, client):
    vol = _user_with_role(db, org, "vol@x.org", "volunteer")
    assert client.get("/api/admin/overview", headers=vol).status_code == 403


def test_overview_returns_cross_domain_metrics_for_admin(db, org, client, admin_headers):
    r = client.get("/api/admin/overview", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("active_volunteers", "upcoming_shifts_7d", "applications_by_state",
                "approved_hours"):
        assert key in body
    # org_admin holds donation.view → donation figures are included.
    assert "donations" in body and "volume_minor_units" in body["donations"]


def test_overview_withholds_donations_from_coordinator(db, org, client):
    # Coordinator holds report.view_staffing but NOT donation.view.
    coord = _user_with_role(db, org, "coord@x.org", "coordinator")
    r = client.get("/api/admin/overview", headers=coord)
    assert r.status_code == 200
    assert "donations" not in r.json()
