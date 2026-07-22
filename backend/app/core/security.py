"""Password hashing and single-use token generation/verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def generate_token() -> str:
    """A high-entropy opaque token to email to a person (the plaintext is never stored)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Store only a keyed hash of a token, so a DB leak doesn't yield usable links."""
    return hmac.new(settings.app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
