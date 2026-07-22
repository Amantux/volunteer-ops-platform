"""People services: guest→volunteer activation (identity reconciliation) + qualifications."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.core.security import hash_password
from app.modules.identity.models import Person, User
from app.modules.training.models import Course, RegistrationStatus, TrainingRegistration

from .models import VolunteerProfile, VolunteerQualification


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
