"""Public, unauthenticated endpoints: browse sessions, register as a guest, verify email."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import botcheck, ratelimit
from app.modules.org.models import Organization
from app.modules.training.models import RegistrationStatus, TrainingSession
from app.modules.training.service import TrainingError, register_guest, verify_email

from .deps import get_db, get_public_org

router = APIRouter(prefix="/api/public", tags=["public"])


class SessionOut(BaseModel):
    id: int
    course_title: str
    description: str
    location: str
    starts_at: datetime | None
    ends_at: datetime | None
    capacity: int | None
    seats_available: bool


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str = ""
    # Cloudflare Turnstile token when bot-check is enabled (ignored when disabled).
    bot_token: str | None = None


class RegisterOut(BaseModel):
    status: str
    waitlisted: bool
    message: str


class VerifyIn(BaseModel):
    token: str


def _to_out(s: TrainingSession) -> SessionOut:
    return SessionOut(
        id=s.id, course_title=s.course.title, description=s.course.description,
        location=s.location, starts_at=s.starts_at, ends_at=s.ends_at,
        capacity=s.capacity, seats_available=s.seats_available,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: Session = Depends(get_db), org: Organization = Depends(get_public_org)):
    rows = db.scalars(
        select(TrainingSession)
        .join(TrainingSession.course)
        .where(TrainingSession.org_id == org.id, TrainingSession.is_open.is_(True))
        .order_by(TrainingSession.starts_at.is_(None), TrainingSession.starts_at)
    )
    return [_to_out(s) for s in rows if s.course.is_public]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db),
                org: Organization = Depends(get_public_org)):
    s = db.get(TrainingSession, session_id)
    if s is None or s.org_id != org.id or not s.course.is_public:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_out(s)


@router.post("/sessions/{session_id}/register", response_model=RegisterOut)
def register(session_id: int, payload: RegisterIn, request: Request,
             db: Session = Depends(get_db), org: Organization = Depends(get_public_org)):
    client = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"register:{client}", limit=5, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again shortly.")
    if not botcheck.verify(payload.bot_token, remote_ip=client):
        raise HTTPException(status_code=400, detail="Bot check failed. Please try again.")
    try:
        result = register_guest(db, org_id=org.id, session_id=session_id,
                                name=payload.name, email=str(payload.email), phone=payload.phone)
    except TrainingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    msg = ("This session is full — check your email to confirm, and we'll waitlist you."
           if result.waitlisted
           else "Almost done! Check your email to confirm your registration.")
    return RegisterOut(status=result.registration.status.value, waitlisted=result.waitlisted,
                       message=msg)


@router.post("/verify", response_model=RegisterOut)
def verify(payload: VerifyIn, db: Session = Depends(get_db)):
    try:
        reg = verify_email(db, token=payload.token)
    except TrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    if reg is None:
        return RegisterOut(status="verified", waitlisted=False, message="Email verified.")
    waitlisted = reg.status == RegistrationStatus.waitlisted
    return RegisterOut(
        status=reg.status.value, waitlisted=waitlisted,
        message=("You're on the waitlist — we'll email you if a spot opens."
                 if waitlisted else "You're confirmed. Thank you for volunteering!"),
    )
