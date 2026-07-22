"""First-run bootstrap: organization, roles/permissions, admin, email templates, demo data."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.communications.models import EmailTemplate
from app.modules.identity.models import (
    Person,
    Role,
    RolePermission,
    User,
    UserRoleAssignment,
)
from app.modules.org.models import Organization
from app.modules.people.models import QualificationType
from app.modules.training.models import Course, TrainingSession

# role_key -> permissions granted
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "org_admin": [
        "training.manage_course", "training.manage_session", "training.manage_any_session",
        "training.record_attendance", "training.record_completion", "training.view_roster",
        "training.approve_promotion", "training.register_guest", "report.view_training",
        "shift.manage", "shift.view_roster", "shift.record_attendance", "hours.approve",
        "report.view_staffing", "shift.view_eligible", "shift.signup", "audit.view",
    ],
    "trainer": [
        "training.manage_session", "training.record_attendance", "training.record_completion",
        "training.view_roster",
    ],
    "coordinator": [
        "shift.manage", "shift.view_roster", "shift.record_attendance", "hours.approve",
        "report.view_staffing",
    ],
    "volunteer": [
        "shift.view_eligible", "shift.signup",
    ],
}

TEMPLATES: dict[str, tuple[str, str]] = {
    "training_verify": (
        "Confirm your email for {{course}}",
        "Hi {{name}},\n\nPlease confirm your email to finish registering for {{course}}:\n"
        "{{verify_url}}\n\nThanks for volunteering!",
    ),
    "training_confirmation": (
        "You're registered for {{course}}",
        "Hi {{name}},\n\nYou're confirmed for {{course}}. We'll send a reminder before it starts.\n"
        "Thank you for volunteering!",
    ),
    "training_waitlisted": (
        "You're on the waitlist for {{course}}",
        "Hi {{name}},\n\n{{course}} is currently full, so you're on the waitlist. We'll email you "
        "if a spot opens up.",
    ),
    "training_promoted": (
        "A spot opened up in {{course}}",
        "Hi {{name}},\n\nGood news — a spot opened in {{course}} and you're now confirmed. "
        "See you there!",
    ),
    "login_link": (
        "Your sign-in link",
        "Hi {{name}},\n\nUse this link to sign in:\n{{login_url}}\n\nIt expires soon and can be "
        "used once. If you didn't request this, you can ignore it.",
    ),
}


def seed_bootstrap(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == settings.bootstrap_org_slug))
    if org is None:
        org = Organization(name=settings.bootstrap_org_name, slug=settings.bootstrap_org_slug)
        db.add(org)
        db.flush()

    _seed_roles(db, org.id)
    _seed_admin(db, org.id)
    _seed_templates(db, org.id)
    _seed_demo_training(db, org.id)
    db.commit()
    return org


def _seed_roles(db: Session, org_id: int) -> None:
    for role_key, perms in ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.org_id == org_id, Role.key == role_key))
        if role is None:
            role = Role(org_id=org_id, key=role_key, label=role_key.replace("_", " ").title())
            db.add(role)
            db.flush()
        have = {rp.permission for rp in role.permissions}
        for perm in perms:
            if perm not in have:
                db.add(RolePermission(role_id=role.id, permission=perm))
    db.flush()


def _seed_admin(db: Session, org_id: int) -> None:
    email = settings.bootstrap_admin_email.lower()
    person = db.scalar(select(Person).where(Person.org_id == org_id, Person.email == email))
    if person is None:
        person = Person(org_id=org_id, name="Org Admin", email=email, email_verified=True)
        db.add(person)
        db.flush()
    if person.user is None:
        user = User(org_id=org_id, person_id=person.id)
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.org_id == org_id, Role.key == "org_admin"))
        db.add(UserRoleAssignment(org_id=org_id, user_id=user.id, role_id=role.id))
    db.flush()


def _seed_templates(db: Session, org_id: int) -> None:
    for key, (subject, body) in TEMPLATES.items():
        existing = db.scalar(
            select(EmailTemplate).where(EmailTemplate.org_id == org_id, EmailTemplate.key == key)
        )
        if existing is None:
            db.add(EmailTemplate(org_id=org_id, key=key, subject=subject, body_text=body))
    db.flush()


def _seed_demo_training(db: Session, org_id: int) -> None:
    if db.scalar(select(func.count()).select_from(Course).where(Course.org_id == org_id)):
        return
    qtype = QualificationType(org_id=org_id, key="orientation", label="Orientation Complete",
                              validity_days=365)
    db.add(qtype)
    db.flush()
    course = Course(org_id=org_id, title="Volunteer Orientation",
                    description="Everything you need to get started as a volunteer.",
                    is_public=True, grants_qualification_type_id=qtype.id)
    db.add(course)
    db.flush()
    db.add(TrainingSession(org_id=org_id, course_id=course.id, capacity=20,
                           location="Community Center, Room A"))
    db.flush()
