"""Launch-hardening: form submit acknowledgement email, abandoned-donation drift sweep, and the
rate limiter's enforcement (the Redis backend is selected in prod; the memory backend is tested)."""

from __future__ import annotations

from datetime import timedelta

from conftest import inbox, relay

from app.core.db import utcnow
from app.modules.donations.models import Donation, DonationStatus
from app.modules.donations.service import (
    create_campaign,
    expire_stale_pending_donations,
    update_campaign,
)


def test_form_ack_emails_the_submitter_on_submit(db, org, client):
    from app.modules.communications.models import EmailTemplate
    from app.modules.forms.service import (
        create_definition,
        create_draft_version,
        publish_version,
    )
    db.add(EmailTemplate(org_id=org.id, key="signup_ack", subject="Thanks!",
                         body_text="We received your {{form}} — thank you."))
    d = create_definition(db, org_id=org.id, key="newsletter_signup", name="Newsletter signup",
                          default_visibility="public", ack_template_key="signup_ack",
                          ack_recipient_field="email")
    v = create_draft_version(db, org_id=org.id, def_id=d.id, schema={"fields": [
        {"key": "email", "type": "text", "label": "Email", "visibility": "public",
         "validation": {"required": True}}]})
    publish_version(db, org_id=org.id, def_id=d.id, version=v.version, actor_user_id=None)
    db.commit()

    r = client.post("/api/forms/newsletter_signup/submissions",
                    json={"answers": {"email": "subscriber@x.org"}})
    assert r.status_code == 201
    relay(db)  # form-ack -> email.send -> dev inbox
    assert any(m.to_email == "subscriber@x.org" for m in inbox(db, org.id))


def test_ack_email_is_capped_per_recipient(db, org, client):
    """Repeated submissions naming the same address can't email-bomb it (per-recipient cap)."""
    from app.core import ratelimit
    from app.modules.communications.models import EmailTemplate
    from app.modules.forms.service import (
        create_definition,
        create_draft_version,
        publish_version,
    )
    ratelimit._hits.clear()
    db.add(EmailTemplate(org_id=org.id, key="ack2", subject="Thanks", body_text="ok {{form}}"))
    d = create_definition(db, org_id=org.id, key="signup2", name="Signup 2",
                          default_visibility="public", ack_template_key="ack2",
                          ack_recipient_field="email")
    v = create_draft_version(db, org_id=org.id, def_id=d.id, schema={"fields": [
        {"key": "email", "type": "text", "label": "Email", "visibility": "public",
         "validation": {"required": True}}]})
    publish_version(db, org_id=org.id, def_id=d.id, version=v.version, actor_user_id=None)
    db.commit()

    for _ in range(5):
        client.post("/api/forms/signup2/submissions", json={"answers": {"email": "victim@x.org"}})
    relay(db)
    acks = [m for m in inbox(db, org.id) if m.to_email == "victim@x.org"]
    assert len(acks) == 3  # capped at the per-recipient limit despite 5 submissions


def test_form_without_ack_config_sends_nothing(db, org, client):
    # The incident form has no ack config → a submission queues no acknowledgement.
    before = len(inbox(db, org.id))
    client.post("/api/forms/incident_report/submissions",
                json={"answers": {"category": "safety", "description": "x"}})
    relay(db)
    assert len(inbox(db, org.id)) == before


def _pending_donation(db, org, *, key, token, age_hours):
    campaign = create_campaign(db, org_id=org.id, slug=f"c-{key}", title="C")
    update_campaign(db, org_id=org.id, campaign_id=campaign.id, status="active", is_public=True)
    d = Donation(org_id=org.id, campaign_id=campaign.id, amount_minor_units=1000, currency="USD",
                 idempotency_key=key, public_token=token, provider="fake")
    db.add(d)
    db.flush()
    d.created_at = utcnow() - timedelta(hours=age_hours)
    db.flush()
    return d


def test_sweep_fails_abandoned_pending_but_spares_fresh_ones(db, org):
    stale = _pending_donation(db, org, key="k1", token="t1", age_hours=48)
    fresh = _pending_donation(db, org, key="k2", token="t2", age_hours=1)
    assert expire_stale_pending_donations(db, older_than_hours=24) == 1
    db.refresh(stale)
    db.refresh(fresh)
    assert stale.status == DonationStatus.failed
    assert fresh.status == DonationStatus.pending
    # Idempotent: a second sweep finds nothing new.
    assert expire_stale_pending_donations(db, older_than_hours=24) == 0


def test_memory_rate_limiter_enforces_limit():
    from app.core import ratelimit
    ratelimit._hits.clear()
    key = "unit-test-ip"
    assert all(ratelimit.allow(key, limit=3, window_seconds=60) for _ in range(3))
    assert ratelimit.allow(key, limit=3, window_seconds=60) is False
