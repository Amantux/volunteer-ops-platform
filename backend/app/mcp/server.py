"""Minimal MCP-style JSON-RPC server over stdio, backed by the governed tool layer.

This is the transport: it exposes ``tools/list``, ``tools/call``, ``resources/list``, and
``resources/read``, delegating to ``invoke_tool`` / ``resources`` so authorization, org
scoping, risk gating, and audit are enforced in one place. Every call is attributed to a
human/service/agent identity via a VOP session token (``VOP_MCP_SESSION_TOKEN``) — the
server never holds raw DB, shell, or secret access.

Run: ``VOP_MCP_SESSION_TOKEN=<token> python -m app.mcp.server``
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from app.core.authz import Principal
from app.core.db import SessionLocal
from app.core.session import read_session_token

from . import resources, tools


class MCPError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _principal_from_env() -> Principal:
    token = os.environ.get("VOP_MCP_SESSION_TOKEN", "")
    parsed = read_session_token(token)
    if parsed is None:
        raise MCPError(-32001, "MCP requires a valid VOP_MCP_SESSION_TOKEN")
    user_id, org_id, version = parsed
    # Same revocation check as the HTTP surface: reject if the user is gone, deactivated, in a
    # different org, or the token's session_version is stale (logged out / force-signed-out).
    from app.modules.identity.models import User
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.org_id != org_id or not user.is_active \
                or user.session_version != version:
            raise MCPError(-32001, "session token is invalid or has been revoked")
    return Principal(user_id=user_id, org_id=org_id)


def dispatch(method: str, params: dict, principal: Principal) -> Any:
    """Handle one JSON-RPC method. Separated from the loop so it is unit-testable."""
    if method == "initialize":
        return {"protocolVersion": "0.1", "serverInfo": {"name": "volunteer-ops", "version": "0.1"}}
    if method == "tools/list":
        return {"tools": [
            {"name": c.name, "risk": c.risk.value, "approvalRequired": c.approval_required,
             "reversible": c.reversible, "idempotent": c.idempotent,
             "dataClassification": c.data_classification, "permission": c.permission}
            for c in tools.contracts()
        ]}
    if method == "tools/call":
        name = params["name"]
        args = params.get("arguments", {})
        with SessionLocal() as db:
            try:
                return {"result": tools.invoke_tool(db, principal, name, args)}
            except tools.ToolError as exc:
                raise MCPError(-32002, str(exc)) from exc
    if method == "resources/list":
        return {"resources": resources.list_resources()}
    if method == "resources/read":
        with SessionLocal() as db:
            try:
                return {"contents": resources.read_resource(db, principal, params["uri"])}
            except KeyError as exc:
                raise MCPError(-32003, str(exc)) from exc
    raise MCPError(-32601, f"method not found: {method}")


def handle_rpc(message: dict, principal: Principal) -> dict:
    rpc_id = message.get("id")
    try:
        result = dispatch(message.get("method", ""), message.get("params", {}) or {}, principal)
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
    except MCPError as exc:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": exc.code, "message": exc.message}}


def main() -> None:  # pragma: no cover - stdio loop
    principal = _principal_from_env()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        sys.stdout.write(json.dumps(handle_rpc(message, principal)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    main()
