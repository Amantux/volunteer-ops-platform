"""Authenticated dashboard read endpoints: /auth/me, /shifts/mine, /coordinator/board."""

from __future__ import annotations

from test_scheduling import _shift, _volunteer


def test_me_reports_identity_and_permissions(client, db, org, admin_headers):
    # A volunteer sees their signup permissions and a profile; no coordinator report perm.
    _, headers = _volunteer(db, org, "vol@x.org")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == "vol@x.org"
    assert me["has_volunteer_profile"] is True
    assert "shift.signup" in me["permissions"]
    assert "report.view_staffing" not in me["permissions"]

    # The org admin has the coordinator/report permissions but no volunteer profile.
    admin_me = client.get("/api/auth/me", headers=admin_headers).json()
    assert "report.view_staffing" in admin_me["permissions"]
    assert admin_me["has_volunteer_profile"] is False


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_my_shifts_lists_only_own_signups(client, db, org):
    _, role = _shift(db, org, capacity=2)
    _, mine = _volunteer(db, org, "mine@x.org")
    _, theirs = _volunteer(db, org, "theirs@x.org")
    client.post("/api/shifts/signup", headers=mine, json={"role_id": role.id})
    client.post("/api/shifts/signup", headers=theirs, json={"role_id": role.id})

    rows = client.get("/api/shifts/mine", headers=mine).json()
    assert len(rows) == 1
    assert rows[0]["event_title"] == "Cleanup" and rows[0]["role"] == "Helper"
    assert rows[0]["status"] == "confirmed" and rows[0]["waitlisted"] is False


def test_coordinator_board_shows_events_shifts_and_signups(client, db, org, admin_headers):
    _, role = _shift(db, org, capacity=2)
    _, vol = _volunteer(db, org, "vol@x.org")
    client.post("/api/shifts/signup", headers=vol, json={"role_id": role.id})

    board = client.get("/api/coordinator/board", headers=admin_headers).json()
    # Seed-independent: find the event this test created (the demo seed adds others).
    event = next(e for e in board if e["title"] == "Cleanup")
    role_row = event["shifts"][0]["roles"][0]
    assert role_row["capacity"] == 2 and role_row["filled"] == 1
    assert role_row["signups"][0]["volunteer"] == "vol@x.org"


def test_coordinator_board_requires_roster_permission(client, db, org):
    # A plain volunteer lacks shift.view_roster → 403.
    _, headers = _volunteer(db, org, "vol@x.org")
    assert client.get("/api/coordinator/board", headers=headers).status_code == 403
