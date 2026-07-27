"""Celery worker: relays the transactional outbox (idempotent) on a schedule.

The relay logic lives in `app.core.outbox`; the worker/beat just drive it. In tests the
same `relay_pending` is called directly, so behavior is identical.
"""

from __future__ import annotations

from celery import Celery

import app.modules.communications.service  # noqa: F401  (registers the outbox email handler)
import app.modules.donations.service  # noqa: F401  (registers donation.checkout/succeeded handlers)
import app.modules.social.service  # noqa: F401  (registers the "social.publish" handler)
import app.modules.workflows.service  # noqa: F401  (registers the "workflow.notify" handler)
from app.core.config import settings
from app.core.db import SessionLocal

celery_app = Celery("vop", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "relay-outbox": {"task": "app.worker.relay_outbox", "schedule": 5.0},
    "expire-holds": {"task": "app.worker.expire_holds", "schedule": 300.0},
    "send-due-campaigns": {"task": "app.worker.send_due_campaigns", "schedule": 60.0},
    "publish-due-social": {"task": "app.worker.publish_due_social", "schedule": 60.0},
    "sweep-workflow-deadlines": {"task": "app.worker.sweep_workflow_deadlines", "schedule": 300.0},
    "send-shift-reminders": {"task": "app.worker.send_shift_reminders", "schedule": 3600.0},
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="app.worker.relay_outbox")
def relay_outbox() -> int:
    from app.core.outbox import relay_pending

    with SessionLocal() as db:
        return relay_pending(db)


@celery_app.task(name="app.worker.expire_holds")
def expire_holds() -> int:
    """Reclaim seats held by never-verified registrations past their TTL."""
    from app.modules.training.service import expire_unconfirmed_holds

    with SessionLocal() as db:
        return expire_unconfirmed_holds(db)


@celery_app.task(name="app.worker.send_due_campaigns")
def send_due_campaigns() -> int:
    """Send approved campaigns whose scheduled time has arrived."""
    from app.modules.communications.campaigns import send_due_campaigns as _send

    with SessionLocal() as db:
        return _send(db)


@celery_app.task(name="app.worker.publish_due_social")
def publish_due_social() -> int:
    """Publish approved social posts whose scheduled time has arrived."""
    from app.modules.social.service import publish_due_social_posts

    with SessionLocal() as db:
        return publish_due_social_posts(db)


@celery_app.task(name="app.worker.sweep_workflow_deadlines")
def sweep_workflow_deadlines() -> int:
    """Escalate workflow instances past their SLA deadline."""
    from app.modules.workflows.service import sweep_deadlines

    with SessionLocal() as db:
        n = sweep_deadlines(db)
        db.commit()
        return n


@celery_app.task(name="app.worker.send_shift_reminders")
def send_shift_reminders() -> int:
    """Email confirmed volunteers ahead of their upcoming shifts."""
    from app.modules.scheduling.service import send_shift_reminders as _remind

    with SessionLocal() as db:
        n = _remind(db)
        db.commit()
        return n
