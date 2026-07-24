"""Scheduling endpoints: volunteer self-service + coordinator management."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import PermissionDenied, Principal, require_scoped
from app.modules.people.service import profile_for_user
from app.modules.scheduling import service
from app.modules.scheduling.models import Event, Shift, ShiftRole, ShiftSignup, SignupStatus
from app.modules.scheduling.service import SchedulingError

from .deps import current_principal, get_db, require_permission


def _program_of_event(db: Session, org_id: int, event_id: int) -> int | None:
    ev = db.get(Event, event_id)
    if ev is None or ev.org_id != org_id:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev.program_id


def _program_of_shift(db: Session, org_id: int, shift_id: int) -> int | None:
    shift = db.get(Shift, shift_id)
    if shift is None or shift.org_id != org_id:
        raise HTTPException(status_code=404, detail="Shift not found")
    return _program_of_event(db, org_id, shift.event_id)


def _program_of_signup(db: Session, org_id: int, signup_id: int) -> int | None:
    s = db.get(ShiftSignup, signup_id)
    if s is None or s.org_id != org_id:
        raise HTTPException(status_code=404, detail="Signup not found")
    role = db.get(ShiftRole, s.shift_role_id)
    assert role is not None
    return _program_of_shift(db, org_id, role.shift_id)


def _enforce_scope(db: Session, principal: Principal, permission: str,
                   program_id: int | None) -> None:
    """Fine-grained: the coordinator's role must be scoped to cover this program."""
    try:
        require_scoped(db, principal, permission, program_id=program_id)
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Not permitted for this program") from exc

router = APIRouter(prefix="/api", tags=["scheduling"])


# --- Coordinator ------------------------------------------------------------ #

class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = "event"
    description: str = ""
    program_id: int | None = None
    is_public: bool = False


class ShiftIn(BaseModel):
    event_id: int
    starts_at: datetime
    ends_at: datetime
    location: str = ""


class RoleIn(BaseModel):
    shift_id: int
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(default=1, ge=1)
    required_qualification_type_id: int | None = None


class IdOut(BaseModel):
    id: int


@router.post("/coordinator/events", response_model=IdOut, status_code=201)
def create_event(payload: EventIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("shift.manage"))):
    _enforce_scope(db, principal, "shift.manage", payload.program_id)
    ev = service.create_event(db, org_id=principal.org_id, title=payload.title,
                              kind=payload.kind, description=payload.description,
                              program_id=payload.program_id, is_public=payload.is_public)
    db.commit()
    return IdOut(id=ev.id)


@router.post("/coordinator/shifts", response_model=IdOut, status_code=201)
def create_shift(payload: ShiftIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("shift.manage"))):
    _enforce_scope(db, principal, "shift.manage",
                   _program_of_event(db, principal.org_id, payload.event_id))
    try:
        shift = service.create_shift(db, org_id=principal.org_id, event_id=payload.event_id,
                                     starts_at=payload.starts_at, ends_at=payload.ends_at,
                                     location=payload.location)
    except SchedulingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=shift.id)


@router.post("/coordinator/roles", response_model=IdOut, status_code=201)
def create_role(payload: RoleIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("shift.manage"))):
    _enforce_scope(db, principal, "shift.manage",
                   _program_of_shift(db, principal.org_id, payload.shift_id))
    role = service.add_role(db, org_id=principal.org_id, shift_id=payload.shift_id,
                            name=payload.name, capacity=payload.capacity,
                            required_qualification_type_id=payload.required_qualification_type_id)
    db.commit()
    return IdOut(id=role.id)


@router.get("/coordinator/metrics/staffing")
def staffing(db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("report.view_staffing"))):
    return service.staffing_metrics(db, org_id=principal.org_id)


@router.get("/coordinator/board")
def board(db: Session = Depends(get_db),
          principal: Principal = Depends(require_permission("shift.view_roster"))):
    """Events → shifts → roles → signups for the coordinator schedule view."""
    return service.coordinator_board(db, org_id=principal.org_id)


class CheckinIn(BaseModel):
    signup_id: int


class HoursIn(BaseModel):
    signup_id: int
    hours: float = Field(ge=0)


