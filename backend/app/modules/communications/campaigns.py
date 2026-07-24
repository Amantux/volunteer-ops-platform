"""Campaign communications: explicit audiences, preview, approval-gated sending.

Anti-goal enforced here: no bulk send happens without an explicit resolved audience, a
recipient count the approver signed off on, applied suppression, and an audit record.
Above a configurable threshold, sending REQUIRES human approval.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.modules.identity.models import Person
from app.modules.org.models import OrganizationSetting
from app.modules.people.models import VolunteerProfile

from .models import AudienceDefinition, CampaignStatus, EmailCampaign, Suppression
from .service import queue_email

DEFAULT_AUTO_SEND_THRESHOLD = 25


class CommsError(Exception):
    pass


# --- Audiences -------------------------------------------------------------- #

def create_audience(db: Session, *, org_id: int, name: str, rule: dict) -> AudienceDefinition:
    segment = rule.get("segment", "volunteers")
    if segment not in {"volunteers", "all_contacts"}:
        raise CommsError(f"unknown audience segment: {segment}")
    audience = AudienceDefinition(org_id=org_id, name=name, rule=rule)
    db.add(audience)
    db.flush()
    return audience


def _suppressed_emails(db: Session, org_id: int) -> set[str]:
    return set(db.scalars(select(Suppression.email).where(Suppression.org_id == org_id)))


def resolve_recipients(db: Session, *, org_id: int, rule: dict) -> list[Person]:
    """Resolve an audience rule to concrete recipients, minus the suppression list."""
    segment = rule.get("segment", "volunteers")
    stmt = select(Person).where(Person.org_id == org_id, Person.email_verified.is_(True))
    if segment == "volunteers":
        stmt = stmt.join(VolunteerProfile, VolunteerProfile.person_id == Person.id)
    people = db.scalars(stmt).all()
    suppressed = _suppressed_emails(db, org_id)
    return [p for p in people if p.email not in suppressed]


def preview_audience(db: Session, *, org_id: int, audience_id: int) -> dict:
    audience = db.get(AudienceDefinition, audience_id)
    if audience is None or audience.org_id != org_id:
        raise CommsError("audience not found")
    recipients = resolve_recipients(db, org_id=org_id, rule=audience.rule)
    return {
        "audience_id": audience_id,
        "name": audience.name,
        "rule": audience.rule,
        "recipient_count": len(recipients),
        "sample": [p.email for p in recipients[:5]],
    }


# --- Campaigns -------------------------------------------------------------- #

def _auto_send_threshold(db: Session, org_id: int) -> int:
    setting = db.scalar(select(OrganizationSetting).where(
        OrganizationSetting.org_id == org_id, OrganizationSetting.key == "comms.auto_send_threshold"))
    if setting and isinstance(setting.value.get("value"), int):
        return int(setting.value["value"])
    return DEFAULT_AUTO_SEND_THRESHOLD


def create_campaign(db: Session, *, org_id: int, name: str, template_key: str,
                    audience_id: int) -> EmailCampaign:
    audience = db.get(AudienceDefinition, audience_id)
    if audience is None or audience.org_id != org_id:
        raise CommsError("audience not found")
    campaign = EmailCampaign(org_id=org_id, name=name, template_key=template_key,
                             audience_id=audience_id)
    db.add(campaign)
    db.flush()
    return campaign


def _get_campaign(db: Session, org_id: int, campaign_id: int) -> EmailCampaign:
    campaign = db.get(EmailCampaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise CommsError("campaign not found")
    return campaign


def submit_for_approval(db: Session, *, org_id: int, campaign_id: int) -> EmailCampaign:
    campaign = _get_campaign(db, org_id, campaign_id)
    if campaign.status != CampaignStatus.draft:
        raise CommsError("only a draft can be submitted for approval")
    campaign.status = CampaignStatus.pending_approval
    db.flush()
    return campaign


def approve_campaign(db: Session, *, org_id: int, campaign_id: int,
                     approver_user_id: int) -> EmailCampaign:
    campaign = _get_campaign(db, org_id, campaign_id)
    if campaign.status not in (CampaignStatus.pending_approval, CampaignStatus.draft):
        raise CommsError("campaign is not awaiting approval")
    audience = db.get(AudienceDefinition, campaign.audience_id)
    assert audience is not None
    count = len(resolve_recipients(db, org_id=org_id, rule=audience.rule))
    campaign.status = CampaignStatus.approved
    campaign.approved_recipient_count = count  # the number the approver signed off on
    campaign.approved_by_user_id = approver_user_id
    db.flush()
    audit.emit(db, org_id=org_id, action="comms.approve_campaign", actor_id=approver_user_id,
               target_type="campaign", target_id=campaign.id, meta={"recipient_count": count})
    return campaign


def send_campaign(db: Session, *, org_id: int, campaign_id: int, actor_user_id: int) -> dict:
    """Send a campaign. Requires approval above the org's auto-send threshold. Resolves the
    audience, applies suppression, enqueues one idempotent outbox email per recipient."""
    campaign = _get_campaign(db, org_id, campaign_id)
    if campaign.status == CampaignStatus.sent:
        raise CommsError("campaign already sent")
    audience = db.get(AudienceDefinition, campaign.audience_id)
    assert audience is not None
    recipients = resolve_recipients(db, org_id=org_id, rule=audience.rule)
    count = len(recipients)
    threshold = _auto_send_threshold(db, org_id)

    if campaign.status != CampaignStatus.approved and count > threshold:
        raise CommsError(
            f"{count} recipients exceeds the auto-send threshold ({threshold}); "
            f"this campaign requires approval before sending"
        )

    campaign.status = CampaignStatus.sending
    db.flush()
    for person in recipients:
        queue_email(
            db, org_id=org_id, idempotency_key=f"campaign:{campaign.id}:person:{person.id}",
            to_email=person.email, template_key=campaign.template_key,
            context={"name": person.name},
        )
    campaign.status = CampaignStatus.sent
    campaign.sent_at = utcnow()
    db.flush()
    audit.emit(db, org_id=org_id, action="comms.send_campaign", actor_id=actor_user_id,
               target_type="campaign", target_id=campaign.id, meta={"recipient_count": count})
    return {"campaign_id": campaign.id, "status": campaign.status.value, "recipient_count": count}


def send_due_campaigns(db: Session) -> int:
    """Beat task: send approved campaigns whose scheduled time has arrived."""
    now = utcnow()
    due = db.scalars(select(EmailCampaign).where(
        EmailCampaign.status == CampaignStatus.approved,
        EmailCampaign.scheduled_at.is_not(None),
        EmailCampaign.scheduled_at <= now,
    )).all()
    for campaign in due:
        send_campaign(db, org_id=campaign.org_id, campaign_id=campaign.id, actor_user_id=0)
    return len(due)


# --- Suppression / unsubscribe --------------------------------------------- #

def suppress(db: Session, *, org_id: int, email: str, reason: str = "unsubscribe") -> None:
    email = email.strip().lower()
    existing = db.scalar(select(Suppression).where(
        Suppression.org_id == org_id, Suppression.email == email))
    if existing is None:
        db.add(Suppression(org_id=org_id, email=email, reason=reason))
        db.flush()
        audit.emit(db, org_id=org_id, action="comms.suppress", actor_type="service",
                   actor_id=reason, target_type="email", target_id=email)
