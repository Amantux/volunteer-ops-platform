"""Scheduling domain services: eligibility, signup, waitlist, check-in, hours, metrics.

Eligibility and conflict detection are deterministic, explainable code (not agent logic):
callers get a reason when a volunteer is ineligible or double-booked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.modules.people.models import VolunteerQualification

from .models import (
    Event,
    Shift,
    ShiftRole,
    ShiftSignup,
    SignupStatus,
    VolunteerHourEntry,
)


class SchedulingError(Exception):
    pass


@dataclass
class Eligibility:
    eligible: bool
    reason: str


# --- Setup (coordinator) ---------------------------------------------------- #

def create_event(db: Session, *, org_id: int, title: str, kind: str = "event",
                 description: str = "", program_id: int | None = None,
                 is_public: bool = False) -> Event:
    event = Event(org_id=org_id, title=title, kind=kind, description=description,
                  program_id=program_id, is_public=is_public)
    db.add(event)
    db.flush()
    return event


def create_shift(db: Session, *, org_id: int, event_id: int, starts_at: datetime,
                 ends_at: datetime, location: str = "") -> Shift:
    if ends_at <= starts_at:
        raise SchedulingError("shift end must be after start")
    shift = Shift(org_id=org_id, event_id=event_id, starts_at=starts_at, ends_at=ends_at,
                  location=location)
    db.add(shift)
    db.flush()
    return shift


def add_role(db: Session, *, org_id: int, shift_id: int, name: str, capacity: int = 1,
             required_qualification_type_id: int | None = None) -> ShiftRole:
    role = ShiftRole(org_id=org_id, shift_id=shift_id, name=name, capacity=capacity,
                     required_qualification_type_id=required_qualification_type_id)
    db.add(role)
    db.flush()
    return role


# --- Eligibility + conflict (deterministic, explainable) -------------------- #

def check_eligibility(db: Session, *, org_id: int, profile_id: int, role: ShiftRole) -> Eligibility:
    if role.required_qualification_type_id is None:
        return Eligibility(True, "no qualification required")
    qual = db.scalar(select(VolunteerQualification).where(
        VolunteerQualification.org_id == org_id,
        VolunteerQualification.profile_id == profile_id,
        VolunteerQualification.qualification_type_id == role.required_qualification_type_id,
    ))
    if qual is None:
        return Eligibility(False, "missing required qualification")
    if qual.expires_at is not None and qual.expires_at < utcnow():
        return Eligibility(False, "required qualification has expired")
    return Eligibility(True, "holds the required qualification")


def has_time_conflict(db: Session, *, org_id: int, profile_id: int, shift: Shift) -> bool:
    """True if the volunteer already has a confirmed/attended signup on an overlapping shift."""
    signups = db.scalars(select(ShiftSignup).where(
        ShiftSignup.org_id == org_id,
        ShiftSignup.volunteer_profile_id == profile_id,
        ShiftSignup.status.in_(ShiftRole.OCCUPYING),
    )).all()
    for s in signups:
        other_role = db.get(ShiftRole, s.shift_role_id)
        assert other_role is not None
        other = other_role.shift
        if other.id != shift.id and other.overlaps(shift):
            return True
    return False


# --- Signup / cancel / waitlist --------------------------------------------- #

def _role_occupied(db: Session, role_id: int) -> int:
    return db.scalar(select(func.count()).select_from(ShiftSignup).where(
        ShiftSignup.shift_role_id == role_id, ShiftSignup.status.in_(ShiftRole.OCCUPYING),
    )) or 0


def signup_for_shift(db: Session, *, org_id: int, profile_id: int, role_id: int) -> ShiftSignup:
    role = db.get(ShiftRole, role_id)
    if role is None or role.org_id != org_id:
        raise SchedulingError("shift role not found")
    shift = role.shift
    if not shift.is_open:
        raise SchedulingError("this shift is closed")

    eligibility = check_eligibility(db, org_id=org_id, profile_id=profile_id, role=role)
    if not eligibility.eligible:
        raise SchedulingError(f"not eligible: {eligibility.reason}")
    if has_time_conflict(db, org_id=org_id, profile_id=profile_id, shift=shift):
        raise SchedulingError("you already have a shift that overlaps this time")

    existing = db.scalar(select(ShiftSignup).where(
        ShiftSignup.shift_role_id == role_id, ShiftSignup.volunteer_profile_id == profile_id))
    if existing is not None and existing.status != SignupStatus.cancelled:
        raise SchedulingError("already signed up for this role")

    waitlisted = _role_occupied(db, role_id) >= role.capacity
    status = SignupStatus.waitlisted if waitlisted else SignupStatus.confirmed
    position = None
    if waitlisted:
        highest = db.scalar(select(func.max(ShiftSignup.waitlist_position)).where(
            ShiftSignup.shift_role_id == role_id))
        position = (highest or 0) + 1

    if existing is not None:
        existing.status = status
        existing.waitlist_position = position
        signup = existing
    else:
        signup = ShiftSignup(org_id=org_id, shift_role_id=role_id, volunteer_profile_id=profile_id,
                             status=status, waitlist_position=position)
        db.add(signup)
    db.flush()
    audit.emit(db, org_id=org_id, action="shift.signup", actor_type="user",
               actor_id=profile_id, target_type="shift_signup", target_id=signup.id)
    return signup


def cancel_signup(db: Session, *, org_id: int, signup_id: int, actor_id) -> ShiftSignup:
    signup = db.get(ShiftSignup, signup_id)
    if signup is None or signup.org_id != org_id:
        raise SchedulingError("signup not found")
    role_id = signup.shift_role_id
    signup.status = SignupStatus.cancelled
    signup.waitlist_position = None
    db.flush()
    audit.emit(db, org_id=org_id, action="shift.cancel", actor_id=actor_id,
               target_type="shift_signup", target_id=signup.id)
    _promote_first_waitlisted(db, org_id=org_id, role_id=role_id)
    return signup


def _promote_first_waitlisted(db: Session, *, org_id: int, role_id: int) -> None:
    """Deterministically promote the next waitlisted volunteer if a seat is free."""
    role = db.get(ShiftRole, role_id)
    assert role is not None
    if _role_occupied(db, role_id) >= role.capacity:
        return
    candidate = db.scalar(select(ShiftSignup).where(
        ShiftSignup.shift_role_id == role_id, ShiftSignup.status == SignupStatus.waitlisted,
    ).order_by(ShiftSignup.waitlist_position))
    if candidate is None:
        return
    candidate.status = SignupStatus.confirmed
    candidate.waitlist_position = None
    db.flush()
    audit.emit(db, org_id=org_id, action="shift.waitlist_promote", actor_type="service",
               actor_id="scheduler", target_type="shift_signup", target_id=candidate.id)


# --- Check-in + hours ------------------------------------------------------- #

def check_in(db: Session, *, org_id: int, signup_id: int, actor_id) -> ShiftSignup:
    signup = db.get(ShiftSignup, signup_id)
    if signup is None or signup.org_id != org_id:
        raise SchedulingError("signup not found")
    signup.status = SignupStatus.attended
    signup.checked_in_at = utcnow()
    db.flush()
    audit.emit(db, org_id=org_id, action="shift.checkin", actor_id=actor_id,
               target_type="shift_signup", target_id=signup.id)
    return signup


def record_hours(db: Session, *, org_id: int, signup_id: int, hours: float,
                 actor_id) -> VolunteerHourEntry:
    signup = db.get(ShiftSignup, signup_id)
    if signup is None or signup.org_id != org_id:
        raise SchedulingError("signup not found")
    entry = VolunteerHourEntry(org_id=org_id, volunteer_profile_id=signup.volunteer_profile_id,
                               shift_signup_id=signup.id, hours=hours, source="shift")
    db.add(entry)
    db.flush()
    audit.emit(db, org_id=org_id, action="hours.record", actor_id=actor_id,
               target_type="hour_entry", target_id=entry.id, meta={"hours": hours})
    return entry


def approve_hours(db: Session, *, org_id: int, entry_id: int, actor_user_id: int):
    entry = db.get(VolunteerHourEntry, entry_id)
    if entry is None or entry.org_id != org_id:
        raise SchedulingError("hour entry not found")
    entry.approved = True
    entry.approved_by_user_id = actor_user_id
    db.flush()
    audit.emit(db, org_id=org_id, action="hours.approve", actor_id=actor_user_id,
               target_type="hour_entry", target_id=entry.id)
    return entry


# --- Volunteer-facing + coordinator metrics --------------------------------- #

def eligible_open_roles(db: Session, *, org_id: int, profile_id: int) -> list[dict]:
    """Open roles the volunteer is eligible for and not already signed up to."""
    roles = db.scalars(
        select(ShiftRole).join(ShiftRole.shift).where(
            ShiftRole.org_id == org_id, Shift.is_open.is_(True), Shift.starts_at > utcnow())
    ).all()
    out: list[dict] = []
    for role in roles:
        elig = check_eligibility(db, org_id=org_id, profile_id=profile_id, role=role)
        if not elig.eligible or not role.seats_available:
            continue
        already = db.scalar(select(ShiftSignup).where(
            ShiftSignup.shift_role_id == role.id,
            ShiftSignup.volunteer_profile_id == profile_id,
            ShiftSignup.status != SignupStatus.cancelled))
        if already is not None:
            continue
        out.append({"role_id": role.id, "role": role.name, "shift_id": role.shift_id,
                    "starts_at": role.shift.starts_at.isoformat(), "location": role.shift.location,
                    "why_eligible": elig.reason})
    return out


def staffing_metrics(db: Session, *, org_id: int) -> dict:
    roles = db.scalars(select(ShiftRole).where(ShiftRole.org_id == org_id)).all()
    total_capacity = sum(r.capacity for r in roles)
    filled = sum(r.confirmed_count for r in roles)
    understaffed = [
        {"role_id": r.id, "role": r.name, "shift_id": r.shift_id,
         "filled": r.confirmed_count, "capacity": r.capacity}
        for r in roles if r.confirmed_count < r.capacity
    ]
    return {
        "roles": len(roles),
        "capacity": total_capacity,
        "filled": filled,
        "fill_rate": round(filled / total_capacity, 3) if total_capacity else 0.0,
        "understaffed": understaffed,
    }


# --- Read models for the authenticated dashboards --------------------------- #

def my_signups(db: Session, *, org_id: int, profile_id: int) -> list[dict]:
    """A volunteer's own non-cancelled signups, upcoming first, for their dashboard."""
    signups = db.scalars(
        select(ShiftSignup)
        .join(ShiftSignup.role)
        .join(ShiftRole.shift)
        .where(
            ShiftSignup.org_id == org_id,
            ShiftSignup.volunteer_profile_id == profile_id,
            ShiftSignup.status != SignupStatus.cancelled,
        )
        .order_by(Shift.starts_at)
    ).all()
    out: list[dict] = []
    for s in signups:
        shift = s.role.shift
        out.append({
            "signup_id": s.id,
            "status": s.status.value,
            "waitlisted": s.status == SignupStatus.waitlisted,
            "event_title": shift.event.title,
            "role": s.role.name,
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "location": shift.location,
        })
    return out


