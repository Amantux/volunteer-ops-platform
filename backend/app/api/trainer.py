"""Trainer endpoints — check-in and completion (scoped, audited)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authz import PermissionDenied, Principal
from app.modules.training.service import TrainingError, check_in, record_completion

from .deps import get_db, require_permission

router = APIRouter(prefix="/api/trainer", tags=["trainer"])


class RegistrationOut(BaseModel):
    id: int
    status: str


@router.post("/registrations/{registration_id}/checkin", response_model=RegistrationOut)
def checkin(registration_id: int, db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("training.record_attendance"))):
    try:
        reg = check_in(db, org_id=principal.org_id, registration_id=registration_id,
                       principal=principal)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Not permitted for this session") from exc
    except TrainingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return RegistrationOut(id=reg.id, status=reg.status.value)


@router.post("/registrations/{registration_id}/complete", response_model=RegistrationOut)
def complete(registration_id: int, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("training.record_completion"))):
    try:
        reg = record_completion(db, org_id=principal.org_id, registration_id=registration_id,
                                principal=principal)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Not permitted for this session") from exc
    except TrainingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return RegistrationOut(id=reg.id, status=reg.status.value)
