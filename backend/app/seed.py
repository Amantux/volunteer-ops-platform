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
        "enrollment.view", "enrollment.manage", "volunteer.manage_background_check",
        "comms.manage", "comms.approve", "audit.view",
        "site.edit", "site.develop", "site.publish",
        "social.draft", "social.manage", "social.approve", "social.publish",
        "forms.admin", "forms.review", "workflows.admin", "incident.triage", "incident.close",
        "donation.view", "donation.manage", "finance.export",
        "assistant.configure",
    ],
    "trainer": [
        "training.manage_session", "training.record_attendance", "training.record_completion",
        "training.view_roster",
    ],
    "coordinator": [
        "shift.manage", "shift.view_roster", "shift.record_attendance", "hours.approve",
        "report.view_staffing",
        "enrollment.view", "enrollment.manage", "volunteer.manage_background_check",
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
    "operations_coordinator": [
        "forms.review", "incident.triage", "incident.close",
    ],
    "finance_manager": [
        "donation.view", "donation.manage", "finance.export",
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
        "News from Golden Opportunities for Independence",
        "Hi {{name}},\n\nHere's the latest from the GOFI family. Thank you for helping us raise "
        "life-changing dogs!",
    ),
    "incident_update": (
        "Update on your report",
        "Hello,\n\nThank you for your report. Its status is now: {{status}}.\n\n"
        "We appreciate you letting us know.",
    ),
    "application_received": (
        "We received your Puppy Raiser application",
        "Thank you for applying to raise a service dog in training with GOFI. Our team will review "
        "your application and be in touch. We're grateful you want to help.",
    ),
    "application_approved": (
        "Your GOFI Puppy Raiser application — approved!",
        "Great news — your application to become a GOFI Puppy Raiser has been approved. A "
        "coordinator will reach out with next steps, training, and your certification.",
    ),
    "application_declined": (
        "Update on your GOFI Puppy Raiser application",
        "Thank you for your interest in raising a service dog with GOFI. We're not able to move "
        "forward with your application at this time, but we'd welcome you in other volunteer roles.",
    ),
    "donation_thank_you": (
        "Thank you for your donation",
        "Thank you for your generous gift of {{amount_minor_units}} {{currency}} (minor units).\n"
        "Your official receipt will follow. We're grateful for your support!",
    ),
    "shift_reminder": (
        "Reminder: your upcoming shift",
        "Hi {{name}},\n\nThis is a friendly reminder about your upcoming shift on {{when}} at "
        "{{location}}. Thank you — see you there!",
    ),
}


