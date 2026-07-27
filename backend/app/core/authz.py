"""Server-side authorization: resolve a user's permissions within an org + scope.

Called by API dependencies, by workers before side effects, and inside MCP tools —
never only at the route layer.

Two layers:
- coarse: ``has_permission`` / ``require`` — does the user hold the permission in ANY
  scope? Used as a fast pre-filter at the route boundary.
- fine: ``authorize`` / ``require_scoped`` — does the user hold the permission via an
  assignment whose scope actually *covers* the target resource (org-wide, or the target's
  program)? This is what prevents a program-scoped coordinator from acting org-wide.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.models import RolePermission, RoleScopeType, User, UserRoleAssignment


class PermissionDenied(Exception):
    def __init__(self, permission: str) -> None:
        super().__init__(f"permission denied: {permission}")
        self.permission = permission


@dataclass(frozen=True)
class Principal:
    """The authenticated actor for a request/tool call."""

    user_id: int
    org_id: int


@dataclass(frozen=True)
class Grant:
    permission: str
    scope_type: RoleScopeType
    scope_id: int | None


def grants_for(db: Session, *, user_id: int, org_id: int) -> list[Grant]:
    """Every (permission, scope) a user holds in the org, from their role assignments."""
    rows = db.execute(
        select(RolePermission.permission, UserRoleAssignment.scope_type, UserRoleAssignment.scope_id)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == RolePermission.role_id)
        .join(User, User.id == UserRoleAssignment.user_id)
        .where(User.id == user_id, User.org_id == org_id, UserRoleAssignment.org_id == org_id)
    ).all()
    return [Grant(permission=p, scope_type=st, scope_id=sid) for p, st, sid in rows]


def permissions_for(db: Session, *, user_id: int, org_id: int) -> set[str]:
    """All permission strings a user holds in an org (any scope)."""
    return {g.permission for g in grants_for(db, user_id=user_id, org_id=org_id)}


def has_permission(db: Session, principal: Principal, permission: str) -> bool:
    """Coarse check: does the user hold this permission in ANY scope?"""
    return permission in permissions_for(db, user_id=principal.user_id, org_id=principal.org_id)


def require(db: Session, principal: Principal, permission: str) -> None:
    if not has_permission(db, principal, permission):
        raise PermissionDenied(permission)


def _covers(grant: Grant, *, program_id: int | None) -> bool:
    """Does a grant's scope cover the target resource?

    - An org-scoped grant (scope_type=org, or no scope_id) covers everything in the org.
    - A program-scoped grant covers a resource in that same program only.
    - Team/location scopes are not yet associated with resources; they cover nothing below
      org until those associations exist (they never over-grant).
    """
    if grant.scope_type == RoleScopeType.org or grant.scope_id is None:
        return True
    if grant.scope_type == RoleScopeType.program:
        return program_id is not None and grant.scope_id == program_id
    return False


def authorize(db: Session, principal: Principal, permission: str, *,
              program_id: int | None = None) -> bool:
    """Fine check: does the user hold ``permission`` via a grant whose scope covers the
    target resource (identified by its program, when it has one)?"""
    return any(
        g.permission == permission and _covers(g, program_id=program_id)
        for g in grants_for(db, user_id=principal.user_id, org_id=principal.org_id)
    )


def require_scoped(db: Session, principal: Principal, permission: str, *,
                   program_id: int | None = None) -> None:
    if not authorize(db, principal, permission, program_id=program_id):
        raise PermissionDenied(permission)


def scoped_program_ids(db: Session, principal: Principal, permission: str) -> set[int] | None:
    """The set of program ids the principal may act on for ``permission``. Returns ``None`` when
    the principal holds the permission org-wide (i.e. covers *all* programs) — callers should
    treat ``None`` as "no program restriction" and any set (including empty) as a whitelist."""
    ids: set[int] = set()
    for g in grants_for(db, user_id=principal.user_id, org_id=principal.org_id):
        if g.permission != permission:
            continue
        if g.scope_type == RoleScopeType.org or g.scope_id is None:
            return None  # org-wide grant covers everything
        if g.scope_type == RoleScopeType.program:
            ids.add(g.scope_id)
    return ids
