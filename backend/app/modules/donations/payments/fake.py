"""FakePaymentProvider — the default adapter for dev/tests/CI (no network, no keys).

It fabricates a deterministic hosted-checkout ref and can mint verified events the same way a
provider webhook would, so the whole donate→webhook→receipt path is exercisable without Stripe.
It NEVER handles card data (there is none) — INV-NO-PAN holds trivially.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from .port import CheckoutRef, DonationIntent, ProviderEvent, WebhookVerificationError

# A fixed dev secret so tests can sign a fake webhook exactly as the provider would.
FAKE_WEBHOOK_SECRET = "fake-webhook-secret"


def _sign(payload: bytes) -> str:
    return hmac.new(FAKE_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()


class FakePaymentProvider:
    name = "fake"

    def create_checkout(self, intent: DonationIntent) -> CheckoutRef:
        # Deterministic on our idempotency key — a retry returns the same "session".
        sid = f"fake_cs_{intent.idempotency_key}"
        return CheckoutRef(provider_intent_id=sid,
                           redirect_url=f"{intent.success_url or '/donate/return'}?session_id={sid}")

    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent:
        expected = _sign(payload)
        if not signature or not hmac.compare_digest(expected, signature):
            raise WebhookVerificationError("bad fake signature")
        body = json.loads(payload.decode())
        return ProviderEvent(id=body["id"], type=body["type"], data=body.get("data", {}))

    # --- test helper: build a signed event body the way the provider would deliver it --- #
    @staticmethod
    def make_signed_event(event_id: str, event_type: str, data: dict) -> tuple[bytes, str]:
        payload = json.dumps({"id": event_id, "type": event_type, "data": data}).encode()
        return payload, _sign(payload)
