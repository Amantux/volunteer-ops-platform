"""Admin endpoints — manage training, approve promotions, view metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import Principal
from app.modules.training.service import (
    TrainingError,
    approve_promotion,
    create_course,
    create_session,
    training_funnel,
)

from .deps import get_db, require_permission

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CourseIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    is_public: bool = True


class SessionIn(BaseModel):
    course_id: int
    capacity: int | None = Field(default=None, ge=1)
    location: str = ""


class IdOut(BaseModel):
    id: int


@router.post("/courses", response_model=IdOut, status_code=201)
def create_course_ep(payload: CourseIn, db: Session = Depends(get_db),
                     principal: Principal = Depends(require_permission("training.manage_course"))):
    course = create_course(db, org_id=principal.org_id, title=payload.title,
                           description=payload.description, is_public=payload.is_public)
    audit.emit(db, org_id=principal.org_id, action="training.create_course",
               actor_id=principal.user_id, target_type="course", target_id=course.id)
    db.commit()
    return IdOut(id=course.id)


@router.post("/sessions", response_model=IdOut, status_code=201)
def create_session_ep(payload: SessionIn, db: Session = Depends(get_db),
                     principal: Principal = Depends(require_permission("training.manage_session"))):
    session = create_session(db, org_id=principal.org_id, course_id=payload.course_id,
                             capacity=payload.capacity, location=payload.location)
    audit.emit(db, org_id=principal.org_id, action="training.create_session",
               actor_id=principal.user_id, target_type="session", target_id=session.id)
    db.commit()
    return IdOut(id=session.id)


@router.post("/proposals/{proposal_id}/approve", response_model=IdOut)
def approve_ep(proposal_id: int, db: Session = Depends(get_db),
              principal: Principal = Depends(require_permission("training.approve_promotion"))):
    try:
        proposal = approve_promotion(db, org_id=principal.org_id, proposal_id=proposal_id,
                                     decided_by_user_id=principal.user_id)
    except TrainingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=proposal.id)


@router.get("/metrics/training-funnel")
def funnel_ep(session_id: int | None = None, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("report.view_training"))):
    return training_funnel(db, org_id=principal.org_id, session_id=session_id)
