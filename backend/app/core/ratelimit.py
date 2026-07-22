"""Minimal in-process rate limiter for public forms (bot/abuse control).

This is a first-line control for the single-node slice. Production replaces it with a
Redis-backed limiter + a CAPTCHA/turnstile check on public forms (see threat-model.md).
"""

from __future__ import annotations

import time
from collections import defaultdict

_hits: dict[str, list[float]] = defaultdict(list)


def check(key: str, *, limit: int, window_seconds: int) -> bool:
    """Return True if the action is allowed; False if the key exceeded the limit."""
    now = time.time()
    recent = [t for t in _hits[key] if now - t < window_seconds]
    recent.append(now)
    _hits[key] = recent
    return len(recent) <= limit