def seed_bootstrap(db: Session, *, include_demo: bool = True) -> Organization:
    """Idempotent first-boot bootstrap. Structural data (org, roles, admin, email templates,
    starter pages, the incident form) is always seeded; sample content (a demo training session +
    volunteer opportunity + social channel) only when `include_demo` (never in production)."""
    org = db.scalar(select(Organization).where(Organization.slug == settings.bootstrap_org_slug))
    if org is None:
        org = Organization(name=settings.bootstrap_org_name, slug=settings.bootstrap_org_slug)
        db.add(org)
        db.flush()

    _seed_roles(db, org.id)
    _seed_admin(db, org.id)
    _seed_templates(db, org.id)
    _seed_pages(db, org.id)
    _seed_forms(db, org.id)
    if settings.seed_org_content:
        _seed_gofi_programs(db, org.id, include_demo=include_demo)
    if include_demo:
        _seed_demo_training(db, org.id)
        _seed_demo_opportunity(db, org.id)
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
        db, org_id=org_id, title="Puppy Raiser Meet & Greet", kind="event", is_public=True,
        description="Curious about raising a service dog in training? Come meet our puppy raisers "
                    "and dogs, ask questions, and learn what the commitment looks like. Families "
                    "welcome — no experience needed.")
    for week in (1, 2):
        start = (utcnow() + timedelta(days=7 * week)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        shift = scheduling.create_shift(db, org_id=org_id, event_id=event.id, starts_at=start,
                                        ends_at=start + timedelta(hours=2),
                                        location="GOFI, 323 High Street, Walpole, MA")
        scheduling.add_role(db, org_id=org_id, shift_id=shift.id, name="Attendee", capacity=20)
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

    # Starter public pages, editable in the website builder, populated with GOFI's real content.
    faq_html = (
        "<details><summary>Do I need experience to be a puppy raiser?</summary><p>No. Puppy "
        "raisers are the backbone of our Service Dog Program, and we guide you the whole way "
        "with training and support.</p></details>"
        "<details><summary>What dogs does GOFI train?</summary><p>We breed and train Golden "
        "Retrievers for three programs: Service Dogs, Facility Dogs, and Crisis Response Dogs "
        "(CRD).</p></details>"
        "<details><summary>Where are you located?</summary><p>323 High Street, Walpole, MA "
        "02081. We are a 501(c)(3) nonprofit.</p></details>"
        "<details><summary>What's the time commitment?</summary><p>It depends on the role — "
        "puppy raising is a longer commitment, while events and other help can be occasional. "
        "Sign up and we'll talk through what fits.</p></details>"
        "<details><summary>How else can I help?</summary><p>Foster or raise a puppy, host a "
        "fundraiser, donate, or send supplies from our wish list. Every bit helps a dog change "
        "a life.</p></details>"
    )
    pages = [
        ("about", "About us", 1, True, [
            {"type": "heading", "level": 1, "text": "About Golden Opportunities for Independence"},
            para("Through compassion, purpose-driven training, and the healing power of the "
                 "human–canine bond, we strive to create a more inclusive, independent, and "
                 "empowered future for all."),
            para("GOFI breeds and trains Golden Retriever service dogs across three programs — "
                 "Service Dogs, Facility Dogs, and Crisis Response Dogs — and places them with "
                 "the people and organizations who need them. We're a 501(c)(3) nonprofit based in "
                 "Walpole, Massachusetts, where every volunteer, recipient, and dog becomes family."),
            {"type": "button", "label": "Get involved", "href": "/opportunities"},
        ]),
        ("programs", "Our programs", 2, True, [
            {"type": "heading", "level": 1, "text": "Our programs"},
            para("GOFI breeds and trains Golden Retrievers for three programs. Volunteer "
                 "<strong>puppy raisers</strong> give each dog its start; <strong>puppy sitters</strong> "
                 "provide short-term respite care when a raiser is away."),
            {"type": "heading", "level": 2, "text": "Service Dogs"},
            para("Partnered with individuals living with disabilities to open doors to greater "
                 "independence."),
            {"type": "heading", "level": 2, "text": "Facility Dogs"},
            para("Placed with professionals in schools, hospitals, and courts to bring calm and "
                 "connection where it's needed most."),
            {"type": "heading", "level": 2, "text": "Crisis Response Dogs"},
            para("Deployed with handlers to comfort people in the aftermath of trauma and disaster."),
            {"type": "button", "label": "Apply to raise a puppy",
             "href": "/forms/puppy_raiser_application"},
        ]),
        ("get-involved", "Get involved", 3, True, [
            {"type": "heading", "level": 1, "text": "Get involved"},
            para("Our volunteer puppy raisers are the backbone of the Service Dog Program — "
                 "raising a young dog and giving it the foundation to change someone's life. It's "
                 "the most hands-on way to help, and we support you every step of the way."),
            para("Not able to raise a puppy? Become a puppy sitter for short-term respite care, "
                 "foster, host a fundraiser, donate, or send supplies from our wish list."),
            {"type": "button", "label": "Apply to raise a puppy",
             "href": "/forms/puppy_raiser_application"},
            {"type": "button", "label": "Donate", "href": "/donate?campaign=raise-a-service-dog"},
            {"type": "button", "label": "See opportunities", "href": "/opportunities"},
        ]),
        # FAQ + Contact are editable and served at /faq /contact, linked from the footer.
        ("faq", "FAQ", 3, False, [
            {"type": "heading", "level": 1, "text": "Frequently asked questions"},
            {"type": "html", "safe_html": faq_html},
        ]),
        ("contact", "Contact", 4, False, [
            {"type": "heading", "level": 1, "text": "Contact us"},
            para("Golden Opportunities for Independence &middot; 323 High Street, Walpole, MA 02081 "
                 "&middot; (502)-501-GOFI. We'll get back to you within a couple of days."),
            {"type": "button", "label": "Email contact@gofidog.org",
             "href": "mailto:contact@gofidog.org"},
        ]),
    ]
    now = utcnow()
    for slug, title, order, in_nav, blocks in pages:
        db.add(Page(org_id=org_id, slug=slug, title=title, status=PageStatus.published,
                    blocks=blocks, published_blocks=blocks, published_css="", published_at=now,
                    show_in_nav=in_nav, nav_order=order))
    db.flush()


def _seed_social(db: Session, org_id: int) -> None:
    """Seed one manual channel so the social composer works out of the box (no external creds)."""
    from app.modules.social.models import Platform, SocialChannel

    if db.scalar(select(func.count()).select_from(SocialChannel).where(
            SocialChannel.org_id == org_id)):
        return
    db.add(SocialChannel(org_id=org_id, platform=Platform.manual, handle="@gofidog",
                         display_name="GOFI (manual)", char_limit=280))
    db.flush()


def _seed_forms(db: Session, org_id: int) -> None:
    """Seed the incident-report process as CONFIG — a FormDefinition + a WorkflowDefinition — to
    demonstrate that a new operational process is data, not code."""
    from app.modules.forms.models import FormDefinition
    from app.modules.forms.service import create_definition, create_draft_version, publish_version
    from app.modules.workflows.models import WorkflowDefinition

    if db.scalar(select(func.count()).select_from(FormDefinition).where(
            FormDefinition.org_id == org_id)):
        return

    # The state machine (every arrow is one row of JSON, no code).
    db.add(WorkflowDefinition(
        org_id=org_id, key="incident_report", name="Incident report", subject_type="form_submission",
        initial_state="reported",
        states=[{"name": "reported", "sla_hours": 48}, {"name": "needs_triage"},
                {"name": "in_progress"}, {"name": "resolved", "is_terminal": True},
                {"name": "rejected", "is_terminal": True}],
        transitions=[
            {"name": "triage", "from": "reported", "to": "needs_triage",
             "permission": "incident.triage", "entry_actions": [{"emit_audit": "incident.triaged"}]},
            {"name": "start", "from": "needs_triage", "to": "in_progress",
             "permission": "incident.triage"},
            {"name": "reject", "from": "needs_triage", "to": "rejected",
             "permission": "incident.triage"},
            {"name": "resolve", "from": "in_progress", "to": "resolved",
             "permission": "incident.close", "requires_approval": True,
             "action": "work.close",  # R3 — an agent could never execute this
             "entry_actions": [{"emit_audit": "incident.resolved"},
                               {"notify": {"template": "incident_update",
                                           "to": "reporter_contact"}}]},
        ]))
    db.flush()

    definition = create_definition(
        db, org_id=org_id, key="incident_report", name="Report an issue",
        purpose="Report a safety concern, facility problem, or other issue.",
        default_visibility="public", workflow_key="incident_report")
    schema = {"fields": [
        {"key": "category", "type": "select", "label": "What kind of issue?",
         "options": ["safety", "facility", "equipment", "other"], "visibility": "public",
         "validation": {"required": True}},
        {"key": "description", "type": "text", "label": "Describe what happened",
         "visibility": "public", "validation": {"required": True}},
        {"key": "is_injury", "type": "boolean", "label": "Did anyone get hurt?",
         "visibility": "public", "validation": {"required": False}},
        {"key": "reporter_contact", "type": "text", "label": "Your email (optional)",
         "visibility": "public", "validation": {"required": False}},
        # Reviewer-only fields — never shown to or writable by the public reporter.
        {"key": "severity", "type": "select", "label": "Severity",
         "options": ["low", "medium", "high", "critical"], "visibility": "internal",
         "validation": {"required": False}},
        {"key": "internal_notes", "type": "text", "label": "Internal notes",
         "visibility": "internal", "validation": {"required": False}},
    ]}
    fv = create_draft_version(db, org_id=org_id, def_id=definition.id, schema=schema)
    publish_version(db, org_id=org_id, def_id=definition.id, version=fv.version, actor_user_id=None)
    db.flush()


def _seed_gofi_programs(db: Session, org_id: int, *, include_demo: bool = True) -> None:
    """GOFI programs, the two puppy qualifications, the Puppy Raiser application (apply → review →
    approve/decline, emailing the applicant via Phase A's notify→email), and — for demos — a
    certified raiser enrollment, a qualification-gated puppy-sitter signup sheet, and a donation
    campaign. Structural parts always seed; demo content is gated on `include_demo`."""
    from datetime import timedelta

    from app.core.db import utcnow
    from app.modules.forms.models import FormDefinition
    from app.modules.forms.service import create_definition, create_draft_version, publish_version
    from app.modules.org.models import Program
    from app.modules.people.service import create_qualification_type
    from app.modules.workflows.models import WorkflowDefinition

    if db.scalar(select(func.count()).select_from(Program).where(Program.org_id == org_id)):
        return  # idempotent — GOFI programs already seeded

    # --- Programs (the three GOFI service-dog programs) --- #
    programs = {}
    for key, name in (("service_dog", "Service Dog Program"),
                      ("facility_dog", "Facility Dog Program"),
                      ("crisis_response_dog", "Crisis Response Dog Program")):
        p = Program(org_id=org_id, key=key, name=name)
        db.add(p)
        db.flush()
        programs[key] = p

    # --- Qualifications: raiser (long-term) vs sitter (short-term respite) --- #
    raiser_qual = create_qualification_type(
        db, org_id=org_id, key="puppy_raiser_certified", label="Puppy Raiser Certified")
    sitter_qual = create_qualification_type(
        db, org_id=org_id, key="puppy_sitter_certified", label="Puppy Sitter Certified")

    # --- Puppy Raiser application: governed apply → review → approve/decline, emailing the
    #     applicant (Phase A notify→email uses the submission's `email` answer). --- #
    if db.scalar(select(FormDefinition).where(FormDefinition.org_id == org_id,
                                              FormDefinition.key == "puppy_raiser_application")) is None:
        db.add(WorkflowDefinition(
            org_id=org_id, key="volunteer_application", name="Volunteer application",
            subject_type="form_submission", initial_state="submitted",
            states=[{"name": "submitted", "sla_hours": 168}, {"name": "under_review"},
                    {"name": "approved", "is_terminal": True},
                    {"name": "declined", "is_terminal": True}],
            transitions=[
                {"name": "start_review", "from": "submitted", "to": "under_review",
                 "permission": "forms.review",
                 "entry_actions": [{"emit_audit": "application.reviewing"}]},
                {"name": "approve", "from": "under_review", "to": "approved",
                 "permission": "forms.review",
                 "entry_actions": [{"emit_audit": "application.approved"},
                                   {"notify": {"template": "application_approved", "to": "email"}}]},
                {"name": "decline", "from": "under_review", "to": "declined",
                 "permission": "forms.review",
                 "entry_actions": [{"emit_audit": "application.declined"},
                                   {"notify": {"template": "application_declined", "to": "email"}}]},
            ]))
        db.flush()
        app_def = create_definition(
            db, org_id=org_id, key="puppy_raiser_application", name="Puppy Raiser application",
            purpose="Apply to raise a service dog in training as a GOFI puppy raiser.",
            default_visibility="public", workflow_key="volunteer_application")
        app_schema = {"fields": [
            {"key": "full_name", "type": "text", "label": "Your full name",
             "visibility": "public", "validation": {"required": True}},
            {"key": "email", "type": "text", "label": "Email",
             "visibility": "public", "validation": {"required": True}},
            {"key": "phone", "type": "text", "label": "Phone", "visibility": "public",
             "validation": {"required": False}},
            {"key": "town", "type": "text", "label": "Town / area you live in",
             "visibility": "public", "validation": {"required": True}},
            {"key": "home_type", "type": "select", "label": "Your home",
             "options": ["House with a yard", "House, no yard", "Apartment/condo", "Other"],
             "visibility": "public", "validation": {"required": True}},
            {"key": "has_other_pets", "type": "boolean", "label": "Do you have other pets?",
             "visibility": "public", "validation": {"required": False}},
            {"key": "experience", "type": "text",
             "label": "Tell us about your experience with dogs",
             "visibility": "public", "validation": {"required": False}},
            {"key": "availability", "type": "select",
             "label": "Can you commit to raising a puppy (~12-18 months)?",
             "options": ["Yes", "Not sure — I have questions", "No, other volunteering only"],
             "visibility": "public", "validation": {"required": True}},
            {"key": "why", "type": "text", "label": "Why do you want to be a puppy raiser?",
             "visibility": "public", "validation": {"required": False}},
            {"key": "reviewer_notes", "type": "text", "label": "Reviewer notes",
             "visibility": "internal", "validation": {"required": False}},
        ]}
        afv = create_draft_version(db, org_id=org_id, def_id=app_def.id, schema=app_schema)
        publish_version(db, org_id=org_id, def_id=app_def.id, version=afv.version,
                        actor_user_id=None)
        db.flush()

    if not include_demo:
        return

    # --- Demo: a certified puppy raiser enrolled long-term in the Service Dog program --- #
    from app.modules.people.models import VolunteerProfile
    from app.modules.people.service import enroll, grant_qualification

    raiser_email = "demo.raiser@gofidog.org"
    person = db.scalar(select(Person).where(Person.org_id == org_id,
                                            Person.email == raiser_email))
    if person is None:
        person = Person(org_id=org_id, name="Dana Raiser", email=raiser_email, email_verified=True)
        db.add(person)
        db.flush()
        user = User(org_id=org_id, person_id=person.id)
        db.add(user)
        db.flush()
        db.add(VolunteerProfile(org_id=org_id, person_id=person.id))
        vol_role = db.scalar(select(Role).where(Role.org_id == org_id, Role.key == "volunteer"))
        if vol_role is not None:
            db.add(UserRoleAssignment(org_id=org_id, user_id=user.id, role_id=vol_role.id))
        db.flush()
        grant_qualification(db, org_id=org_id, volunteer_email=raiser_email,
                            qualification_type_id=raiser_qual.id, source="seed")
        enroll(db, org_id=org_id, volunteer_email=raiser_email,
               program_id=programs["service_dog"].id, role="puppy_raiser",
               notes="Demo long-term raiser enrollment.")

    # --- Demo: a qualification-gated Puppy Sitter respite signup sheet --- #
    from app.modules.scheduling.service import create_event, create_recurring_shifts

    ev = create_event(db, org_id=org_id, title="Puppy Sitter — respite care",
                      kind="event", is_public=True, program_id=programs["service_dog"].id,
                      description="Short-term care for a service-dog-in-training while their raiser "
                                  "is away. Requires Puppy Sitter certification.")
    start = (utcnow() + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
    create_recurring_shifts(
        db, org_id=org_id, event_id=ev.id, starts_at=start, ends_at=start + timedelta(hours=8),
        location="Sitter's home", repeat="weekly", count=4,
        roles=[{"name": "Puppy Sitter", "capacity": 1,
                "required_qualification_type_id": sitter_qual.id}])

    # --- Demo: a public donation campaign (Phase C) --- #
    from app.modules.donations.service import create_campaign, update_campaign

    campaign = create_campaign(
        db, org_id=org_id, slug="raise-a-service-dog", title="Raise a Service Dog",
        description="It costs about $45,000 to breed, raise, and train one GOFI service dog. Your "
                    "gift helps place a life-changing dog with someone who needs one.",
        goal_minor_units=4500000, currency="USD", suggested_amounts=[2500, 5000, 10000, 25000])
    update_campaign(db, org_id=org_id, campaign_id=campaign.id, status="active", is_public=True,
                    publish_progress=True)
    db.flush()
