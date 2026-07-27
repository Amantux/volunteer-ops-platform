"""People services: guest→volunteer activation (identity reconciliation) + qualifications."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.core.security import hash_password
from app.modules.identity.models import Person, User
from app.modules.training.models import Course, RegistrationStatus, TrainingRegistration

from .models import ProgramEnrollment, VolunteerProfile, VolunteerQualification


class ActivationError(Exception):
    pass


def activate_volunteer(db: Session, *, org_id: int, person_id: int,
                       password: str | None = None) -> User:
    """Turn a known Person into an authenticable volunteer WITHOUT creating a duplicate.

    Identity reconciliation: activation attaches a User + VolunteerProfile to the
    *existing* Person (matched earlier by verified email), so a guest who registered for
    training becomes the same volunteer record.
    """
    person = db.get(Person, person_id)
    if person is None or person.org_id != org_id:
        raise ActivationError("person not found")
    if not person.email_verified:
        raise ActivationError("email must be verified before activation")

    if person.user is not None:
        return person.user  # idempotent

    user = User(org_id=org_id, person_id=person.id,
                password_hash=hash_password(password) if password else "")
    db.add(user)
    profile = db.scalar(
        select(VolunteerProfile).where(VolunteerProfile.person_id == person.id)
    )
    if profile is None:
        profile = VolunteerProfile(org_id=org_id, person_id=person.id)
        db.add(profile)
    db.flush()

    # Grant qualifications for any already-completed courses.
    completed = db.scalars(
        select(TrainingRegistration).where(
            TrainingRegistration.org_id == org_id,
            TrainingRegistration.person_id == person.id,
            TrainingRegistration.status == RegistrationStatus.completed,
        )
    )
    for reg in completed:
        grant_course_qualification(db, org_id=org_id, person_id=person.id,
                                   course_id=reg.session.course_id)

    audit.emit(db, org_id=org_id, action="volunteer.activate", actor_type="user",
               actor_id=user.id, target_type="person", target_id=person.id)
    db.flush()
    return user


def profile_for_user(db: Session, *, org_id: int, user_id: int) -> VolunteerProfile | None:
    """Resolve the volunteer profile for an authenticated user (user → person → profile)."""
    user = db.get(User, user_id)
    if user is None or user.org_id != org_id:
        return None
    return db.scalar(select(VolunteerProfile).where(
        VolunteerProfile.org_id == org_id, VolunteerProfile.person_id == user.person_id))


def grant_course_qualification(db: Session, *, org_id: int, person_id: int, course_id: int) -> None:
    """Grant the course's qualification to the person's volunteer profile, if any and if not
    already held. No-op when the person isn't a volunteer yet (granted at activation)."""
    course = db.get(Course, course_id)
    if course is None or course.org_id != org_id or course.grants_qualification_type_id is None:
        return
    profile = db.scalar(select(VolunteerProfile).where(
        VolunteerProfile.org_id == org_id, VolunteerProfile.person_id == person_id))
    if profile is None:
        return
    already = db.scalar(select(VolunteerQualification).where(
        VolunteerQualification.profile_id == profile.id,
        VolunteerQualification.qualification_type_id == course.grants_qualification_type_id,
    ))
    if already is not None:
        return
    from app.modules.people.models import QualificationType

    qtype = db.get(QualificationType, course.grants_qualification_type_id)
    expires = None
    if qtype and qtype.validity_days:
        expires = utcnow() + timedelta(days=qtype.validity_days)
    db.add(VolunteerQualification(
        org_id=org_id, profile_id=profile.id,
        qualification_type_id=course.grants_qualification_type_id,
        granted_at=utcnow(), expires_at=expires, source="training",
    ))
    db.flush()


class PeopleError(Exception):
    pass


def list_qualification_types(db: Session, *, org_id: int) -> list:
    from app.modules.people.models import QualificationType
    return list(db.scalars(select(QualificationType).where(QualificationType.org_id == org_id)
                           .order_by(QualificationType.label)))


