"""Operational endpoints: readiness (DB + Redis) and metrics the runbooks consume."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.db import SessionLocal, utcnow
from app.core.outbox import OutboxEvent

router = APIRouter(prefix="/api", tags=["ops"])

# Retries after which an unprocessed outbox event is considered "stuck".
_STUCK_ATTEMPTS = 5


def _redis_ok() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


@router.get("/ready")
def ready() -> dict[str, object]:
    """Readiness: the DB is reachable AND Redis (broker/cache) responds. 503 otherwise."""
    checks: dict[str, bool] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        checks["database"] = False
    checks["redis"] = _redis_ok()
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not-ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@router.get("/metrics")
def metrics() -> dict[str, object]:
    """Lightweight operational metrics — the signals the runbooks/alerts read.

    Outbox backlog is the proxy for email/worker health: a rising ``pending`` or any
    ``stuck`` events means the worker isn't relaying (queue has no consumer / provider down).
    """
    with SessionLocal() as db:
        pending = db.scalar(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.processed_at.is_(None))
        ) or 0
        stuck = db.scalar(
            select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.processed_at.is_(None), OutboxEvent.attempts >= _STUCK_ATTEMPTS)
        ) or 0
        oldest = db.scalar(
            select(func.min(OutboxEvent.created_at)).where(OutboxEvent.processed_at.is_(None))
        )
        oldest_age = (utcnow() - oldest).total_seconds() if oldest is not None else 0.0
    return {
        "outbox_pending": int(pending),
        "outbox_stuck": int(stuck),
        "outbox_oldest_pending_age_seconds": round(oldest_age, 1),
        "redis_ok": _redis_ok(),
    }
