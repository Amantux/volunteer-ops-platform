"""Social media: the safety matrix — no autopublish, no double-post, MCP can draft not publish."""

from __future__ import annotations

from conftest import relay
from sqlalchemy import func, select

from app.core.outbox import OutboxEvent
from app.modules.agents.risk import RiskLevel, classify_action
from app.modules.social.models import SocialPost, SocialPublishTarget, TargetStatus


def _channel(client, admin_headers, handle="@vol", char_limit=280):
    return client.post("/api/social/channels", headers=admin_headers,
                       json={"platform": "manual", "handle": handle,
                             "char_limit": char_limit}).json()["id"]


def _draft(client, admin_headers, cid, body="Come volunteer with us this weekend!"):
    return client.post("/api/social/posts", headers=admin_headers,
                       json={"body": body, "channel_ids": [cid]}).json()["id"]


def _social_events(db):
    return db.scalar(select(func.count()).select_from(OutboxEvent).where(
        OutboxEvent.event_type == "social.publish")) or 0


def _user_with_perms(db, org, perms, email):
    from app.core.session import make_session_token
    from app.modules.identity.models import (
        Person,
        Role,
        RolePermission,
        User,
        UserRoleAssignment,
    )
    role = Role(org_id=org.id, key=f"role_{email}", label="Test")
    db.add(role)
    db.flush()
    for p in perms:
        db.add(RolePermission(role_id=role.id, permission=p))
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


def test_publish_refused_without_approval(client, db, admin_headers):
    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    # A draft cannot be published — no approval yet.
    r = client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    assert r.status_code == 409 and "approved" in r.json()["detail"].lower()
    assert _social_events(db) == 0  # nothing was ever enqueued
    post = db.get(SocialPost, pid)
    assert post.status.value == "draft" and post.approved_by_user_id is None


def test_full_lifecycle_publishes_once(client, db, admin_headers):
    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    assert client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers).status_code == 200
    assert client.post(f"/api/social/posts/{pid}/approve", headers=admin_headers).status_code == 200
    assert client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers).status_code == 200

    # The publish happens via the outbox (like email), not synchronously.
    relay(db)
    targets = db.scalars(select(SocialPublishTarget).where(
        SocialPublishTarget.post_id == pid)).all()
    assert len(targets) == 1 and targets[0].status == TargetStatus.published
    assert targets[0].external_ref.startswith("manual:")
    assert db.get(SocialPost, pid).status.value == "published"


def test_no_double_post_on_repeat(client, db, admin_headers):
    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers)
    client.post(f"/api/social/posts/{pid}/approve", headers=admin_headers)
    client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    # Relaying twice must not publish the same channel twice.
    relay(db)
    relay(db)
    published = db.scalar(select(func.count()).select_from(SocialPublishTarget).where(
        SocialPublishTarget.post_id == pid, SocialPublishTarget.status == TargetStatus.published))
    assert published == 1
    # A second publish call on an already-published post is refused.
    assert client.post(f"/api/social/posts/{pid}/publish",
                       headers=admin_headers).status_code == 409


def test_char_limit_enforced_at_submit(client, admin_headers):
    cid = _channel(client, admin_headers, handle="@short", char_limit=10)
    pid = _draft(client, admin_headers, cid, body="this body is way over ten characters")
    r = client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers)
    assert r.status_code == 409 and "chars" in r.json()["detail"].lower()


def test_mcp_can_draft_but_never_publish(client, db, org, admin_user):
    from app.core.authz import Principal
    from app.mcp import tools

    principal = Principal(user_id=admin_user.id, org_id=org.id)
    result = tools.invoke_tool(db, principal, "draft_social_post",
                               {"prompt": "a thank-you to our weekend volunteers"})
    post = db.get(SocialPost, result["post_id"])
    assert post.source.value == "llm_assisted" and post.agent_proposal_id is not None
    assert post.status.value == "draft"  # a draft — never published

    # There is NO publish tool exposed via MCP, and social.publish is a prohibited (R4) action.
    names = {c.name for c in tools.contracts()}
    assert "draft_social_post" in names
    assert not any("publish" in n for n in names)
    assert classify_action("social.publish") == RiskLevel.r4_prohibited


