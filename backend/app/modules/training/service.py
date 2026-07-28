"""Training domain services — the core of the first vertical slice.

Capacity and waitlist ordering are deterministic code (not agent logic). Emails go
through the transactional outbox. Sensitive actions emit audit events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import PermissionDenied, Principal, has_permission
from app.core.config import settings
from app.core.db import utcnow
from app.core.security import generate_token, hash_token
from app.modules.agents.models import AgentProposal, ProposalStatus, RiskLevel
from app.modules.communications.service import queue_email
from app.modules.identity.models import Person, TokenPurpose, VerificationToken
from app.modules.org.models import OrganizationSetting

from .models import Course, RegistrationStatus, TrainingRegistration, TrainingSession


class TrainingError(Exception):
    pass


def _occupied_seats(db: Session, session_id: int) -> int:
    """Count occupying registrations by query (the ORM relationship can be stale mid-tx)."""
    return db.scalar(
        select(func.count())
        .select_from(TrainingRegistration)
        .where(
            TrainingRegistration.session_id == session_id,
            TrainingRegistration.status.in_(TrainingSession.OCCUPYING),
        )
    ) or 0


def _seats_available(db: Session, session: TrainingSession) -> bool:
    return session.capacity is None or _occupied_seats(db, session.id) < session.capacity


def _next_waitlist_position(db: Session, session_id: int) -> int:
    highest = db.scalar(
        select(func.max(TrainingRegistration.waitlist_position)).where(
            TrainingRegistration.session_id == session_id
        )
    )
    return (highest or 0) + 1


@dataclass
class RegistrationResult:
    registration: TrainingRegistration
    verification_token: str  # plaintext, emailed to the person (never stored)
    waitlisted: bool


# --- Setup (admin / trainer) ------------------------------------------------ #

def create_course(db: Session, *, org_id: int, title: str, description: str = "",
                  is_public: bool = True) -> Course:
    course = Course(org_id=org_id, title=title, description=description, is_public=is_public)
    db.add(course)
    db.flush()
    return course


def create_session(db: Session, *, org_id: int, course_id: int, capacity: int | None = None,
                   location: str = "", trainer_user_id: int | None = None,
                   starts_at=None, ends_at=None) -> TrainingSession:
    session = TrainingSession(
        org_id=org_id, course_id=course_id, capacity=capacity, location=location,
        trainer_user_id=trainer_user_id, starts_at=starts_at, ends_at=ends_at,
    )
    db.add(session)
    db.flush()
    return session


# --- Public registration ---------------------------------------------------- #

def _get_or_create_person(db: Session, *, org_id: int, name: str, email: str, phone: str) -> Person:
    email = email.strip().lower()
    person = db.scalar(select(Person).where(Person.org_id == org_id, Person.email == email))
    if person is None:
        person = Person(org_id=org_id, name=name.strip(), email=email, phone=phone.strip())
        db.add(person)
        db.flush()
    elif name.strip():
        person.name = name.strip()
    return person


def _issue_token(db: Session, *, org_id: int, person_id: int, purpose: TokenPurpose,
                 ttl_min: int, registration_id: int | None = None) -> str:
    token = generate_token()
    db.add(VerificationToken(
        org_id=org_id, person_id=person_id, registration_id=registration_id, purpose=purpose,
        token_hash=hash_token(token), expires_at=utcnow() + timedelta(minutes=ttl_min),
    ))
    db.flush()
    return token


def register_guest(db: Session, *, org_id: int, session_id: int, name: str, email: str,
                   phone: str = "", source: str = "public") -> RegistrationResult:
    """Register a guest (no account). Allocates a seat or waitlists deterministically,
    issues a verification token, and enqueues a verification email via the outbox."""
    session = db.get(TrainingSession, session_id)
    if session is None or session.org_id != org_id:
        raise TrainingError("session not found")
    if not session.is_open:
        raise TrainingError("registration is closed")
    if not session.course.is_public and source == "public":
        raise TrainingError("session is not open to the public")

    person = _get_or_create_person(db, org_id=org_id, name=name, email=email, phone=phone)

    existing = db.scalar(
        select(TrainingRegistration).where(
            TrainingRegistration.session_id == session_id,
            TrainingRegistration.person_id == person.id,
        )
    )
    if existing is not None and existing.status != RegistrationStatus.cancelled:
        raise TrainingError("already registered for this session")

    waitlisted = not _seats_available(db, session)
    if existing is not None:  # re-registering after a cancel
        registration = existing
        registration.status = (
            RegistrationStatus.waitlisted if waitlisted else RegistrationStatus.registered
        )
    else:
        registration = TrainingRegistration(
            org_id=org_id, session_id=session_id, person_id=person.id, source=source,
            status=RegistrationStatus.waitlisted if waitlisted else RegistrationStatus.registered,
        )
        db.add(registration)
    registration.waitlist_position = (
        _next_waitlist_position(db, session_id) if waitlisted else None
    )
    db.flush()

    token = _issue_token(
        db, org_id=org_id, person_id=person.id, purpose=TokenPurpose.email_verification,
        ttl_min=settings.verification_token_ttl_min, registration_id=registration.id,
    )
    queue_email(
        db, org_id=org_id, idempotency_key=f"verify:reg:{registration.id}",
        to_email=person.email, template_key="training_verify",
        context={
            "name": person.name, "course": session.course.title,
            "verify_url": f"{settings.public_base_url}/verify?token={token}",
        },
    )
    return RegistrationResult(registration=registration, verification_token=token,
                              waitlisted=waitlisted)


def verify_email(db: Session, *, token: str) -> TrainingRegistration | None:
    """Consume a single-use verification token, verify the person's email, and confirm the
    *specific* registration the token was issued for (not merely the newest)."""
    row = db.scalar(select(VerificationToken).where(
        VerificationToken.token_hash == hash_token(token),
        VerificationToken.purpose == TokenPurpose.email_verification,
    ))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise TrainingError("invalid or expired token")
    row.used_at = utcnow()
    person = db.get(Person, row.person_id)
    assert person is not None  # token FK guarantees the person exists
    person.email_verified = True

    registration = db.get(TrainingRegistration, row.registration_id) if row.registration_id else None
    if registration is None:
        db.flush()
        return None

    if registration.status == RegistrationStatus.registered:
        registration.status = RegistrationStatus.confirmed
        template, key = "confirmed", "training_confirmation"
    else:
        template, key = "waitlisted", "training_waitlisted"
    db.flush()
    queue_email(
        db, org_id=registration.org_id, idempotency_key=f"{template}:reg:{registration.id}",
        to_email=person.email, template_key=key,
        context={"name": person.name, "course": registration.session.course.title},
    )
    return registration


# --- Cancellation + waitlist promotion -------------------------------------- #

def _auto_promote_enabled(db: Session, org_id: int) -> bool:
    setting = db.scalar(select(OrganizationSetting).where(
        OrganizationSetting.org_id == org_id, OrganizationSetting.key == "training.auto_promote",
    ))
    return bool(setting and setting.value.get("enabled"))


def cancel_registration(db: Session, *, org_id: int, registration_id: int,
                        actor_type: str = "user", actor_id: str = "") -> AgentProposal | None:
    reg = db.get(TrainingRegistration, registration_id)
    if reg is None or reg.org_id != org_id:
        raise TrainingError("registration not found")
    reg.status = RegistrationStatus.cancelled
    reg.waitlist_position = None
    db.flush()
    audit.emit(db, org_id=org_id, action="training.cancel", actor_type=actor_type,
               actor_id=actor_id, target_type="registration", target_id=reg.id)
    return propose_waitlist_promotion(db, org_id=org_id, session_id=reg.session_id,
                                      requested_by_user_id=None)


def _first_waitlisted(db: Session, session_id: int) -> TrainingRegistration | None:
    return db.scalar(
        select(TrainingRegistration)
        .where(TrainingRegistration.session_id == session_id,
               TrainingRegistration.status == RegistrationStatus.waitlisted)
        .order_by(TrainingRegistration.waitlist_position)
    )


def propose_waitlist_promotion(db: Session, *, org_id: int, session_id: int,
                               requested_by_user_id: int | None,
                               allow_auto_execute: bool = True) -> AgentProposal | None:
    """Create a promotion proposal. If the org enabled the narrow auto-promote policy and a seat is
    genuinely free for the #1 waitlisted person, execute it; else require approval.

    `allow_auto_execute=False` forces an approval-only `proposed` record regardless of org policy —
    used by the chat assistant, which must never autonomously change records or send email."""
    session = db.get(TrainingSession, session_id)
    if session is None or session.org_id != org_id or not _seats_available(db, session):
        return None
    candidate = _first_waitlisted(db, session_id)
    if candidate is None:
        return None

    proposal = AgentProposal(
        org_id=org_id, agent="scheduling", action="promote_waitlist",
        risk_level=RiskLevel.r3_approval,
        goal=f"Fill the seat freed in session {session_id}",
        inputs={"session_id": session_id, "registration_id": candidate.id},
        rationale=(f"{candidate.person_id} is position #{candidate.waitlist_position} on the "
                   f"waitlist and a seat is available."),
        confidence=1.0, requested_by_user_id=requested_by_user_id,
    )
    db.add(proposal)
    db.flush()

    if allow_auto_execute and _auto_promote_enabled(db, org_id):
        _execute_promotion(db, proposal, candidate, actor_type="agent", actor_id="scheduling")
        proposal.status = ProposalStatus.auto_executed
        db.flush()
    return proposal


def approve_promotion(db: Session, *, org_id: int, proposal_id: int, decided_by_user_id: int):
    proposal = db.get(AgentProposal, proposal_id)
    if proposal is None or proposal.org_id != org_id:
        raise TrainingError("proposal not found")
    if proposal.status != ProposalStatus.proposed:
        raise TrainingError("proposal is not pending")
    candidate = db.get(TrainingRegistration, proposal.inputs["registration_id"])
    session = db.get(TrainingSession, candidate.session_id) if candidate else None
    # Re-check eligibility AND seat availability at approval time: the freed seat may have
    # been taken by a new registration between propose and approve.
    if (candidate is None or candidate.status != RegistrationStatus.waitlisted
            or session is None or not _seats_available(db, session)):
        proposal.status = ProposalStatus.rejected
        db.flush()
        raise TrainingError("no seat available or candidate no longer eligible")
    proposal.status = ProposalStatus.approved
    proposal.decided_by_user_id = decided_by_user_id
    proposal.decided_at = utcnow()
    _execute_promotion(db, proposal, candidate, actor_type="user", actor_id=decided_by_user_id)
    proposal.status = ProposalStatus.executed
    db.flush()
    return proposal


def _execute_promotion(db: Session, proposal: AgentProposal, candidate: TrainingRegistration,
                       *, actor_type: str, actor_id) -> None:
    # Defensive final seat check (auto-promote path calls this directly).
    session = db.get(TrainingSession, candidate.session_id)
    assert session is not None
    if not _seats_available(db, session):
        raise TrainingError("no seat available")
    candidate.status = RegistrationStatus.confirmed
    candidate.waitlist_position = None
    person = db.get(Person, candidate.person_id)
    assert person is not None
    proposal.result = {"promoted_registration_id": candidate.id}
    audit.emit(db, org_id=candidate.org_id, action="training.waitlist_promote",
               actor_type=actor_type, actor_id=actor_id, target_type="registration",
               target_id=candidate.id, meta={"proposal_id": proposal.id})
    queue_email(
        db, org_id=candidate.org_id, idempotency_key=f"promoted:reg:{candidate.id}",
        to_email=person.email, template_key="training_promoted",
        context={"name": person.name, "course": candidate.session.course.title},
    )


# --- Attendance / completion ------------------------------------------------ #

def _load_reg_for_actor(db: Session, *, org_id: int, registration_id: int,
                        principal: Principal) -> TrainingRegistration:
    """Load a registration and enforce object-level ownership: the actor must run the
    session (trainer_user_id) OR hold the org-wide override permission."""
    reg = db.get(TrainingRegistration, registration_id)
    if reg is None or reg.org_id != org_id:
        raise TrainingError("registration not found")
    session = db.get(TrainingSession, reg.session_id)
    assert session is not None
    owns = session.trainer_user_id in (None, principal.user_id)
    if not owns and not has_permission(db, principal, "training.manage_any_session"):
        raise PermissionDenied("training.manage_any_session")
    return reg


def check_in(db: Session, *, org_id: int, registration_id: int,
             principal: Principal) -> TrainingRegistration:
    reg = _load_reg_for_actor(db, org_id=org_id, registration_id=registration_id,
                              principal=principal)
    reg.status = RegistrationStatus.attended
    reg.checked_in_at = utcnow()
    db.flush()
    audit.emit(db, org_id=org_id, action="training.checkin", actor_id=principal.user_id,
               target_type="registration", target_id=reg.id)
    return reg


def record_completion(db: Session, *, org_id: int, registration_id: int, principal: Principal):
    from app.modules.people.service import grant_course_qualification

    reg = _load_reg_for_actor(db, org_id=org_id, registration_id=registration_id,
                              principal=principal)
    reg.status = RegistrationStatus.completed
    reg.completed_at = utcnow()
    db.flush()
    audit.emit(db, org_id=org_id, action="training.completion", actor_id=principal.user_id,
               target_type="registration", target_id=reg.id)
    # Grant the course's qualification if the person is already an active volunteer;
    # otherwise it is granted when they activate their account.
    grant_course_qualification(db, org_id=org_id, person_id=reg.person_id,
                               course_id=reg.session.course_id)
    return reg


# --- Maintenance: reclaim stale unverified holds ---------------------------- #

def expire_unconfirmed_holds(db: Session, *, ttl_min: int | None = None) -> int:
    """Reclaim seats held by never-verified 'registered' rows older than the TTL.

    Expiring frees the seat (status → expired), then proposes waitlist promotion for each
    affected session (respecting the org's approval/auto-promote policy). Idempotent and
    safe to run repeatedly on a schedule. Returns the number expired.
    """
    cutoff = utcnow() - timedelta(minutes=ttl_min or settings.unconfirmed_hold_ttl_min)
    stale = db.scalars(
        select(TrainingRegistration).where(
            TrainingRegistration.status == RegistrationStatus.registered,
            TrainingRegistration.created_at < cutoff,
        )
    ).all()
    affected_sessions: set[int] = set()
    for reg in stale:
        reg.status = RegistrationStatus.expired
        affected_sessions.add(reg.session_id)
        audit.emit(db, org_id=reg.org_id, action="training.hold_expired", actor_type="service",
                   actor_id="reaper", target_type="registration", target_id=reg.id)
    db.flush()
    for session_id in affected_sessions:
        session = db.get(TrainingSession, session_id)
        assert session is not None
        propose_waitlist_promotion(db, org_id=session.org_id, session_id=session_id,
                                   requested_by_user_id=None)
    db.commit()
    return len(stale)


# --- Reporting -------------------------------------------------------------- #

def training_funnel(db: Session, *, org_id: int, session_id: int | None = None) -> dict[str, int]:
    stmt = select(TrainingRegistration).where(TrainingRegistration.org_id == org_id)
    if session_id is not None:
        stmt = stmt.where(TrainingRegistration.session_id == session_id)
    regs = list(db.scalars(stmt))
    counts = {s.value: 0 for s in RegistrationStatus}
    for r in regs:
        counts[r.status.value] += 1
    counts["total"] = len(regs)
    return counts
