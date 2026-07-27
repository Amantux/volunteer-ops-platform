"""Donations service: campaigns, the donate→hosted-checkout→verified-webhook→immutable-receipt
lifecycle, recurring plans, in-kind gifts, reporting, and CSV export.

Invariants enforced here (docs/architecture/donations-design.md §1.1):
- INV-NO-PAN: only ids + money metadata ever touch the DB/outbox/audit — never card data.
- INV-WEBHOOK-AUTHORITATIVE: a Donation reaches ``succeeded``/``refunded`` ONLY from a
  signature-verified webhook reconciled server-side (never the browser redirect).
- INV-ORG-SCOPED: every row is org-scoped; cross-org access is a miss, not another org's row.
Refund *execution* is intentionally NOT built in v1 (handled in the provider dashboard); a
dashboard-initiated ``charge.refunded`` webhook still reconciles the Donation here.
"""

from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.core.outbox import enqueue, handler
from app.modules.communications.service import queue_email

from .models import (
    CampaignStatus,
    Donation,
    DonationCampaign,
    DonationKind,
    DonationReceipt,
    DonationStatus,
    Donor,
    InKindDonation,
    PaymentEvent,
    ReceiptCounter,
    RecurringDonationPlan,
    RecurringStatus,
)
from .payments.factory import get_payment_provider
from .payments.port import DonationIntent, ProviderEvent

_SUCCEEDED_EVENTS = {"checkout.session.completed", "payment_intent.succeeded",
                     "checkout.session.async_payment_succeeded"}
_FAILED_EVENTS = {"payment_intent.payment_failed", "checkout.session.expired",
                  "checkout.session.async_payment_failed"}
_REFUND_EVENTS = {"charge.refunded"}
# Money is collected only for these session payment_status values; delayed-notification methods
# (ACH/SEPA/OXXO) deliver checkout.session.completed with payment_status="unpaid" and settle later
# via async_payment_succeeded — do NOT issue a receipt for those (design §4 rule 3).
_PAID_STATUSES = {"paid", "no_payment_required"}


class DonationError(Exception):
    pass


