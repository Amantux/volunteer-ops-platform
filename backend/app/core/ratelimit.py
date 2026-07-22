"""Rate limiting for public forms (bot/abuse control).

Two backends: an in-process limiter (single node / dev / tests) and a Redis-backed one
(multi-node / production). Selected by ``settings.ratelimit_backend``. Both share the
``allow(key, limit, window_seconds)`` interface used by the public routes.
"""

from __future__ import annotations

import time
from collections import defaultdict

from .config import settings

_hits: dict[str, list[float]] = defaultdict(list)
_redis = None


def _memory_allow(key: str, *, limit: int, window_seconds: int) -> bool:
    now = time.time()
    recent = [t for t in _hits[key] if now - t < window_seconds]
    recent.append(now)
    _hits[key] = recent
    return len(recent) <= limit


def _redis_client():
    global _redis
    if _redis is None:
        import redis  # provided by celery[redis]

        _redis = redis.Redis.from_url(settings.redis_url)
    return _redis


def _redis_allow(key: str, *, limit: int, window_seconds: int) -> bool:
    client = _redis_client()
    redis_key = f"rl:{key}:{int(time.time() // window_seconds)}"
    count = client.incr(redis_key)
    if count == 1:
        client.expire(redis_key, window_seconds)
    return int(count) <= limit


def allow(key: str, *, limit: int, window_seconds: int) -> bool:
    """Return True if the action is allowed; False if the key exceeded the limit."""
    if settings.ratelimit_backend == "redis":
        try:
            return _redis_allow(key, limit=limit, window_seconds=window_seconds)
        except Exception:  # noqa: BLE001 - if Redis is down, fail open to a local limit
            return _memory_allow(key, limit=limit, window_seconds=window_seconds)
    return _memory_allow(key, limit=limit, window_seconds=window_seconds)


# Backwards-compatible alias.
def check(key: str, *, limit: int, window_seconds: int) -> bool:
    return allow(key, limit=limit, window_seconds=window_seconds)
