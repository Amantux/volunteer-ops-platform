"""Donations domain models (org-scoped, Confidential; donor identity kept separate from the
volunteer ``Person`` — INV-DONOR-SEPARATION). Money is always integer minor units + ISO-4217
currency, never a float. No card/PAN/token data appears on any column — INV-NO-PAN; provider
linkage is ids + money metadata only. See docs/architecture/donations-design.md §3.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    closed = "closed"
    archived = "archived"


class DonationKind(str, enum.Enum):
    one_time = "one_time"
    recurring = "recurring"


class DonationStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    refunded = "refunded"
    partially_refunded = "partially_refunded"
    failed = "failed"


class RecurringStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"


class DonationCampaign(Base, TimestampMixin):
    __tablename__ = "donation_campaign"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_campaign_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    goal_minor_units: Mapped[int | None] = mapped_column(Integer)  # None = open-ended
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # Explicit type name: the default (class-name-derived) "campaignstatus" collides with the
    # email CampaignStatus enum's Postgres type, which has different labels.
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="donation_campaign_status"),
        default=CampaignStatus.draft, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    publish_progress: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column()
    ends_at: Mapped[datetime | None] = mapped_column()
    designations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggested_amounts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class Donor(Base, TimestampMixin):
    """Donor financial identity — module-owned, distinct from volunteer ``Person``. ``person_id``
    is an OPTIONAL, consent-gated pointer, never required and never traversed by volunteer code."""

    __tablename__ = "donor"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_donor_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="Anonymous", nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))  # Confidential; redacted in logs
    phone: Mapped[str | None] = mapped_column(String(40))
    postal_address: Mapped[dict | None] = mapped_column(JSON)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))  # consented link only
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    is_anonymous_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RecurringDonationPlan(Base, TimestampMixin):
    __tablename__ = "recurring_donation_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("donation_campaign.id"), nullable=False)
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donor.id"))
    amount_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    interval: Mapped[str] = mapped_column(String(20), default="month", nullable=False)
    status: Mapped[RecurringStatus] = mapped_column(default=RecurringStatus.active, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120))


class Donation(Base, TimestampMixin):
    """One gift + money lifecycle. pending→succeeded is driven ONLY by a verified webhook
    (INV-WEBHOOK-AUTHORITATIVE). Provider columns carry ids/metadata only — INV-NO-PAN."""

    __tablename__ = "donation"
    __table_args__ = (
        UniqueConstraint("org_id", "idempotency_key", name="uq_donation_idem"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("donation_campaign.id"), nullable=False, index=True)
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donor.id"))  # None = hard-anonymous
    amount_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)  # never float
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    kind: Mapped[DonationKind] = mapped_column(default=DonationKind.one_time, nullable=False)
    status: Mapped[DonationStatus] = mapped_column(default=DonationStatus.pending, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    designation_code: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    recurring_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_donation_plan.id"))
    # --- provider linkage (ids/metadata ONLY — INV-NO-PAN) ---
    provider: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    provider_intent_id: Mapped[str | None] = mapped_column(String(120))
    provider_charge_id: Mapped[str | None] = mapped_column(String(120))
    # Hosted-checkout redirect, populated by the worker (create_checkout runs off the request
    # path — no network call while serving a request). The browser polls until this is set.
    checkout_url: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # Unguessable capability for the unauthenticated checkout-poll / return page (avoids IDOR on
    # the sequential donation id). Never sent to the provider; never exposes donor data.
    public_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    refunded_minor_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded_at: Mapped[datetime | None] = mapped_column()  # set only by webhook reconcile


class InKindDonation(Base, TimestampMixin):
    """Non-cash gift — no payment flow, recorded by staff."""

    __tablename__ = "in_kind_donation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("donation_campaign.id"))
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("donor.id"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    estimated_value_minor_units: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class DonationReceipt(Base, TimestampMixin):
    """Immutable, per-(org, tax_year) gapless-numbered receipt. Never UPDATEd after issue —
    a correction is a new receipt. ``snapshot`` freezes the facts at issue time."""

    __tablename__ = "donation_receipt"
    __table_args__ = (
        UniqueConstraint("org_id", "tax_year", "sequence_no", name="uq_receipt_sequence"),
        UniqueConstraint("donation_id", name="uq_receipt_donation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    donation_id: Mapped[int | None] = mapped_column(ForeignKey("donation.id"))
    in_kind_donation_id: Mapped[int | None] = mapped_column(ForeignKey("in_kind_donation.id"))
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ReceiptCounter(Base, TimestampMixin):
    """Per-(org, tax_year) counter for gapless receipt numbering. Allocated under a row lock
    inside the receipt-issuing transaction so there are no gaps and no reuse."""

    __tablename__ = "receipt_counter"
    __table_args__ = (UniqueConstraint("org_id", "tax_year", name="uq_receipt_counter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    next_sequence_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PaymentEvent(Base, TimestampMixin):
    """Verified-webhook ledger + reconciliation source of truth. Append-only; deduped on the
    provider event id (INV: replay-safe). ``payload_digest`` holds ids/money metadata only."""

    __tablename__ = "payment_event"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", "provider_event_id", name="uq_payment_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    donation_id: Mapped[int | None] = mapped_column(ForeignKey("donation.id"))
    status: Mapped[str] = mapped_column(String(30), default="applied", nullable=False)
    payload_digest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False)
