"""Executive overview endpoint — one cross-domain read for leadership. Gated on
`report.view_staffing`; donation figures are included only when the caller also holds
`donation.view`, so donor data never reaches a non-finance viewer (INV-DONOR-SEPARATION)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.authz import Principal, has_permission
from app.modules import reporting

from .deps import get_db, require_permission

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("report.view_staffing"))):
    include_donations = has_permission(db, principal, "donation.view")
    return reporting.overview(db, org_id=principal.org_id, include_donations=include_donations)
