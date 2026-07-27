"""Adapter selection. Fake is the default (dev/tests/CI, no keys); Stripe test/live mode is a
config switch. The domain resolves the provider through here — never instantiates one inline.
"""

from __future__ import annotations

from app.core.config import settings

from .fake import FakePaymentProvider
from .port import PaymentProvider
from .stripe_provider import StripePaymentProvider


def get_payment_provider() -> PaymentProvider:
    if settings.payment_provider == "stripe" and settings.stripe_secret_key:
        return StripePaymentProvider(settings.stripe_secret_key, settings.stripe_webhook_secret)
    return FakePaymentProvider()


def webhook_secret() -> str:
    """The secret the current provider signs webhooks with (used only by the webhook route).

    Single global secret — correct for this single-tenant-per-instance deployment. A multi-org
    host would need a per-org STRIPE_WEBHOOK_SECRET resolved from IntegrationConfiguration before
    trusting a signature; wire that in with the multi-tenant host/slug resolution, not before."""
    if settings.payment_provider == "stripe" and settings.stripe_secret_key:
        return settings.stripe_webhook_secret
    from .fake import FAKE_WEBHOOK_SECRET
    return FAKE_WEBHOOK_SECRET
