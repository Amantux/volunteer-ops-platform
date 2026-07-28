"""Cross-domain executive overview — a single read model composed from the per-domain services
so leadership sees volunteers, upcoming shifts, the application funnel, and (for finance viewers)
donations in one place. Read-only and org-scoped; donation figures are included only when the
caller holds `donation.view` (INV-DONOR-SEPARATION preserved)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.modules.donations.service import donation_metrics
from app.modules.people.models import VolunteerProfile
from app.modules.scheduling.models import Shift
from app.modules.scheduling.service import hours_report
from app.modules.workflows.models import WorkflowInstance


def overview(db: Session, *, org_id: int, include_donations: bool) -> dict:
    active_volunteers = db.scalar(select(func.count()).select_from(VolunteerProfile).where(
        VolunteerProfile.org_id == org_id, VolunteerProfile.status == "active")) or 0

    now = utcnow()
    upcoming_shifts = db.scalar(select(func.count()).select_from(Shift).where(
        Shift.org_id == org_id, Shift.starts_at >= now,
        Shift.starts_at < now + timedelta(days=7))) or 0

    # Application funnel: open form-driven workflow instances grouped by their current state.
    funnel_rows = db.execute(
        select(WorkflowInstance.current_state, func.count())
        .where(WorkflowInstance.org_id == org_id,
               WorkflowInstance.subject_type == "form_submission")
        .group_by(WorkflowInstance.current_state)).all()
    applications_by_state = {state: int(count) for state, count in funnel_rows}

    result: dict = {
        "active_volunteers": int(active_volunteers),
        "upcoming_shifts_7d": int(upcoming_shifts),
        "applications_by_state": applications_by_state,
        "approved_hours": hours_report(db, org_id=org_id)["total_hours"],
    }
    if include_donations:
        result["donations"] = donation_metrics(db, org_id=org_id)
    return result