def coordinator_board(db: Session, *, org_id: int) -> list[dict]:
    """Upcoming events → shifts → roles with their signups, for the coordinator view.

    Includes each signup's id + volunteer name + status so the coordinator can check in
    attendees and log hours against a concrete signup.
    """
    from app.modules.identity.models import Person
    from app.modules.people.models import VolunteerProfile

    events = db.scalars(
        select(Event).where(Event.org_id == org_id, Event.status == "active").order_by(Event.id)
    ).all()
    names: dict[int, str] = {
        pid: name
        for pid, name in db.execute(
            select(VolunteerProfile.id, Person.name)
            .join(Person, Person.id == VolunteerProfile.person_id)
            .where(VolunteerProfile.org_id == org_id)
        ).all()
    }
    board: list[dict] = []
    for event in events:
        shifts = []
        for shift in sorted(event.shifts, key=lambda s: s.starts_at):
            roles = [
                {
                    "role_id": role.id,
                    "role": role.name,
                    "filled": role.confirmed_count,
                    "capacity": role.capacity,
                    "signups": [
                        {
                            "signup_id": s.id,
                            "volunteer": names.get(s.volunteer_profile_id, "Unknown"),
                            "status": s.status.value,
                        }
                        for s in role.signups
                        if s.status != SignupStatus.cancelled
                    ],
                }
                for role in shift.roles
            ]
            shifts.append({
                "shift_id": shift.id,
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "location": shift.location,
                "is_open": shift.is_open,
                "roles": roles,
            })
        board.append({
            "event_id": event.id,
            "title": event.title,
            "kind": event.kind,
            "shifts": shifts,
        })
    return board