def create_qualification_type(db: Session, *, org_id: int, key: str, label: str,
                              validity_days: int | None = None):
    from app.modules.people.models import QualificationType
    if db.scalar(select(QualificationType).where(
            QualificationType.org_id == org_id, QualificationType.key == key)) is not None:
        raise PeopleError("a qualification type with that key already exists")
    qt = QualificationType(org_id=org_id, key=key, label=label or key, validity_days=validity_days)
    db.add(qt)
    db.flush()
    return qt


def grant_qualification(db: Session, *, org_id: int, volunteer_email: str,
                        qualification_type_id: int, source: str = "manual") -> VolunteerQualification:
    """Grant a qualification to a volunteer (by email). Idempotent per (profile, type)."""
    from app.modules.identity.models import Person
    from app.modules.people.models import QualificationType

    qtype = db.get(QualificationType, qualification_type_id)
    if qtype is None or qtype.org_id != org_id:
        raise PeopleError("qualification type not found")
    person = db.scalar(select(Person).where(Person.org_id == org_id,
                                            Person.email == volunteer_email.lower()))
    profile = None if person is None else db.scalar(select(VolunteerProfile).where(
        VolunteerProfile.org_id == org_id, VolunteerProfile.person_id == person.id))
    if profile is None:
        raise PeopleError("no volunteer with that email")
    existing = db.scalar(select(VolunteerQualification).where(
        VolunteerQualification.profile_id == profile.id,
        VolunteerQualification.qualification_type_id == qualification_type_id))
    if existing is not None:
        existing.granted_at = utcnow()
        existing.expires_at = (utcnow() + timedelta(days=qtype.validity_days)
                               if qtype.validity_days else None)
        db.flush()
        return existing
    vq = VolunteerQualification(
        org_id=org_id, profile_id=profile.id, qualification_type_id=qualification_type_id,
        granted_at=utcnow(),
        expires_at=(utcnow() + timedelta(days=qtype.validity_days) if qtype.validity_days else None),
        source=source)
    db.add(vq)
    db.flush()
    return vq


# --- Program enrollment (long-term assignment) ------------------------------------------ #

ENROLLMENT_STATUSES = ("active", "paused", "completed", "withdrawn")
_TERMINAL_STATUSES = ("completed", "withdrawn")


def _profile_by_email(db: Session, *, org_id: int, volunteer_email: str) -> VolunteerProfile:
    person = db.scalar(select(Person).where(
        Person.org_id == org_id, Person.email == volunteer_email.lower()))
    profile = None if person is None else db.scalar(select(VolunteerProfile).where(
        VolunteerProfile.org_id == org_id, VolunteerProfile.person_id == person.id))
    if profile is None:
        raise PeopleError("no volunteer with that email")
    return profile


def enroll(db: Session, *, org_id: int, volunteer_email: str, program_id: int, role: str,
           notes: str = "", actor_id: str | int = "") -> ProgramEnrollment:
    """Enrol a volunteer in a program under a role. Idempotent: returns the existing
    non-terminal enrollment for (profile, program, role) instead of creating a duplicate."""
    from app.modules.org.models import Program

    role = role.strip()
    if not role:
        raise PeopleError("role is required")
    program = db.get(Program, program_id)
    if program is None or program.org_id != org_id:
        raise PeopleError("program not found")
    profile = _profile_by_email(db, org_id=org_id, volunteer_email=volunteer_email)

    def _active(db: Session) -> ProgramEnrollment | None:
        return db.scalar(select(ProgramEnrollment).where(
            ProgramEnrollment.org_id == org_id,
            ProgramEnrollment.profile_id == profile.id,
            ProgramEnrollment.program_id == program_id,
            ProgramEnrollment.role == role,
            ProgramEnrollment.status.not_in(_TERMINAL_STATUSES),
        ))

    existing = _active(db)
    if existing is not None:
        return existing  # idempotent — already actively enrolled in this role

    enr = ProgramEnrollment(org_id=org_id, profile_id=profile.id, program_id=program_id,
                            role=role, status="active", started_at=utcnow(), notes=notes)
    db.add(enr)
    try:
        # The partial unique index (one non-terminal per profile/program/role) makes this
        # race-safe: a concurrent enroll that won the insert raises here on flush.
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        winner = _active(db)
        if winner is not None:
            return winner  # the concurrent request created it — return theirs, idempotently
        raise
    audit.emit(db, org_id=org_id, action="program.enroll", actor_type="user", actor_id=actor_id,
               target_type="program_enrollment", target_id=enr.id,
               meta={"program_id": program_id, "role": role})
    return enr


