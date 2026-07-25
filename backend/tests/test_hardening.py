"""Production hardening: startup guardrails, security headers, and session revocation."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.production import assert_production_ready
from app.modules.identity.models import User


def _good_prod(**over) -> Settings:
    base = dict(environment="prod", app_secret="a" * 40, ratelimit_backend="redis",
                botcheck_provider="turnstile", public_base_url="https://vol.example.org",
                email_provider="smtp")
    base.update(over)
    return Settings(**base)


def test_production_guard_passes_on_good_config():
    assert_production_ready(_good_prod())  # should not raise


def test_production_guard_ignored_outside_production():
    # A dev environment with insecure settings is fine — the guard only bites staging/prod.
    assert_production_ready(Settings(environment="dev", app_secret="dev-secret-change-me"))


@pytest.mark.parametrize("bad", [
    {"app_secret": "dev-secret-change-me"},
    {"app_secret": "short"},
    {"ratelimit_backend": "memory"},
    {"botcheck_provider": "none"},
    {"public_base_url": "http://vol.example.org"},
    {"email_provider": "inbox"},
])
def test_production_guard_trips_on_each_insecure_setting(bad):
    with pytest.raises(RuntimeError):
        assert_production_ready(_good_prod(**bad))


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert "referrer-policy" in r.headers


def test_logout_revokes_the_session(client, admin_headers):
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200
    assert client.post("/api/auth/logout", headers=admin_headers).status_code == 200
    # The same token is now invalid — session_version was bumped.
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401


def test_forced_revocation_invalidates_existing_tokens(client, db, admin_user, admin_headers):
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200
    user = db.get(User, admin_user.id)
    user.session_version += 1  # e.g. an admin force-signs-out a compromised account
    db.commit()
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401


def test_inactive_user_token_rejected(client, db, admin_user, admin_headers):
    user = db.get(User, admin_user.id)
    user.is_active = False
    db.commit()
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 401
