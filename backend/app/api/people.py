"""People-management endpoints: long-term program enrollment + (sensitive) background-check
status. Background-check data is internal-only — it is never returned by any volunteer/public
endpoint and is written only via the privileged endpoint below, audited on change."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authz import PermissionDenied, Principal, require_scoped, scoped_program_ids
from app.modules.people import service as people
from app.modules.people.models import ProgramEnrollment

from .deps import get_db, require_permission

router = APIRouter(prefix="/api", tags=["people"])


class IdOut(BaseModel):
    id: int


def _enforce_program_scope(db: Session, principal: Principal, permission: str,
                           program_id: int | None) -> None:
    try:
        require_scoped(db, principal, permission, program_id=program_id)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Not permitted for this program") from exc


# --- Program enrollment ------------------------------------------------------------------ #

class EnrollIn(BaseModel):
    volunteer_email: str
    program_id: int
    role: str = Field(min_length=1, max_length=60)
    notes: str = Field(default="", max_length=500)


class EnrollmentStatusIn(BaseModel):
    status: str


@router.get("/coordinator/enrollments")
def list_enrollments(program_id: int | None = None, role: str | None = None,
                     status: str | None = None, db: Session = Depends(get_db),
                     principal: Principal = Depends(require_permission("enrollment.view"))):
    # Fine-grained scope: a program-scoped coordinator must not read other programs' rosters/PII.
    if program_id is not None:
        _enforce_program_scope(db, principal, "enrollment.view", program_id)
        allowed = None  # already narrowed to a program this principal covers
    else:
        # No filter: restrict to the programs the principal covers (None = org-wide, all).
        allowed = scoped_program_ids(db, principal, "enrollment.view")
    return people.list_enrollments(db, org_id=principal.org_id, program_id=program_id,
                                   role=role, status=status, allowed_program_ids=allowed)


@router.post("/coordinator/enrollments", response_model=IdOut, status_code=201)
def create_enrollment(payload: EnrollIn, db: Session = Depends(get_db),
                      principal: Principal = Depends(require_permission("enrollment.manage"))):
    _enforce_program_scope(db, principal, "enrollment.manage", payload.program_id)
    try:
        enr = people.enroll(db, org_id=principal.org_id, volunteer_email=payload.volunteer_email,
                            program_id=payload.program_id, role=payload.role, notes=payload.notes,
                            actor_id=principal.user_id)
    except people.PeopleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=enr.id)


@router.post("/coordinator/enrollments/{enrollment_id}/status", response_model=IdOut)
def set_enrollment_status(enrollment_id: int, payload: EnrollmentStatusIn,
                          db: Session = Depends(get_db),
                          principal: Principal = Depends(require_permission("enrollment.manage"))):
    enr = db.get(ProgramEnrollment, enrollment_id)
    if enr is None or enr.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    _enforce_program_scope(db, principal, "enrollment.manage", enr.program_id)
    try:
        enr = people.set_enrollment_status(db, org_id=principal.org_id,
                                           enrollment_id=enrollment_id, status=payload.status,
                                           actor_id=principal.user_id)
    except people.PeopleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=enr.id)


# --- Background check (sensitive; internal-only) ----------------------------------------- #

class BackgroundCheckIn(BaseModel):
    volunteer_email: str
    status: str
    expires_at: datetime | None = None


@router.post("/coordinator/background-check", response_model=IdOut)
def set_background_check(
    payload: BackgroundCheckIn, db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("volunteer.manage_background_check")),
):
    # Background check is a person-level (not program-level) sensitive attribute → require an
    # org-wide grant (program_id=None is satisfiable only by an org-scoped grant), so a
    # program-scoped coordinator can't alter it for volunteers outside their remit.
    _enforce_program_scope(db, principal, "volunteer.manage_background_check", None)
    try:
        profile = people.set_background_check(
            db, org_id=principal.org_id, volunteer_email=payload.volunteer_email,
            status=payload.status, expires_at=payload.expires_at, actor_id=principal.user_id)
    except people.PeopleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=profile.id)
