"""Publish targets abstraction. Default is the manual/dev publisher (no external effect →
retry-safe). Real platform adapters (X/Meta/LinkedIn/Mastodon) are deferred behind this port.

LLM drafting reuses the shared provider in `app.modules.content.llm` (dev stub by default,
Anthropic when configured) — assist only.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.core.config import settings

if TYPE_CHECKING:
    from .models import SocialChannel, SocialPost


@dataclass
class PublishResult:
    ok: bool
    external_ref: str = ""
    error: str = ""


class SocialPublisher(Protocol):
    def publish(self, *, post: SocialPost, channel: SocialChannel,
                idempotency_key: str) -> PublishResult: ...


class ManualPublisher:
    """Dev/default: records the post as published with a synthetic reference and NO external
    side-effect, so retries are always safe. The copy is exported for a human to post by hand."""

    name = "manual"

    def publish(self, *, post: SocialPost, channel: SocialChannel,
                idempotency_key: str) -> PublishResult:
        return PublishResult(ok=True, external_ref=f"manual:{post.id}:{channel.handle}")


class WebhookPublisher:
    """POST the post to an outgoing webhook (Zapier/Make/self-hosted). Carries the idempotency
    key so the receiver can dedupe — retries must not double-post downstream."""

    name = "webhook"

    def publish(self, *, post: SocialPost, channel: SocialChannel,
                idempotency_key: str) -> PublishResult:
        if not settings.social_webhook_url:
            return PublishResult(ok=False, error="social_webhook_url not configured")
        # Only ever POST over http(s) — guard against a misconfigured file://custom-scheme URL.
        if not settings.social_webhook_url.startswith(("http://", "https://")):
            return PublishResult(ok=False, error="social_webhook_url must be http(s)")
        payload = json.dumps({
            "idempotency_key": idempotency_key,
            "platform": channel.platform.value,
            "handle": channel.handle,
            "body": post.body,
            "post_id": post.id,
        }).encode()
        req = urllib.request.Request(
            settings.social_webhook_url, data=payload,
            headers={"Content-Type": "application/json",
                     "Idempotency-Key": idempotency_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  # nosec B310
                ok = 200 <= resp.status < 300
                return PublishResult(ok=ok, external_ref=f"webhook:{idempotency_key}",
                                     error="" if ok else f"webhook returned {resp.status}")
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed target for retry
            return PublishResult(ok=False, error=str(exc)[:500])


def get_publisher() -> SocialPublisher:
    if settings.social_publisher == "webhook":
        return WebhookPublisher()
    return ManualPublisher()
