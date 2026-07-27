"""Donations: the donate→verified-webhook→immutable-receipt lifecycle plus the five hard
invariants from docs/architecture/donations-design.md §1.1 (NO-PAN, WEBHOOK-AUTHORITATIVE,
AGENT-NO-REFUND, DONOR-SEPARATION, ORG-SCOPED). The Fake provider signs webhooks the same way
the real one would, so the whole path runs with no network."""

from __future__ import annotations

import json

from conftest import relay
from sqlalchemy import select

from app.core.session import make_session_token
from app.modules.donations import service
from app.modules.donations.models import (
    Donation,
    DonationReceipt,
    DonationStatus,
    PaymentEvent,
)
from app.modules.donations.payments.fake import FakePaymentProvider
from app.modules.identity.models import Person, Role, User, UserRoleAssignment


def _campaign(db, org, *, slug="rescue", public=True, active=True):
    c = service.create_campaign(db, org_id=org.id, slug=slug, title="Rescue Fund",
                                goal_minor_units=100000, suggested_amounts=[2500, 5000])
    if public:
        c.is_public = True
    if active:
        from app.modules.donations.models import CampaignStatus
        c.status = CampaignStatus.active
    db.commit()
    return c


def _volunteer_headers(db, org, email="vol@x.org"):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == "volunteer"))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


def _deliver_webhook(client, db, donation_id, *, event_id, event_type, charge="ch_1",
                     amount_refunded=None):
    """Build a provider-signed event for a donation and POST it to the webhook route."""
    d = db.get(Donation, donation_id)
    data = {"metadata": {"idempotency_key": d.idempotency_key}, "client_reference_id": d.id,
            "amount_total": d.amount_minor_units, "currency": d.currency.lower(),
            "status": "complete", "latest_charge": charge}
    if amount_refunded is not None:
        data["amount_refunded"] = amount_refunded
    payload, sig = FakePaymentProvider.make_signed_event(event_id, event_type, data)
    return client.post("/api/webhooks/payments", content=payload, headers={"X-Signature": sig})


def _donate(client, slug="rescue", amount=5000, **kw):
    body = {"campaign_slug": slug, "amount_minor_units": amount, **kw}
    return client.post("/api/public/donations", json=body)


# --- Exit criterion: test-mode donation → receipt --------------------------- #

def test_full_donation_lifecycle_to_receipt(db, org, client):
    _campaign(db, org)
    r = _donate(client, donor_name="Ada", donor_email="ada@x.org")
    assert r.status_code == 201
    token = r.json()["token"]
    did = r.json()["donation_id"]

    # Redirect/return page shows pending until the webhook lands (INV-WEBHOOK-AUTHORITATIVE).
    assert client.get(f"/api/public/donations/status?token={token}").json()["status"] == "pending"

    relay(db)  # donation.checkout -> populates hosted checkout URL
    assert client.get(f"/api/public/donations/status?token={token}").json()["checkout_url"]

    resp = _deliver_webhook(client, db, did, event_id="evt_1",
                            event_type="checkout.session.completed")
    assert resp.status_code == 200 and resp.json()["outcome"] == "applied"
    db.expire_all()
    assert db.get(Donation, did).status == DonationStatus.succeeded

    relay(db)  # donation.succeeded -> issues receipt + queues thank-you email
    receipt = db.scalar(select(DonationReceipt).where(DonationReceipt.donation_id == did))
    assert receipt is not None
    assert receipt.receipt_number.endswith("-000001")


def test_receipt_numbers_are_gapless_per_year(db, org, client):
    _campaign(db, org)
    numbers = []
    for i in range(2):
        did = _donate(client, donor_email=f"d{i}@x.org").json()["donation_id"]
        relay(db)
        _deliver_webhook(client, db, did, event_id=f"evt_{i}",
                         event_type="checkout.session.completed")
        relay(db)
        db.expire_all()
        numbers.append(db.scalar(select(DonationReceipt).where(
            DonationReceipt.donation_id == did)).sequence_no)
    assert numbers == [1, 2]


# --- INV-WEBHOOK-AUTHORITATIVE + replay safety ------------------------------ #

def test_bad_webhook_signature_is_rejected(db, org, client):
    _campaign(db, org)
    did = _donate(client).json()["donation_id"]
    payload = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {}}).encode()
    resp = client.post("/api/webhooks/payments", content=payload,
                       headers={"X-Signature": "deadbeef"})
    assert resp.status_code == 401
    db.expire_all()
    assert db.get(Donation, did).status == DonationStatus.pending  # never marked paid