def set_enrollment_status(db: Session, *, org_id: int, enrollment_id: int, status: str,
                          actor_id: str | int = "") -> ProgramEnrollment:

    if status not in ENROLLMENT_STATUSES:
        raise PeopleError(f"invalid status: {status}")
    enr = db.get(ProgramEnrollment, enrollment_id)
    if enr is None or enr.org_id != org_id:
        raise PeopleError("enrollment not found")
    if enr.status in _TERMINAL_STATUSES:
        # completed/withdrawn are final — reviving one would resurrect a closed commitment and
        # collide with the active-enrollment uniqueness. Start a new enrollment instead.
        raise PeopleError(f"enrollment is already {enr.status}")
    previous = enr.status
    enr.status = status
    enr.ended_at = utcnow() if status in _TERMINAL_STATUSES else None
    db.flush()
    audit.emit(db, org_id=org_id, action="program.enrollment_status", actor_type="user",
               actor_id=actor_id, target_type="program_enrollment", target_id=enr.id,
               meta={"from": previous, "to": status})
    return enr


def list_enrollments(db: Session, *, org_id: int, program_id: int | None = None,
                     role: str | None = None, status: str | None = None,
                     allowed_program_ids: set[int] | None = None) -> list[dict]:
    """List enrollments with the volunteer's display name/email for the coordinator view.

    ``allowed_program_ids`` restricts results to a whitelist of programs (the caller's fine-grained
    scope); ``None`` means no restriction (org-wide). An empty set returns nothing."""
    q = select(ProgramEnrollment, Person).join(
        VolunteerProfile, ProgramEnrollment.profile_id == VolunteerProfile.id
    ).join(Person, VolunteerProfile.person_id == Person.id).where(
        ProgramEnrollment.org_id == org_id)
    if allowed_program_ids is not None:
        q = q.where(ProgramEnrollment.program_id.in_(allowed_program_ids))
    if program_id is not None:
        q = q.where(ProgramEnrollment.program_id == program_id)
    if role is not None:
        q = q.where(ProgramEnrollment.role == role)
    if status is not None:
        q = q.where(ProgramEnrollment.status == status)
    q = q.order_by(ProgramEnrollment.started_at.desc())
    return [{
        "id": enr.id, "program_id": enr.program_id, "role": enr.role, "status": enr.status,
        "started_at": enr.started_at.isoformat(),
        "ended_at": enr.ended_at.isoformat() if enr.ended_at else None,
        "notes": enr.notes, "volunteer_name": person.name, "volunteer_email": person.email,
    } for enr, person in db.execute(q).all()]


# --- Background check (sensitive; internal-only) ----------------------------------------- #

BACKGROUND_CHECK_STATUSES = ("none", "requested", "cleared", "expired")


def has_valid_background_check(profile: VolunteerProfile) -> bool:
    """True when the profile holds a cleared, non-expired background check."""
    if profile.background_check_status != "cleared":
        return False
    exp = profile.background_check_expires_at
    return exp is None or exp > utcnow()


def set_background_check(db: Session, *, org_id: int, volunteer_email: str, status: str,
                        expires_at: datetime | None = None,
                        actor_id: str | int = "") -> VolunteerProfile:
    """Set a volunteer's background-check status. Audited; only the status (not any PII) is
    recorded in the audit meta."""
    if status not in BACKGROUND_CHECK_STATUSES:
        raise PeopleError(f"invalid status: {status}")
    profile = _profile_by_email(db, org_id=org_id, volunteer_email=volunteer_email)
    profile.background_check_status = status
    profile.background_check_expires_at = expires_at if status == "cleared" else None
    db.flush()
    audit.emit(db, org_id=org_id, action="volunteer.background_check", actor_type="user",
               actor_id=actor_id, target_type="volunteer_profile", target_id=profile.id,
               meta={"status": status})
    return profile