def public_opportunities(db: Session, *, org_id: int) -> list[dict]:
    """Public, active events that still have upcoming shifts — the visitor-facing opportunity
    list. Only ``is_public`` events are exposed; each opportunity summarises its next upcoming
    shift and how many roles still have open seats. No volunteer PII is included.
    """
    now = utcnow()
    events = db.scalars(
        select(Event)
        .where(Event.org_id == org_id, Event.status == "active", Event.is_public.is_(True))
        .order_by(Event.id)
    ).all()
    out: list[dict] = []
    for event in events:
        upcoming = sorted(
            (s for s in event.shifts if s.is_open and s.ends_at > now),
            key=lambda s: s.starts_at,
        )
        if not upcoming:
            continue
        shifts = [
            {
                "shift_id": s.id,
                "starts_at": s.starts_at.isoformat(),
                "ends_at": s.ends_at.isoformat(),
                "location": s.location,
                "open_roles": sum(1 for r in s.roles if r.seats_available),
            }
            for s in upcoming
        ]
        out.append({
            "event_id": event.id,
            "title": event.title,
            "description": event.description,
            "kind": event.kind,
            "next_shift_at": upcoming[0].starts_at.isoformat(),
            "location": upcoming[0].location,
            "shift_count": len(shifts),
            "shifts": shifts,
        })
    return out