def test_duplicate_webhook_event_is_a_noop(db, org, client):
    _campaign(db, org)
    did = _donate(client, donor_email="dup@x.org").json()["donation_id"]
    relay(db)
    first = _deliver_webhook(client, db, did, event_id="evt_same",
                             event_type="checkout.session.completed")
    second = _deliver_webhook(client, db, did, event_id="evt_same",
                              event_type="checkout.session.completed")
    assert first.json()["outcome"] == "applied"
    assert second.json()["outcome"] == "duplicate"
    relay(db)
    db.expire_all()
    # Exactly one receipt despite the replay.
    assert len(list(db.scalars(select(DonationReceipt).where(
        DonationReceipt.donation_id == did)))) == 1
    assert len(list(db.scalars(select(PaymentEvent).where(
        PaymentEvent.provider_event_id == "evt_same")))) == 1


# --- INV-NO-PAN ------------------------------------------------------------- #

def test_payment_event_digest_holds_no_card_data(db, org, client):
    _campaign(db, org)
    did = _donate(client, donor_email="nopan@x.org").json()["donation_id"]
    relay(db)
    # Include card-looking fields in the event; the digest must NOT retain them.
    d = db.get(Donation, did)
    data = {"metadata": {"idempotency_key": d.idempotency_key}, "amount_total": d.amount_minor_units,
            "currency": "usd", "status": "complete", "latest_charge": "ch_1",
            "card": {"number": "4242424242424242", "cvc": "123", "exp_month": 12}}
    payload, sig = FakePaymentProvider.make_signed_event("evt_pan", "checkout.session.completed", data)
    client.post("/api/webhooks/payments", content=payload, headers={"X-Signature": sig})
    db.expire_all()
    pe = db.scalar(select(PaymentEvent).where(PaymentEvent.provider_event_id == "evt_pan"))
    blob = json.dumps(pe.payload_digest)
    assert "4242" not in blob and "cvc" not in blob and "card" not in blob
    assert set(pe.payload_digest.keys()) <= {"amount", "currency", "status", "charge"}


# --- INV-AGENT-NO-REFUND ---------------------------------------------------- #

def test_refund_is_prohibited_for_agents():
    from app.modules.agents import risk
    assert "donation.refund" in risk.PROHIBITED
    assert "finance.modify" in risk.PROHIBITED


# --- INV-DONOR-SEPARATION --------------------------------------------------- #

def test_public_endpoints_never_expose_donor_identity(db, org, client):
    _campaign(db, org)
    r = _donate(client, donor_name="Grace", donor_email="grace@x.org")
    token = r.json()["token"]
    public_campaign = client.get("/api/campaigns/rescue").text.lower()
    status = client.get(f"/api/public/donations/status?token={token}").text.lower()
    assert "grace" not in public_campaign and "grace@x.org" not in public_campaign
    assert "grace" not in status and "grace@x.org" not in status


def test_donor_data_requires_finance_permission(db, org, client):
    _campaign(db, org)
    _donate(client, donor_email="secret@x.org")
    vol = _volunteer_headers(db, org)
    assert client.get("/api/admin/donations", headers=vol).status_code == 403


# --- Public flow guards + refunds via dashboard webhook --------------------- #

def test_campaign_must_be_active_and_public(db, org, client):
    _campaign(db, org, slug="draft1", public=False, active=False)
    assert _donate(client, slug="draft1").status_code == 404  # not a public campaign


def test_dashboard_refund_webhook_reconciles_status(db, org, client):
    _campaign(db, org)
    did = _donate(client, donor_email="ref@x.org", amount=5000).json()["donation_id"]
    relay(db)
    _deliver_webhook(client, db, did, event_id="evt_ok", event_type="checkout.session.completed")
    # A refund initiated in the provider dashboard arrives as a webhook and reconciles here.
    _deliver_webhook(client, db, did, event_id="evt_ref", event_type="charge.refunded",
                     amount_refunded=5000)
    db.expire_all()
    assert db.get(Donation, did).status == DonationStatus.refunded


# --- Reporting, export, recurring, authz ------------------------------------ #

def test_metrics_and_export(db, org, client, admin_headers):
    _campaign(db, org)
    did = _donate(client, donor_email="m@x.org", amount=5000).json()["donation_id"]
    relay(db)
    _deliver_webhook(client, db, did, event_id="evt_m", event_type="checkout.session.completed")
    relay(db)
    m = client.get("/api/admin/donations/metrics", headers=admin_headers).json()
    assert m["volume_minor_units"] == 5000 and m["donation_count"] == 1 and m["donor_count"] == 1
    csv_text = client.get("/api/admin/donations/export.csv", headers=admin_headers).text
    assert "5000" in csv_text and "4242" not in csv_text


def test_recurring_donation_creates_a_plan(db, org, client, admin_headers):
    _campaign(db, org)
    _donate(client, donor_email="r@x.org", amount=1000, kind="recurring")
    m = client.get("/api/admin/donations/metrics", headers=admin_headers).json()
    assert m["active_recurring_plans"] == 1 and m["recurring_mrr_minor_units"] == 1000


def test_campaign_management_requires_permission(db, org, client):
    vol = _volunteer_headers(db, org)
    r = client.post("/api/admin/campaigns", headers=vol,
                    json={"slug": "x", "title": "X"})
    assert r.status_code == 403