def _redact_email(email: str | None) -> str:
    """a***@example.org — never log a full donor email (data-classification.md P3)."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


# --- Campaigns -------------------------------------------------------------- #

def create_campaign(db: Session, *, org_id: int, slug: str, title: str, description: str = "",
                    goal_minor_units: int | None = None, currency: str = "USD",
                    suggested_amounts: list[int] | None = None,
                    designations: list[dict] | None = None) -> DonationCampaign:
    slug = slug.strip().lower()
    if not slug or not title.strip():
        raise DonationError("slug and title are required")
    if db.scalar(select(DonationCampaign).where(DonationCampaign.org_id == org_id,
                                                DonationCampaign.slug == slug)) is not None:
        raise DonationError("a campaign with that slug already exists")
    c = DonationCampaign(org_id=org_id, slug=slug, title=title.strip(), description=description,
                         goal_minor_units=goal_minor_units, currency=currency,
                         suggested_amounts=suggested_amounts or [],
                         designations=designations or [])
    db.add(c)
    db.flush()
    audit.emit(db, org_id=org_id, action="donation.campaign_created", target_type="donation_campaign",
               target_id=c.id)
    return c


def update_campaign(db: Session, *, org_id: int, campaign_id: int, **fields) -> DonationCampaign:
    c = db.get(DonationCampaign, campaign_id)
    if c is None or c.org_id != org_id:
        raise DonationError("campaign not found")
    allowed = {"title", "description", "goal_minor_units", "status", "is_public",
               "publish_progress", "starts_at", "ends_at", "suggested_amounts", "designations"}
    for k, v in fields.items():
        if k in allowed and v is not None:
            setattr(c, k, v)
    db.flush()
    audit.emit(db, org_id=org_id, action="donation.campaign_updated",
               target_type="donation_campaign", target_id=c.id)
    return c


def list_campaigns(db: Session, *, org_id: int) -> list[DonationCampaign]:
    return list(db.scalars(select(DonationCampaign).where(DonationCampaign.org_id == org_id)
                           .order_by(DonationCampaign.created_at.desc())))


def get_public_campaign(db: Session, *, org_id: int, slug: str) -> DonationCampaign | None:
    c = db.scalar(select(DonationCampaign).where(
        DonationCampaign.org_id == org_id, DonationCampaign.slug == slug,
        DonationCampaign.is_public.is_(True)))
    return c


def campaign_progress(db: Session, *, org_id: int, campaign: DonationCampaign) -> dict | None:
    """Public aggregate — returned ONLY when the campaign opts in via publish_progress."""
    if not campaign.publish_progress:
        return None
    raised = db.scalar(select(func.coalesce(func.sum(Donation.amount_minor_units), 0)).where(
        Donation.org_id == org_id, Donation.campaign_id == campaign.id,
        Donation.status == DonationStatus.succeeded)) or 0
    return {"raised_minor_units": int(raised), "goal_minor_units": campaign.goal_minor_units,
            "currency": campaign.currency}


# --- Donors ----------------------------------------------------------------- #

def _resolve_donor(db: Session, *, org_id: int, hard_anonymous: bool, display_name: str,
                   email: str | None, consent_marketing: bool, consent_source: str) -> Donor | None:
    if hard_anonymous:
        return None  # donor_id stays NULL — no donor record at all
    donor = None
    if email:
        donor = db.scalar(select(Donor).where(Donor.org_id == org_id,
                                              Donor.email == email.lower()))
    if donor is None:
        donor = Donor(org_id=org_id, display_name=display_name or "Anonymous",
                      email=email.lower() if email else None, consent_marketing=consent_marketing,
                      consent_source=consent_source)
        db.add(donor)
        db.flush()
    else:
        donor.display_name = display_name or donor.display_name
        if consent_marketing:  # consent can be granted, never silently revoked here
            donor.consent_marketing = True
            donor.consent_source = consent_source or donor.consent_source
    return donor


# --- Donation creation (request path: NO network) --------------------------- #

def create_donation(db: Session, *, org_id: int, campaign_id: int, amount_minor_units: int,
                    currency: str | None = None, kind: str = "one_time",
                    donor_name: str = "", donor_email: str | None = None,
                    is_anonymous: bool = False, hard_anonymous: bool = False,
                    designation_code: str = "", consent_marketing: bool = False,
                    consent_source: str = "public_donate_form") -> Donation:
    """Create a PENDING donation and enqueue hosted-checkout creation (done off the request path
    by a worker). Never contacts the provider synchronously — INV: no network on request path."""
    campaign = db.get(DonationCampaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise DonationError("campaign not found")
    if campaign.status != CampaignStatus.active or not campaign.is_public:
        raise DonationError("this campaign is not accepting donations")
    now = utcnow()
    if (campaign.starts_at and now < campaign.starts_at) or (campaign.ends_at and now > campaign.ends_at):
        raise DonationError("this campaign is not accepting donations")
    if amount_minor_units <= 0:
        raise DonationError("amount must be positive")
    if kind not in (DonationKind.one_time.value, DonationKind.recurring.value):
        raise DonationError("invalid donation kind")

    donor = _resolve_donor(db, org_id=org_id, hard_anonymous=hard_anonymous,
                           display_name=donor_name, email=donor_email,
                           consent_marketing=consent_marketing, consent_source=consent_source)

    # Note: for kind="recurring" the RecurringDonationPlan is NOT created here — it is activated
    # only when a payment settles (see _mark_succeeded), so metrics never count uncollected plans.
    donation = Donation(
        org_id=org_id, campaign_id=campaign_id, donor_id=donor.id if donor else None,
        amount_minor_units=amount_minor_units, currency=currency or campaign.currency,
        kind=DonationKind(kind), status=DonationStatus.pending, is_anonymous=is_anonymous,
        designation_code=designation_code, recurring_plan_id=None,
        provider=get_payment_provider().name, idempotency_key=secrets.token_hex(24),
        public_token=secrets.token_urlsafe(32))
    db.add(donation)
    db.flush()
    enqueue(db, org_id=org_id, event_type="donation.checkout",
            idempotency_key=f"donation-checkout:{donation.id}",
            payload={"donation_id": donation.id})
    audit.emit(db, org_id=org_id, action="donation.created", target_type="donation",
               target_id=donation.id, meta={"amount_minor_units": amount_minor_units,
                                            "currency": donation.currency, "kind": kind})
    return donation


def public_donation_status(db: Session, *, org_id: int, public_token: str) -> dict | None:
    """Capability-token lookup for the unauthenticated checkout-poll / return page. Returns only
    status + the hosted checkout URL — never donor identity or provider secrets."""
    d = db.scalar(select(Donation).where(Donation.org_id == org_id,
                                         Donation.public_token == public_token))
    if d is None:
        return None
    return {"status": d.status.value, "checkout_url": d.checkout_url,
            "amount_minor_units": d.amount_minor_units, "currency": d.currency}


# --- Webhook reconciliation (provider = source of truth) -------------------- #

def record_webhook_event(db: Session, *, org_id: int, event: ProviderEvent, provider: str) -> str:
    """Idempotently record + reconcile a verified provider event. Returns "applied" | "duplicate"
    | "ignored" | "unmatched". Money state changes ONLY here — INV-WEBHOOK-AUTHORITATIVE."""
    # Dedupe replays on the provider event id (INV: replay-safe). Check-first handles the common
    # replay; the UniqueConstraint is the DB backstop for a true race → IntegrityError bubbles to
    # the route as a 5xx and the provider retries (design §4 rule 4), converging idempotently.
    if db.scalar(select(PaymentEvent).where(
            PaymentEvent.org_id == org_id, PaymentEvent.provider == provider,
            PaymentEvent.provider_event_id == event.id)) is not None:
        return "duplicate"
    pe = PaymentEvent(org_id=org_id, provider=provider, provider_event_id=event.id,
                      event_type=event.type, status="applied", received_at=utcnow(),
                      payload_digest=_digest(event))
    db.add(pe)
    db.flush()

    donation = _match_donation(db, org_id=org_id, event=event)
    if donation is None:
        pe.status = "unmatched"
        db.flush()
        return "unmatched"
    pe.donation_id = donation.id

    if event.type in _SUCCEEDED_EVENTS:
        outcome = _mark_succeeded(db, org_id=org_id, donation=donation, event=event)
    elif event.type in _FAILED_EVENTS:
        # Out-of-order guard: a late/re-delivered failure must not clobber an already-collected
        # donation (its receipt is immutable). Only a still-pending donation can go to failed.
        if donation.status == DonationStatus.pending:
            donation.status = DonationStatus.failed
            outcome = "applied"
        else:
            pe.status = "ignored"
            outcome = "ignored"
    elif event.type in _REFUND_EVENTS:
        # Refunds only apply to money that was actually collected.
        if donation.status in (DonationStatus.succeeded, DonationStatus.partially_refunded):
            _apply_refund(db, donation=donation, event=event)
            outcome = "applied"
        else:
            pe.status = "ignored"
            outcome = "ignored"
    else:
        pe.status = "ignored"
        outcome = "ignored"
    db.flush()
    return outcome


def _digest(event: ProviderEvent) -> dict:
    """Only ids + money metadata — never card data (INV-NO-PAN)."""
    d = event.data or {}
    return {"amount": d.get("amount_total") or d.get("amount"), "currency": d.get("currency"),
            "status": d.get("status"), "charge": d.get("latest_charge") or d.get("charge")}


def _match_donation(db: Session, *, org_id: int, event: ProviderEvent) -> Donation | None:
    d = event.data or {}
    meta = d.get("metadata") or {}
    idem = meta.get("idempotency_key")
    if idem:
        by_idem = db.scalar(select(Donation).where(Donation.org_id == org_id,
                                                   Donation.idempotency_key == idem))
        if by_idem is not None:
            return by_idem
    ref = d.get("client_reference_id") or meta.get("donation_id")
    if ref is not None:
        try:
            dn = db.get(Donation, int(ref))
        except (TypeError, ValueError):
            dn = None
        if dn is not None and dn.org_id == org_id:
            return dn
    intent_id = d.get("id")
    if intent_id:
        return db.scalar(select(Donation).where(Donation.org_id == org_id,
                                               Donation.provider_intent_id == intent_id))
    return None


def _mark_succeeded(db: Session, *, org_id: int, donation: Donation, event: ProviderEvent) -> str:
    if donation.status == DonationStatus.succeeded:
        return "duplicate"  # already reconciled by an earlier event of the same session
    data = event.data or {}
    payment_status = data.get("payment_status")
    if payment_status is not None and payment_status not in _PAID_STATUSES:
        # e.g. checkout.session.completed with payment_status="unpaid" (ACH/SEPA pending) — the
        # money isn't collected yet; wait for async_payment_succeeded before issuing a receipt.
        return "ignored"
    donation.status = DonationStatus.succeeded
    donation.succeeded_at = utcnow()
    charge = data.get("latest_charge") or data.get("charge")
    if charge:
        donation.provider_charge_id = str(charge)
    # A recurring subscription's plan is activated ONLY now that a payment has settled — never on
    # the unauthenticated create path (which would inflate MRR with uncollected $0 plans).
    if donation.kind == DonationKind.recurring and donation.recurring_plan_id is None:
        plan = RecurringDonationPlan(
            org_id=org_id, campaign_id=donation.campaign_id, donor_id=donation.donor_id,
            amount_minor_units=donation.amount_minor_units, currency=donation.currency,
            status=RecurringStatus.active, provider=donation.provider,
            provider_subscription_id=data.get("subscription"))
        db.add(plan)
        db.flush()
        donation.recurring_plan_id = plan.id
    # Receipt + thank-you happen through the outbox (independently retryable) — never inline.
    enqueue(db, org_id=org_id, event_type="donation.succeeded",
            idempotency_key=f"donation-succeeded:{donation.id}",
            payload={"donation_id": donation.id})
    return "applied"


def _apply_refund(db: Session, *, donation: Donation, event: ProviderEvent) -> None:
    refunded = (event.data or {}).get("amount_refunded")
    if refunded is not None:
        donation.refunded_minor_units = int(refunded)
    else:
        donation.refunded_minor_units = donation.amount_minor_units
    donation.status = (DonationStatus.refunded
                       if donation.refunded_minor_units >= donation.amount_minor_units
                       else DonationStatus.partially_refunded)


# --- In-kind ---------------------------------------------------------------- #

def record_in_kind(db: Session, *, org_id: int, description: str, received_at: datetime,
                   campaign_id: int | None = None, donor_name: str = "",
                   donor_email: str | None = None, estimated_value_minor_units: int | None = None,
                   currency: str = "USD", recorded_by_user_id: int | None = None) -> InKindDonation:
    if not description.strip():
        raise DonationError("description is required")
    donor = _resolve_donor(db, org_id=org_id, hard_anonymous=False, display_name=donor_name,
                           email=donor_email, consent_marketing=False, consent_source="in_kind")
    ik = InKindDonation(org_id=org_id, campaign_id=campaign_id,
                        donor_id=donor.id if donor else None, description=description.strip(),
                        estimated_value_minor_units=estimated_value_minor_units, currency=currency,
                        received_at=received_at, recorded_by_user_id=recorded_by_user_id)
    db.add(ik)
    db.flush()
    audit.emit(db, org_id=org_id, action="donation.in_kind_recorded",
               target_type="in_kind_donation", target_id=ik.id)
    return ik


# --- Outbox handlers -------------------------------------------------------- #

@handler("donation.checkout")
def handle_checkout(db: Session, event) -> None:
    """Worker: create the provider-hosted checkout (the only place we call the provider for
    checkout) and store its redirect URL for the browser to poll."""
    donation = db.get(Donation, event.payload["donation_id"])
    if donation is None or donation.checkout_url:
        return  # idempotent — already has a checkout
    campaign = db.get(DonationCampaign, donation.campaign_id)
    donor = db.get(Donor, donation.donor_id) if donation.donor_id else None
    intent = DonationIntent(
        amount_minor_units=donation.amount_minor_units, currency=donation.currency,
        kind=donation.kind.value, donation_id=donation.id,
        idempotency_key=donation.idempotency_key, org_id=donation.org_id,
        campaign_id=donation.campaign_id,
        description=campaign.title if campaign else "Donation",
        customer_email=donor.email if donor else None)
    ref = get_payment_provider().create_checkout(intent)
    donation.provider_intent_id = ref.provider_intent_id
    donation.checkout_url = ref.redirect_url
    db.flush()


@handler("donation.succeeded")
def handle_succeeded(db: Session, event) -> None:
    """Worker: issue the immutable, gapless receipt (once) and enqueue the thank-you email."""
    donation = db.get(Donation, event.payload["donation_id"])
    if donation is None or donation.status != DonationStatus.succeeded:
        return
    existing = db.scalar(select(DonationReceipt).where(
        DonationReceipt.donation_id == donation.id))
    if existing is None:
        _issue_receipt(db, donation=donation)
    donor = db.get(Donor, donation.donor_id) if donation.donor_id else None
    if donor and donor.email:
        queue_email(db, org_id=donation.org_id,
                    idempotency_key=f"donation-thankyou:{donation.id}",
                    to_email=donor.email, template_key="donation_thank_you",
                    context={"amount_minor_units": donation.amount_minor_units,
                             "currency": donation.currency})


def _issue_receipt(db: Session, *, donation: Donation) -> DonationReceipt:
    tax_year = (donation.succeeded_at or utcnow()).year
    # Gapless per (org, tax_year): allocate under a row lock on the counter.
    counter = db.scalar(select(ReceiptCounter).where(
        ReceiptCounter.org_id == donation.org_id,
        ReceiptCounter.tax_year == tax_year).with_for_update())
    if counter is None:
        counter = ReceiptCounter(org_id=donation.org_id, tax_year=tax_year, next_sequence_no=1)
        db.add(counter)
        db.flush()
    seq = counter.next_sequence_no
    counter.next_sequence_no = seq + 1
    donor = db.get(Donor, donation.donor_id) if donation.donor_id else None
    receipt = DonationReceipt(
        org_id=donation.org_id, donation_id=donation.id, tax_year=tax_year, sequence_no=seq,
        receipt_number=f"{tax_year}-{seq:06d}", issued_at=utcnow(),
        snapshot={"amount_minor_units": donation.amount_minor_units, "currency": donation.currency,
                  "donor_name": (donor.display_name if donor and not donation.is_anonymous
                                 else "Anonymous"),
                  "designation_code": donation.designation_code,
                  "date": (donation.succeeded_at or utcnow()).isoformat()})
    db.add(receipt)
    db.flush()
    audit.emit(db, org_id=donation.org_id, action="donation.receipt_issued",
               target_type="donation_receipt", target_id=receipt.id,
               meta={"receipt_number": receipt.receipt_number})
    return receipt


# --- Reporting & export ----------------------------------------------------- #

def donation_metrics(db: Session, *, org_id: int) -> dict:
    succeeded = select(Donation).where(Donation.org_id == org_id,
                                       Donation.status == DonationStatus.succeeded).subquery()
    volume = db.scalar(select(func.coalesce(func.sum(succeeded.c.amount_minor_units), 0))) or 0
    count = db.scalar(select(func.count()).select_from(succeeded)) or 0
    donor_count = db.scalar(select(func.count(func.distinct(succeeded.c.donor_id)))
                            .where(succeeded.c.donor_id.isnot(None))) or 0
    refunded = db.scalar(select(func.coalesce(func.sum(Donation.refunded_minor_units), 0))
                         .where(Donation.org_id == org_id)) or 0
    active_recurring = db.scalar(select(func.count()).select_from(RecurringDonationPlan).where(
        RecurringDonationPlan.org_id == org_id,
        RecurringDonationPlan.status == RecurringStatus.active)) or 0
    mrr = db.scalar(select(func.coalesce(func.sum(RecurringDonationPlan.amount_minor_units), 0))
                    .where(RecurringDonationPlan.org_id == org_id,
                           RecurringDonationPlan.status == RecurringStatus.active)) or 0
    return {
        "volume_minor_units": int(volume), "donation_count": int(count),
        "donor_count": int(donor_count),
        "average_minor_units": int(volume // count) if count else 0,
        "refunded_minor_units": int(refunded),
        "active_recurring_plans": int(active_recurring), "recurring_mrr_minor_units": int(mrr),
    }


def export_rows(db: Session, *, org_id: int) -> str:
    """Accounting CSV: one row per money event, ids + money metadata only — no card data."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "type", "amount_minor_units", "currency", "campaign_slug",
                "designation", "receipt_number", "donor_reference", "status"])
    rows = db.execute(
        select(Donation, DonationCampaign.slug, DonationReceipt.receipt_number)
        .join(DonationCampaign, DonationCampaign.id == Donation.campaign_id)
        .join(DonationReceipt, DonationReceipt.donation_id == Donation.id, isouter=True)
        .where(Donation.org_id == org_id,
               Donation.status.in_([DonationStatus.succeeded, DonationStatus.refunded,
                                    DonationStatus.partially_refunded]))
        .order_by(Donation.succeeded_at)).all()
    for d, slug, receipt_number in rows:
        w.writerow([(d.succeeded_at or d.created_at).date().isoformat(), "donation",
                    d.amount_minor_units, d.currency, slug, d.designation_code,
                    receipt_number or "", f"donor#{d.donor_id}" if d.donor_id else "anonymous",
                    d.status.value])
    return buf.getvalue()
