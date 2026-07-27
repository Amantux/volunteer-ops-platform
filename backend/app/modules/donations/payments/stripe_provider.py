"""StripePaymentProvider — Stripe Checkout (hosted), test mode by default.

Implemented against Stripe's REST API over stdlib ``urllib`` and its webhook signature scheme via
stdlib ``hmac`` — NO ``stripe`` SDK dependency, so CI builds/tests without the package or network.
Live mode is a config switch (a live ``stripe_secret_key``), not new code. Card entry happens on
Stripe's hosted page; this adapter only ever sees ids + money metadata (INV-NO-PAN).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
import urllib.request

from .port import CheckoutRef, DonationIntent, ProviderEvent, WebhookVerificationError

_API_BASE = "https://api.stripe.com/v1"
_SIGNATURE_TOLERANCE_SECONDS = 300  # 5-minute replay window (design §4 rule 1)


class StripePaymentProvider:
    name = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret

    def create_checkout(self, intent: DonationIntent) -> CheckoutRef:
        # Stripe Checkout Session (hosted). We pass our idempotency key as the HTTP idempotency
        # header AND as metadata so the webhook can correlate back to our Donation.
        mode = "subscription" if intent.kind == "recurring" else "payment"
        form: list[tuple[str, str]] = [
            ("mode", mode),
            ("success_url", intent.success_url or "/donate/return?session_id={CHECKOUT_SESSION_ID}"),
            ("cancel_url", intent.cancel_url or "/donate/cancelled"),
            ("client_reference_id", str(intent.donation_id)),
            ("line_items[0][quantity]", "1"),
            ("line_items[0][price_data][currency]", intent.currency.lower()),
            ("line_items[0][price_data][unit_amount]", str(intent.amount_minor_units)),
            ("line_items[0][price_data][product_data][name]",
             intent.description or "Donation"),
            ("metadata[donation_id]", str(intent.donation_id)),
            ("metadata[idempotency_key]", intent.idempotency_key),
            ("metadata[org_id]", str(intent.org_id)),
        ]
        if intent.customer_email:
            form.append(("customer_email", intent.customer_email))
        if mode == "subscription":
            form.append(("line_items[0][price_data][recurring][interval]", "month"))
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(
            f"{_API_BASE}/checkout/sessions", data=data,
            headers={
                "Authorization": f"Bearer {self._secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Idempotency-Key": intent.idempotency_key,
            }, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310  # nosec B310
            body = json.loads(resp.read().decode())
        return CheckoutRef(provider_intent_id=body["id"], redirect_url=body["url"])

    def verify_webhook(self, payload: bytes, signature: str) -> ProviderEvent:
        # Stripe-Signature: "t=<ts>,v1=<hex>[,v1=<hex>...]". Verify HMAC over "<t>.<payload>"
        # against the raw body BEFORE parsing (design §4 rule 1). See Stripe's signing scheme.
        if not signature:
            raise WebhookVerificationError("missing signature")
        parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
        timestamp = parts.get("t")
        candidates = [v for k, v in (p.split("=", 1) for p in signature.split(",") if "=" in p)
                      if k == "v1"]
        if not timestamp or not candidates:
            raise WebhookVerificationError("malformed signature header")
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(self._webhook_secret.encode(), signed_payload,
                            hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, c) for c in candidates):
            raise WebhookVerificationError("signature mismatch")
        self._assert_fresh(timestamp)
        body = json.loads(payload.decode())
        return ProviderEvent(id=body["id"], type=body["type"],
                             data=body.get("data", {}).get("object", body.get("data", {})))

    @staticmethod
    def _assert_fresh(timestamp: str) -> None:
        from app.core.db import utcnow
        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise WebhookVerificationError("bad timestamp") from exc
        now = int(utcnow().timestamp())
        if abs(now - ts) > _SIGNATURE_TOLERANCE_SECONDS:
            raise WebhookVerificationError("timestamp outside tolerance (replay?)")
