"""MCP transport: JSON-RPC dispatch delegates to the governed tool/resource layer."""

from __future__ import annotations

from sqlalchemy import select

from app.core.authz import Principal
from app.mcp.server import handle_rpc
from app.modules.training.models import TrainingSession


def _principal(org, admin_user) -> Principal:
    return Principal(user_id=admin_user.id, org_id=org.id)


def test_tools_list_exposes_contracts(db, org, admin_user):
    resp = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                      _principal(org, admin_user))
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"register_training_guest", "promote_waitlist_candidate",
            "get_training_funnel_metrics", "list_training_sessions"} <= names
    # Read-only tools are marked r0; promotion is approval-required.
    by_name = {t["name"]: t for t in resp["result"]["tools"]}
    assert by_name["get_training_funnel_metrics"]["risk"] == "r0_read"
    assert by_name["promote_waitlist_candidate"]["approvalRequired"] is True


def test_tools_call_read_metric(db, org, admin_user):
    resp = handle_rpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "get_training_funnel_metrics", "arguments": {}}},
        _principal(org, admin_user),
    )
    assert "funnel" in resp["result"]["result"]
    assert "total" in resp["result"]["result"]["funnel"]


def test_tools_call_write_registers_guest(client, db, org, admin_user):
    sid = db.scalar(select(TrainingSession)).id
    resp = handle_rpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "register_training_guest",
                    "arguments": {"session_id": sid, "name": "Ada", "email": "ada@x.org"}}},
        _principal(org, admin_user),
    )
    assert resp["result"]["result"]["registration_id"]


def test_resources_list_and_read(db, org, admin_user):
    principal = _principal(org, admin_user)
    listing = handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list"}, principal)
    uris = {r["uri"] for r in listing["result"]["resources"]}
    assert "vop://org-config" in uris and "vop://training-catalog" in uris

    read = handle_rpc(
        {"jsonrpc": "2.0", "id": 5, "method": "resources/read",
         "params": {"uri": "vop://org-config"}}, principal)
    assert read["result"]["contents"]["id"] == org.id


def test_unknown_method_and_tool_return_errors(db, org, admin_user):
    principal = _principal(org, admin_user)
    bad_method = handle_rpc({"jsonrpc": "2.0", "id": 6, "method": "nope"}, principal)
    assert bad_method["error"]["code"] == -32601

    bad_tool = handle_rpc(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "does_not_exist", "arguments": {}}}, principal)
    assert bad_tool["error"]["code"] == -32002


def test_tool_call_denied_without_permission(db, org):
    from app.modules.identity.models import Person, User

    person = Person(org_id=org.id, name="NoRole", email="norole@x.org", email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.commit()
    resp = handle_rpc(
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
         "params": {"name": "get_training_funnel_metrics", "arguments": {}}},
        Principal(user_id=user.id, org_id=org.id),
    )
    assert resp["error"]["code"] == -32002  # permission denied surfaced as a tool error
