"""Test fixtures. Uses a file-based SQLite DB (shared across connections) for speed;
production runs Postgres. Models are written portably so behavior matches."""

from __future__ import annotations

import os
import tempfile

# Point the app at a throwaway SQLite DB + the dev inbox email adapter BEFORE importing app.
_DB_PATH = os.path.join(tempfile.gettempdir(), "vop_test.db")
os.environ.setdefault("VOP_DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("VOP_EMAIL_PROVIDER", "inbox")
os.environ.setdefault("VOP_APP_SECRET", "test-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.session import make_session_token  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.models import Person, User  # noqa: E402
from app.modules.org.models import Organization  # noqa: E402
from app.seed import seed_bootstrap  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_bootstrap(db)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def org(db) -> Organization:
    return db.scalar(select(Organization))


@pytest.fixture
def admin_user(db, org) -> User:
    person = db.scalar(select(Person).where(Person.org_id == org.id, Person.name == "Org Admin"))
    return person.user


@pytest.fixture
def admin_headers(admin_user, org) -> dict[str, str]:
    token = make_session_token(user_id=admin_user.id, org_id=org.id)
    return {"Authorization": f"Bearer {token}"}


def relay(db):
    """Run the outbox relay (what the Celery worker does) and return processed count."""
    from app.core.outbox import relay_pending

    return relay_pending(db)


def inbox(db, org_id: int):
    from app.modules.communications.models import InboxMessage

    return list(db.scalars(select(InboxMessage).where(InboxMessage.org_id == org_id)))
