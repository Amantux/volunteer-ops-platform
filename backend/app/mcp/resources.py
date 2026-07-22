"""Read-only MCP resources (org- and permission-scoped).

Resources expose reference data (catalog, org config) — never raw tables, secrets, or
cross-org data. Each reader is called with an authenticated, org-scoped principal.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import Principal
from app.modules.org.models import Organization
from app.modules.training.models import TrainingSession

_READERS: dict[str, tuple[str, Callable[[Session, Principal], dict]]] = {}


def resource(uri: str, description: str):
    def register(fn: Callable[[Session, Principal], dict]):
        _READERS[uri] = (description, fn)
        return fn

    return register


def list_resources() -> list[dict]:
    return [{"uri": uri, "description": desc} for uri, (desc, _) in _READERS.items()]


def read_resource(db: Session, principal: Principal, uri: str) -> dict:
    entry = _READERS.get(uri)
    if entry is None:
        raise KeyError(f"unknown resource: {uri}")
    return entry[1](db, principal)


@resource("vop://org-config", "Organization identity + timezone (org-scoped).")
def _org_config(db: Session, principal: Principal) -> dict:
    org = db.get(Organization, principal.org_id)
    return {"id": org.id, "name": org.name, "slug": org.slug, "timezone": org.timezone}


@resource("vop://training-catalog", "Public training sessions currently offered.")
def _training_catalog(db: Session, principal: Principal) -> dict:
    rows = db.scalars(
        select(TrainingSession).where(
            TrainingSession.org_id == principal.org_id, TrainingSession.is_open.is_(True)
        )
    ).all()
    return {"sessions": [
        {"id": s.id, "course": s.course.title, "location": s.location,
         "seats_available": s.seats_available}
        for s in rows if s.course.is_public
    ]}