def test_partial_failure_then_retry(client, db, admin_headers, monkeypatch):
    from app.modules.social import service
    from app.modules.social.providers import PublishResult

    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers)
    client.post(f"/api/social/posts/{pid}/approve", headers=admin_headers)

    class Failing:
        def publish(self, **kw):
            return PublishResult(ok=False, error="downstream 503")

    monkeypatch.setattr(service, "get_publisher", lambda: Failing())
    client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    relay(db)
    target = db.scalar(select(SocialPublishTarget).where(SocialPublishTarget.post_id == pid))
    assert target.status == TargetStatus.failed and db.get(SocialPost, pid).status.value == "failed"

    # Fix the provider and re-publish — the failed target retries and succeeds (no duplicate).
    monkeypatch.undo()
    assert client.post(f"/api/social/posts/{pid}/publish",
                       headers=admin_headers).status_code == 200
    relay(db)
    db.expire_all()
    target = db.scalar(select(SocialPublishTarget).where(SocialPublishTarget.post_id == pid))
    assert target.status == TargetStatus.published and target.attempts == 2


def test_downstream_idempotency_key_is_stable_across_retries(client, db, admin_headers,
                                                             monkeypatch):
    """The key sent to the external publisher must NOT change on retry, or the receiver can't
    dedupe an ambiguous failure (e.g. a timeout it actually processed) → double post."""
    from app.modules.social import service
    from app.modules.social.providers import PublishResult

    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers)
    client.post(f"/api/social/posts/{pid}/approve", headers=admin_headers)

    keys: list[str] = []

    class Recorder:
        def __init__(self, ok):
            self.ok = ok

        def publish(self, *, post, channel, idempotency_key):
            keys.append(idempotency_key)
            return PublishResult(ok=self.ok, external_ref="ok" if self.ok else "",
                                 error="" if self.ok else "timeout")

    monkeypatch.setattr(service, "get_publisher", lambda: Recorder(False))
    client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    relay(db)
    monkeypatch.setattr(service, "get_publisher", lambda: Recorder(True))
    client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    relay(db)

    assert len(keys) == 2 and keys[0] == keys[1]  # stable across the retry
    assert ":a" not in keys[0]  # no attempt suffix in the downstream key


def test_schedule_requires_publish_permission(client, db, org):
    from datetime import timedelta

    from app.core.db import utcnow
    # A user who can manage + approve but NOT publish.
    headers = _user_with_perms(db, org, ["social.draft", "social.manage", "social.approve"],
                               "sched@x.org")
    cid = _channel(client, headers)
    pid = _draft(client, headers, cid)
    client.post(f"/api/social/posts/{pid}/submit", headers=headers)
    client.post(f"/api/social/posts/{pid}/approve", headers=headers)
    when = (utcnow() + timedelta(hours=1)).isoformat()
    r = client.post(f"/api/social/posts/{pid}/schedule", headers=headers,
                    json={"scheduled_at": when})
    assert r.status_code == 403  # scheduling commits to an unattended publish


def test_disabled_channel_is_not_published(client, db, admin_headers):
    from app.modules.social.models import SocialChannel

    cid = _channel(client, admin_headers)
    pid = _draft(client, admin_headers, cid)
    client.post(f"/api/social/posts/{pid}/submit", headers=admin_headers)
    client.post(f"/api/social/posts/{pid}/approve", headers=admin_headers)
    ch = db.get(SocialChannel, cid)
    ch.enabled = False
    db.commit()
    client.post(f"/api/social/posts/{pid}/publish", headers=admin_headers)
    relay(db)
    db.expire_all()
    target = db.scalar(select(SocialPublishTarget).where(SocialPublishTarget.post_id == pid))
    assert target.status == TargetStatus.failed and "disabled" in target.error
