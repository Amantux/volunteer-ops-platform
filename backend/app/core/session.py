"""Stateless signed session tokens (HMAC) for authenticated API calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from .config import settings

_TTL_SECONDS = 60 * 60 * 12  # 12h sessions


def _sign(payload: str) -> str:
    return hmac.new(settings.app_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(*, user_id: int, org_id: int) -> str:
    payload = f"{user_id}:{org_id}:{int(time.time()) + _TTL_SECONDS}"
    body = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{body}.{_sign(payload)}"


def read_session_token(token: str) -> tuple[int, int] | None:
    """Return (user_id, org_id) if the token is valid and unexpired, else None."""
    try:
        body, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(body.encode()).decode()
        user_id, org_id, exp = payload.split(":")
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    if int(exp) < int(time.time()):
        return None
    return int(user_id), int(org_id)
