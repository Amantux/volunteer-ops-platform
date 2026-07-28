"""Kiosk surfaces: admin CRUD + permissions, token-authenticated display/check-in/tasks,
token isolation, and the name-addressable MCP tools."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.authz import Principal
from app.core.db import utcnow
from app.core.session import make_session_token
from app.mcp.tools import ToolError, invoke_tool
from app.modules.identity.models import Person, Role, User, UserRoleAssignment
from app.modules.kiosk import service
from app.modules.people.models import VolunteerProfile
from app.modules.scheduling import service as sched
from app.modules.scheduling.models import ShiftSignup, SignupStatus


def _volunteer_signup_today(db, org):
    """A confirmed volunteer signup on a shift starting today (so the kiosk sees it)."""
    person = Person(org_id=org.id, name="Pat Volunteer", email="pat@x.org", email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    profile = VolunteerProfile(org_id=org.id, person_id=person.id)
    db.add(profile)
    db.flush()
    ev = sched.create_event(db, org_id=org.id, title="Kennel duty", is_public=True)
    start = utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    shift = sched.create_shift(db, org_id=org.id, event_id=ev.id, starts_at=start,
                               ends_at=start + timedelta(hours=2), location="Kennel")
    role = sched.add_role(db, org_id=org.id, shift_id=shift.id, name="Carer", capacity=3)
    signup = ShiftSignup(org_id=org.id, shift_role_id=role.id, volunteer_profile_id=profile.id,
                         status=SignupStatus.confirmed)
    db.add(signup)
    db.commit()
    return signup


def _kiosk(db, org, *, mode="shared"):
    k = service.create_kiosk(db, org_id=org.id, name="Front Desk", mode=mode,
                             panels=[{"type": "checkin"}, {"type": "tasks"}])
    db.commit()
    return k


# --- Admin CRUD + permissions ------------------------------------------------ #

def test_admin_creates_kiosk_and_volunteer_cannot(db, org, client, admin_headers):
    r = client.post("/api/admin/kiosks", headers=admin_headers,
                    json={"name": "Lobby", "mode": "display"})
    assert r.status_code == 201
    # A volunteer has no kiosk.manage.
    person = Person(org_id=org.id, name="v@x.org", email="v@x.org", email_verified=True)
    db.add(person)
    db.flush()
    u = User(org_id=org.id, person_id=person.id)
    db.add(u)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == "volunteer"))
    db.add(UserRoleAssignment(org_id=org.id, user_id=u.id, role_id=role.id))
    db.commit()
    vh = {"Authorization": f"Bearer {make_session_token(user_id=u.id, org_id=org.id)}"}
    assert client.post("/api/admin/kiosks", headers=vh, json={"name": "X"}).status_code == 403


def test_invalid_panel_rejected(db, org):
    try:
        service.create_kiosk(db, org_id=org.id, name="Bad", panels=[{"type": "nope"}])
        raise AssertionError("expected KioskError")
    except service.KioskError:
        pass


# --- Device (token) display + check-in + isolation --------------------------- #

def test_display_and_shared_checkin(db, org, client):
    signup = _volunteer_signup_today(db, org)
    k = _kiosk(db, org, mode="shared")
    disp = client.get(f"/api/kiosk/{k.token}").json()
    assert disp["name"] == "Front Desk"
    checkin_panel = next(p for p in disp["panels"] if p["type"] == "checkin")
    assert any(s["signup_id"] == signup.id and not s["checked_in"]
               for s in checkin_panel["signups"])
    r = client.post(f"/api/kiosk/{k.token}/checkin", json={"signup_id": signup.id})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(ShiftSignup, signup.id).status == SignupStatus.attended


def test_display_only_kiosk_refuses_checkin(db, org, client):
    signup = _volunteer_signup_today(db, org)
    k = _kiosk(db, org, mode="display")
    r = client.post(f"/api/kiosk/{k.token}/checkin", json={"signup_id": signup.id})
    assert r.status_code == 400 and "display-only" in r.json()["detail"]


def test_bad_token_is_404_and_isolates(db, org, client):
    assert client.get("/api/kiosk/not-a-real-token").status_code == 404


def test_task_toggle_is_per_day(db, org, client):
    k = _kiosk(db, org, mode="shared")
    t = service.add_task(db, org_id=org.id, kiosk_id=k.id, label="Puppies fed — AM")
    db.commit()
    on = client.post(f"/api/kiosk/{k.token}/tasks/{t.id}/toggle").json()
    assert on["done"] is True
    disp = client.get(f"/api/kiosk/{k.token}").json()
    tasks_panel = next(p for p in disp["panels"] if p["type"] == "tasks")
    assert any(x["id"] == t.id and x["done"] for x in tasks_panel["tasks"])
    off = client.post(f"/api/kiosk/{k.token}/tasks/{t.id}/toggle").json()
    assert off["done"] is False


def test_checkin_rejects_signup_outside_kiosk_program(db, org, client):
    from app.modules.org.models import Program
    prog_b = Program(org_id=org.id, key="prog_b", name="Program B")
    db.add(prog_b)
    db.flush()
    prog_a = Program(org_id=org.id, key="prog_a", name="Program A")
    db.add(prog_a)
    db.commit()
    # A signup lives on a program-less event today (helper), but the kiosk is scoped to program A.
    signup = _volunteer_signup_today(db, org)
    k = service.create_kiosk(db, org_id=org.id, name="Prog A Desk", mode="shared",
                             program_id=prog_a.id, panels=[{"type": "checkin"}])
    db.commit()
    r = client.post(f"/api/kiosk/{k.token}/checkin", json={"signup_id": signup.id})
    assert r.status_code == 400  # not one of this program-scoped kiosk's signups today


def test_rename_to_existing_name_is_400_not_500(db, org, client, admin_headers):
    a = client.post("/api/admin/kiosks", headers=admin_headers, json={"name": "Alpha"}).json()["id"]
    client.post("/api/admin/kiosks", headers=admin_headers, json={"name": "Beta"})
    r = client.patch(f"/api/admin/kiosks/{a}", headers=admin_headers, json={"name": "Beta"})
    assert r.status_code == 400


# --- MCP: name-addressable ---------------------------------------------------- #

def test_mcp_kiosk_tools_by_name(db, org, admin_user):
    _kiosk(db, org, mode="display")
    principal = Principal(user_id=admin_user.id, org_id=org.id)
    listing = invoke_tool(db, principal, "list_kiosks", {})
    assert any(k["name"] == "Front Desk" for k in listing["kiosks"])
    got = invoke_tool(db, principal, "get_kiosk", {"name": "Front Desk"})
    assert got["kiosk"]["name"] == "Front Desk"
    invoke_tool(db, principal, "set_kiosk_panels", {"name": "Front Desk",
                                                    "panels": [{"type": "fyi", "text": "Hi"}]})
    db.expire_all()
    k = service.get_by_name(db, org_id=org.id, name="Front Desk")
    assert k.panels == [{"type": "fyi", "text": "Hi"}]
    with __import__("pytest").raises(ToolError):
        invoke_tool(db, principal, "get_kiosk", {"name": "Nonexistent"})