@router.post("/coordinator/checkin", response_model=IdOut)
def checkin(payload: CheckinIn, db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("shift.record_attendance"))):
    _enforce_scope(db, principal, "shift.record_attendance",
                   _program_of_signup(db, principal.org_id, payload.signup_id))
    try:
        s = service.check_in(db, org_id=principal.org_id, signup_id=payload.signup_id,
                             actor_id=principal.user_id)
    except SchedulingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=s.id)


@router.post("/coordinator/hours", response_model=IdOut, status_code=201)
def log_hours(payload: HoursIn, db: Session = Depends(get_db),
              principal: Principal = Depends(require_permission("shift.record_attendance"))):
    _enforce_scope(db, principal, "shift.record_attendance",
                   _program_of_signup(db, principal.org_id, payload.signup_id))
    try:
        entry = service.record_hours(db, org_id=principal.org_id, signup_id=payload.signup_id,
                                     hours=payload.hours, actor_id=principal.user_id)
    except SchedulingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=entry.id)


# --- Volunteer self-service ------------------------------------------------- #

def _my_profile(db: Session, principal: Principal) -> int:
    profile = profile_for_user(db, org_id=principal.org_id, user_id=principal.user_id)
    if profile is None:
        raise HTTPException(status_code=403, detail="Active volunteer profile required")
    return profile.id


@router.get("/shifts/eligible")
def eligible(db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("shift.view_eligible"))):
    return service.eligible_open_roles(db, org_id=principal.org_id,
                                       profile_id=_my_profile(db, principal))


@router.get("/shifts/mine")
def my_shifts(db: Session = Depends(get_db),
              principal: Principal = Depends(require_permission("shift.view_eligible"))):
    """The signed-in volunteer's own signups (for their dashboard)."""
    return service.my_signups(db, org_id=principal.org_id,
                              profile_id=_my_profile(db, principal))


class SignupIn(BaseModel):
    role_id: int


class SignupOut(BaseModel):
    id: int
    status: str
    waitlisted: bool


@router.post("/shifts/signup", response_model=SignupOut)
def signup(payload: SignupIn, db: Session = Depends(get_db),
           principal: Principal = Depends(require_permission("shift.signup"))):
    try:
        s = service.signup_for_shift(db, org_id=principal.org_id,
                                     profile_id=_my_profile(db, principal), role_id=payload.role_id)
    except SchedulingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return SignupOut(id=s.id, status=s.status.value, waitlisted=s.status == SignupStatus.waitlisted)


@router.post("/shifts/signups/{signup_id}/cancel", response_model=IdOut)
def cancel(signup_id: int, db: Session = Depends(get_db),
           principal: Principal = Depends(require_permission("shift.signup"))):
    # A volunteer may only cancel their own signup.
    profile_id = _my_profile(db, principal)
    s = db.get(ShiftSignup, signup_id)
    if s is None or s.org_id != principal.org_id or s.volunteer_profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Signup not found")
    try:
        service.cancel_signup(db, org_id=principal.org_id, signup_id=signup_id,
                              actor_id=principal.user_id)
    except SchedulingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=signup_id)


@router.get("/shifts/calendar.ics")
def my_calendar(db: Session = Depends(get_db),
                principal: Principal = Depends(current_principal)):
    """An iCalendar feed of the volunteer's confirmed/attended shifts."""
    profile_id = _my_profile(db, principal)
    signups = db.scalars(select(ShiftSignup).where(
        ShiftSignup.org_id == principal.org_id,
        ShiftSignup.volunteer_profile_id == profile_id,
        ShiftSignup.status.in_([SignupStatus.confirmed, SignupStatus.attended]),
    )).all()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//VolunteerOps//EN"]
    for s in signups:
        shift = s.role.shift
        fmt = "%Y%m%dT%H%M%SZ"
        lines += [
            "BEGIN:VEVENT", f"UID:shift-{s.id}@volunteer-ops",
            f"DTSTART:{shift.starts_at.strftime(fmt)}", f"DTEND:{shift.ends_at.strftime(fmt)}",
            f"SUMMARY:{s.role.name} — {shift.event.title}",
            f"LOCATION:{shift.location}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return Response(content="\r\n".join(lines), media_type="text/calendar")
