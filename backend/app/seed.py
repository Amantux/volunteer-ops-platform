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
        "report.view_staffing", "shift.view_eligible", "shift.signup",
        "comms.manage", "comms.approve", "audit.view",
        "site.edit", "site.develop", "site.publish",
        "social.draft", "social.manage", "social.approve", "social.publish",
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
    "comms_manager": [
        "comms.manage",
    ],
    "site_editor": [
        "site.edit", "site.publish",
    ],
    "social_manager": [
        "social.draft", "social.manage", "social.approve", "social.publish",
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
    "newsletter": (
        "News from Riverside Volunteers",
        "Hi {{name}},\n\nHere's the latest from the team. Thank you for volunteering!",
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
    _seed_demo_opportunity(db, org.id)
    _seed_pages(db, org.id)
    _seed_social(db, org.id)
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
        assert role is not None  # seeded just above
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
    from datetime import timedelta

    from app.core.db import utcnow

    start = (utcnow() + timedelta(days=9)).replace(hour=10, minute=0, second=0, microsecond=0)
    db.add(TrainingSession(org_id=org_id, course_id=course.id, capacity=20,
                           location="Community Center, Room A",
                           starts_at=start, ends_at=start + timedelta(hours=2)))
    db.flush()


def _seed_demo_opportunity(db: Session, org_id: int) -> None:
    """A public volunteer opportunity with a couple of upcoming shifts, so the public
    calendar and opportunities page show real data out of the box."""
    from datetime import timedelta

    from app.core.db import utcnow
    from app.modules.scheduling import service as scheduling
    from app.modules.scheduling.models import Event

    if db.scalar(select(func.count()).select_from(Event).where(Event.org_id == org_id)):
        return
    event = scheduling.create_event(
        db, org_id=org_id, title="Community Garden Workday", kind="event", is_public=True,
        description="Help plant, weed, and tend the neighbourhood garden. No experience "
                    "needed — tools, gloves, and guidance provided. Great for individuals, "
                    "families, and groups.")
    for week in (1, 2):
        start = (utcnow() + timedelta(days=7 * week)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        shift = scheduling.create_shift(db, org_id=org_id, event_id=event.id, starts_at=start,
                                        ends_at=start + timedelta(hours=3),
                                        location="Riverside Community Garden")
        scheduling.add_role(db, org_id=org_id, shift_id=shift.id, name="Garden Helper",
                            capacity=8)
    db.flush()


def _seed_pages(db: Session, org_id: int) -> None:
    """Seed the starter public pages as editable, published Page rows so the website builder
    manages a real (non-lorem) site out of the box."""
    from app.core.db import utcnow
    from app.modules.content.models import Page, PageStatus

    if db.scalar(select(func.count()).select_from(Page).where(Page.org_id == org_id)):
        return

    def para(text: str) -> dict:
        return {"type": "paragraph", "html": f"<p>{text}</p>"}

    # Demo pages the builder owns, at slugs that don't collide with the app's built-in routes.
    # (The built-in about/faq/contact pages remain hardcoded; moving them into the builder is a
    # follow-up — see docs. These show the builder end-to-end and populate the public nav.)
    pages = [
        ("our-story", "Our story", 1, [
            {"type": "heading", "level": 1, "text": "Our story"},
            para("Riverside Volunteers began with a handful of neighbours and a simple idea: "
                 "that a community is strongest when everyone has a way to help. Today we train "
                 "and mobilise hundreds of local volunteers across food security, emergency "
                 "response, and everyday care."),
            para("No experience is required to start — just a willingness to help. We provide "
                 "the training, the tools, and a welcoming team."),
            {"type": "button", "label": "Browse opportunities", "href": "/opportunities"},
        ]),
        ("get-involved", "Get involved", 2, [
            {"type": "heading", "level": 1, "text": "Get involved"},
            para("There's a place for everyone here. Start with a free orientation, then pick "
                 "the opportunities that fit your schedule and interests."),
            {"type": "button", "label": "See upcoming trainings", "href": "/trainings"},
        ]),
    ]
    now = utcnow()
    for slug, title, order, blocks in pages:
        db.add(Page(org_id=org_id, slug=slug, title=title, status=PageStatus.published,
                    blocks=blocks, published_blocks=blocks, published_css="", published_at=now,
                    show_in_nav=True, nav_order=order))
    db.flush()


def _seed_social(db: Session, org_id: int) -> None:
    """Seed one manual channel so the social composer works out of the box (no external creds)."""
    from app.modules.social.models import Platform, SocialChannel

    if db.scalar(select(func.count()).select_from(SocialChannel).where(
            SocialChannel.org_id == org_id)):
        return
    db.add(SocialChannel(org_id=org_id, platform=Platform.manual, handle="@riverside",
                         display_name="Riverside (manual)", char_limit=280))
    db.flush()
