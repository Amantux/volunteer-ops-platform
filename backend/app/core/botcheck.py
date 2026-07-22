"""Bot / abuse control for public forms.

Pluggable provider: "none" (dev — always passes) or "turnstile" (Cloudflare Turnstile).
The public registration route calls ``verify()``; when a real provider is configured it
requires and validates a client-supplied token.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

from .config import settings

_TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def is_enabled() -> bool:
    return settings.botcheck_provider == "turnstile" and bool(settings.turnstile_secret)


def verify(token: str | None, *, remote_ip: str | None = None) -> bool:
    """Return True if the submission passes the bot check (or checking is disabled)."""
    if not is_enabled():
        return True
    if not token:
        return False
    data = {"secret": settings.turnstile_secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        req = urllib.request.Request(
            _TURNSTILE_URL, data=urllib.parse.urlencode(data).encode(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https URL
            import json

            return bool(json.loads(resp.read()).get("success"))
    except Exception:  # noqa: BLE001 - on provider error, reject (fail closed for bot control)
        return False
