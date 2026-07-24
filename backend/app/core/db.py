"""Database engine, session, base classes, and the org-scoped repository.

The `OrgScopedRepository` enforces the tenant boundary: every query is filtered by
`org_id`, so forgetting the scope is impossible through the repository. Direct session
use outside a repository is reserved for cross-cutting infrastructure (migrations, the
outbox relay) and reviewed accordingly.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import DateTime, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# In-memory SQLite (tests) must share ONE connection across every session, or each
# connection gets its own private database. StaticPool does that; it also means all
# sessions observe the same committed state (matching Postgres read-committed semantics)
# instead of the per-connection snapshots a file-SQLite QueuePool can hand back.
_engine_kwargs: dict[str, object] = {}
if settings.database_url in ("sqlite://", "sqlite:///:memory:"):
    from sqlalchemy.pool import StaticPool

    _engine_kwargs["poolclass"] = StaticPool
engine = create_engine(
    settings.database_url, connect_args=_connect_args, future=True, **_engine_kwargs
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> datetime:
    # Naive UTC by convention — portable across SQLite (drops tz) and Postgres.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ModelT = TypeVar("ModelT")


class OrgScopedRepository(Generic[ModelT]):
    """Base repository that pins every query to a single organization."""

    model: type[ModelT]

    def __init__(self, db: Session, org_id: int) -> None:
        self.db = db
        self.org_id = org_id

    def _scoped(self):
        return select(self.model).where(self.model.org_id == self.org_id)

    def get(self, pk: int) -> ModelT | None:
        obj = self.db.get(self.model, pk)
        # Never return a row from another org, even by direct id.
        if obj is not None and getattr(obj, "org_id", None) != self.org_id:
            return None
        return obj

    def list(self) -> list[ModelT]:
        return list(self.db.scalars(self._scoped()))

    def add(self, obj: ModelT) -> ModelT:
        if getattr(obj, "org_id", None) != self.org_id:
            raise ValueError("attempted to add a record outside the repository's org scope")
        self.db.add(obj)
        self.db.flush()
        return obj


def init_db() -> None:
    """Create all tables (dev/test convenience; production uses Alembic migrations)."""
    from app import models  # noqa: F401  (imports all model modules)

    Base.metadata.create_all(bind=engine)
