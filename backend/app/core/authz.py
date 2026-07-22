"""Server-side authorization: resolve a user's permissions within an org + scope.

Called by API dependencies, by workers before side effects, and inside MCP tools —
never only at the route layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.models import RolePermission, User, UserRoleAssignment


class PermissionDenied(Exception):
    def __init__(self, permission: str) -> None:
        super().__init__(f"permission denied: {permission}")
        self.permission = permission


@dataclass(frozen=True)
class Principal:
    """The authenticated actor for a request/tool call."""

    user_id: int
    org_id: int


def permissions_for(db: Session, *, user_id: int, org_id: int) -> set[str]:
    """All permission strings a user holds in an org (any scope)."""
    rows = db.execute(
        select(RolePermission.permission)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == RolePermission.role_id)
        .join(User, User.id == UserRoleAssignment.user_id)
        .where(User.id == user_id, User.org_id == org_id, UserRoleAssignment.org_id == org_id)
    ).all()
    return {r[0] for r in rows}


def has_permission(db: Session, principal: Principal, permission: str) -> bool:
    return permission in permissions_for(db, user_id=principal.user_id, org_id=principal.org_id)


def require(db: Session, principal: Principal, permission: str) -> None:
    """Raise PermissionDenied unless the principal holds the permission. Denials are audited
    by the caller boundary (API/worker/MCP)."""
    if not has_permission(db, principal, permission):
        raise PermissionDenied(permission)
