"""Payment-provider port (INV-NO-PAN boundary).

The donations domain depends ONLY on this Protocol — it never imports Stripe, never sees card
data, and never makes a network call on the request path (outbound calls run in workers, driven
by the outbox). Card entry always happens on the provider's hosted surface, so no PAN/CVV/expiry
ever reaches this process. See docs/architecture/donations-design.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class DonationIntent:
    """What we ask the provider to collect — money metadata + our correlation ids only."""

    amount_minor_units: int
    currency: str
    kind: str  # "one_time" | "recurring"
    donation_id: int
    idempotency_key: str
    org_id: int
    campaign_id: int
    description: str = ""
    success_url: str = ""
    cancel_url: str = ""
    customer_email: str | None = None  # provider receipt only; never persisted as card data
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutRef:
    """The provider-hosted checkout to redirect the donor to."""

    provider_intent_id: str  # checkout session / payment intent id
    redirect_url: str


@dataclass(frozen=True)
class ProviderEvent:
    """A signature-verified webhook event, already parsed to money metadata + ids only.

    ``data`` carries NO card data — only ids, amounts, currency, status (INV-NO-PAN)."""

    id: str  # provider event id — dedupe key (INV: replay-safe)
    type: str  # e.g. "checkout.session.completed", "charge.refunded"
    data: dict


class WebhookVerificationError(Exception):
    """Raised when a webhook signature/timestamp fails — treat as an attack signal, return 401."""


class PaymentProvider(Protocol):
    name: str

    def create_checkout(self, intent: DonationIntent) -> CheckoutRef:
        """Create a provider-HOSTED checkout for ``intent`` and return its redirect URL.
        Card entry happens on the provider surface (INV-NO-PAN). Idempotent on
        ``intent.idempotency_key``."""
        ...

    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent:
        """Verify the signature + timestamp window over the RAW body BEFORE any parsing.
        Raise ``WebhookVerificationError`` on failure. Returns a typed ``ProviderEvent``."""
        ...
