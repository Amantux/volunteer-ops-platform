"""Chat assistant: config resolution + admin gating + governance (read-only, permission-scoped
tools, no key leakage). The provider network calls are not exercised here."""

from __future__ import annotations

from sqlalchemy import select

from app.core.authz import Principal
from app.core.session import make_session_token
from app.modules.agents import assistant
from app.modules.identity.models import Person, Role, User, UserRoleAssignment


def _user_with_role(db, org, email, role_key):
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    role = db.scalar(select(Role).where(Role.org_id == org.id, Role.key == role_key))
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return user, {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


def test_config_override_wins_and_key_is_never_returned(db, org):
    assistant.set_org_config(db, org.id, {"provider": "ollama",
                                          "base_url": "http://host.docker.internal:11434",
                                          "model": "llama3.1", "api_key": "secret-key"})
    db.commit()
    cfg = assistant.resolve_config(db, org.id)
    assert cfg.provider == "ollama" and cfg.model == "llama3.1" and cfg.enabled
    pub = assistant.public_config(cfg)
    assert pub["has_api_key"] is True and "api_key" not in pub and "secret" not in str(pub)


def test_blank_api_key_does_not_clobber_stored_one(db, org):
    assistant.set_org_config(db, org.id, {"provider": "ollama", "api_key": "keep-me"})
    assistant.set_org_config(db, org.id, {"model": "llama3.1", "api_key": ""})
    db.commit()
    assert assistant.resolve_config(db, org.id).api_key == "keep-me"


def test_tools_are_filtered_to_caller_permissions(db, org, admin_user):
    admin = Principal(user_id=admin_user.id, org_id=org.id)
    admin_tools = assistant._available_tools(db, admin)
    assert "get_donation_metrics" in admin_tools  # org_admin holds donation.view
    vol_user, _ = _user_with_role(db, org, "vol@x.org", "volunteer")
    vol = Principal(user_id=vol_user.id, org_id=org.id)
    vol_tools = assistant._available_tools(db, vol)
    assert "get_donation_metrics" not in vol_tools  # volunteer must not see finance tools
    assert "my_upcoming_shifts" in vol_tools        # but does get their own shifts


def test_chat_returns_setup_message_when_disabled(db, org, admin_user):
    principal = Principal(user_id=admin_user.id, org_id=org.id)
    res = assistant.run_chat(db, principal, [{"role": "user", "content": "hi"}])
    assert res.provider == "off" and "configure" in res.reply.lower() and res.actions == []


def test_chat_endpoint_requires_auth(client):
    assert client.post("/api/agent/chat", json={"messages": []}).status_code == 401


def test_admin_settings_require_permission(db, org, client):
    _, vol_headers = _user_with_role(db, org, "vol2@x.org", "volunteer")
    assert client.get("/api/admin/agent-settings", headers=vol_headers).status_code == 403


def test_admin_can_configure_and_key_not_echoed(db, org, client, admin_headers):
    r = client.put("/api/admin/agent-settings", headers=admin_headers, json={
        "provider": "ollama", "base_url": "http://host.docker.internal:11434",
        "model": "llama3.1", "api_key": "topsecret"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "ollama" and body["has_api_key"] is True
    assert "topsecret" not in r.text


def test_openai_style_provider_is_accepted(db, org, client, admin_headers):
    r = client.put("/api/admin/agent-settings", headers=admin_headers, json={
        "provider": "openai", "base_url": "https://openrouter.ai/api/v1",
        "model": "gpt-4o-mini", "api_key": "sk-test"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai" and body["has_api_key"] is True
    assert "sk-test" not in r.text


def test_ssrf_guard_rejects_metadata_and_bad_scheme(db, org, client, admin_headers):
    bad = client.put("/api/admin/agent-settings", headers=admin_headers,
                     json={"base_url": "http://169.254.169.254"})
    assert bad.status_code == 400
    bad2 = client.put("/api/admin/agent-settings", headers=admin_headers,
                      json={"base_url": "file:///etc/passwd"})
    assert bad2.status_code == 400
