"""Shared FastAPI dependencies: DB session, org resolution, and authenticated principal."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import PermissionDenied, Principal, require
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.session import read_session_token
from app.modules.org.models import Organization

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_public_org(db: Session = Depends(get_db)) -> Organization:
    """Resolve the organization for public (unauthenticated) endpoints.

    The initial deployment serves one org; multi-org resolution (by host/slug) plugs in
    here without changing callers.
    """
    org = db.scalar(select(Organization).where(Organization.slug == settings.bootstrap_org_slug))
    if org is None:
        raise HTTPException(status_code=503, detail="Organization not provisioned")
    return org


def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    parsed = read_session_token(credentials.credentials)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user_id, org_id, version = parsed
    # Bind the token to the live user: revoked (version bumped), deactivated, or deleted → 401.
    from app.modules.identity.models import User
    user = db.get(User, user_id)
    if user is None or user.org_id != org_id or not user.is_active \
            or user.session_version != version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return Principal(user_id=user_id, org_id=org_id)


def require_permission(permission: str):
    """Dependency factory: enforce a permission; audit the denial."""

    def dependency(
        principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
    ) -> Principal:
        try:
            require(db, principal, permission)
        except PermissionDenied:
            audit.emit(db, org_id=principal.org_id, action="authz.denied",
                       actor_id=principal.user_id, target_type="permission", target_id=permission)
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
        return principal

    return dependency
