"""Communications: audience preview, approval-gated send, suppression/unsubscribe, outbox."""

from __future__ import annotations

from conftest import inbox, relay
from sqlalchemy import func, select

from app.modules.communications.models import EmailCampaign, Suppression
from app.modules.identity.models import Person
from app.modules.org.models import OrganizationSetting
from app.modules.people.models import VolunteerProfile


def _volunteer(db, org, email):
    person = Person(org_id=org.id, name=email.split("@")[0], email=email, email_verified=True)
    db.add(person)
    db.flush()
    db.add(VolunteerProfile(org_id=org.id, person_id=person.id))
    db.commit()
    return person


def _set_threshold(db, org, n):
    db.add(OrganizationSetting(org_id=org.id, key="comms.auto_send_threshold",
                               value={"value": n}))
    db.commit()


def test_audience_preview_counts_and_samples(client, db, org, admin_headers):
    _volunteer(db, org, "a@x.org")
    _volunteer(db, org, "b@x.org")
    aid = client.post("/api/comms/audiences", headers=admin_headers,
                      json={"name": "All volunteers", "rule": {"segment": "volunteers"}}).json()["id"]
    preview = client.get(f"/api/comms/audiences/{aid}/preview", headers=admin_headers).json()
    assert preview["recipient_count"] == 2
    assert set(preview["sample"]) == {"a@x.org", "b@x.org"}


def test_send_requires_approval_above_threshold(client, db, org, admin_headers):
    _volunteer(db, org, "a@x.org")
    _volunteer(db, org, "b@x.org")
    _set_threshold(db, org, 1)  # 2 recipients > 1 -> approval required
    aid = client.post("/api/comms/audiences", headers=admin_headers,
                      json={"name": "vols", "rule": {"segment": "volunteers"}}).json()["id"]
    cid = client.post("/api/comms/campaigns", headers=admin_headers,
                      json={"name": "News", "template_key": "newsletter", "audience_id": aid}).json()["id"]

    # Sending without approval is refused.
    blocked = client.post(f"/api/comms/campaigns/{cid}/send", headers=admin_headers)
    assert blocked.status_code == 409 and "approval" in blocked.json()["detail"].lower()

    # Approve (records the count the approver signed off on) then send.
    client.post(f"/api/comms/campaigns/{cid}/submit", headers=admin_headers)
    approved = client.post(f"/api/comms/campaigns/{cid}/approve", headers=admin_headers)
    assert approved.status_code == 200
    sent = client.post(f"/api/comms/campaigns/{cid}/send", headers=admin_headers)
    assert sent.status_code == 200 and sent.json()["recipient_count"] == 2

    campaign = db.scalar(select(EmailCampaign).where(EmailCampaign.id == cid))
    assert campaign.approved_recipient_count == 2 and campaign.approved_by_user_id is not None

    # The emails go out through the outbox (one per recipient), not synchronously.
    relay(db)
    news = [m for m in inbox(db, org.id) if "News from" in m.subject]
    assert len(news) == 2


def test_small_campaign_auto_sends_below_threshold(client, db, org, admin_headers):
    _volunteer(db, org, "a@x.org")  # 1 recipient, default threshold 25
    aid = client.post("/api/comms/audiences", headers=admin_headers,
                      json={"name": "vols", "rule": {"segment": "volunteers"}}).json()["id"]
    cid = client.post("/api/comms/campaigns", headers=admin_headers,
                      json={"name": "N", "template_key": "newsletter", "audience_id": aid}).json()["id"]
    # No approval needed under the threshold.
    resp = client.post(f"/api/comms/campaigns/{cid}/send", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["recipient_count"] == 1


def test_unsubscribe_suppresses_recipient(client, db, org, admin_headers):
    _volunteer(db, org, "keep@x.org")
    _volunteer(db, org, "leave@x.org")
    aid = client.post("/api/comms/audiences", headers=admin_headers,
                      json={"name": "vols", "rule": {"segment": "volunteers"}}).json()["id"]
    assert client.get(f"/api/comms/audiences/{aid}/preview", headers=admin_headers).json()["recipient_count"] == 2

    resp = client.post("/api/comms/unsubscribe", json={"email": "leave@x.org"})
    assert resp.status_code == 200
    assert db.scalar(select(func.count()).select_from(Suppression)) == 1
    # Suppressed address is excluded from the audience.
    assert client.get(f"/api/comms/audiences/{aid}/preview", headers=admin_headers).json()["recipient_count"] == 1


def test_send_is_not_repeatable(client, db, org, admin_headers):
    _volunteer(db, org, "a@x.org")
    aid = client.post("/api/comms/audiences", headers=admin_headers,
                      json={"name": "vols", "rule": {"segment": "volunteers"}}).json()["id"]
    cid = client.post("/api/comms/campaigns", headers=admin_headers,
                      json={"name": "N", "template_key": "newsletter", "audience_id": aid}).json()["id"]
    assert client.post(f"/api/comms/campaigns/{cid}/send", headers=admin_headers).status_code == 200
    assert client.post(f"/api/comms/campaigns/{cid}/send", headers=admin_headers).status_code == 409
