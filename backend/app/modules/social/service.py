"""Social post lifecycle + publishing. The safety-critical module.

Hard rules (do not weaken):
- NO auto-publish. `publish_post` is the ONLY thing that can enqueue a `social.publish` event,
  and it asserts the post is approved (approved_by_user_id set) first. There is no threshold /
  auto path (unlike email campaigns).
- Per-target idempotency key `social:{post}:target:{target}:a{attempt}` prevents double-posting.
- LLM output is assist-only; a human must approve before anything publishes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow
from app.core.outbox import OutboxEvent, enqueue, handler
from app.modules.content import llm

from .models import (
    Platform,
    PostSource,
    PostStatus,
    SocialChannel,
    SocialPost,
    SocialPublishTarget,
    TargetStatus,
)
from .providers import get_publisher


class SocialError(Exception):
    pass


# Post statuses from which publishing may (re-)start. Not `publishing` (in-flight) or `published`.
_PUBLISHABLE = {PostStatus.approved, PostStatus.scheduled, PostStatus.failed,
                PostStatus.partially_published}


def _get_post(db: Session, org_id: int, post_id: int) -> SocialPost:
    post = db.get(SocialPost, post_id)
    if post is None or post.org_id != org_id:
        raise SocialError("post not found")
    return post


def _channels(db: Session, org_id: int, channel_ids: list[int]) -> list[SocialChannel]:
    out = []
    for cid in channel_ids:
        ch = db.get(SocialChannel, cid)
        if ch is None or ch.org_id != org_id or not ch.enabled:
            raise SocialError(f"channel {cid} not found or disabled")
        out.append(ch)
    return out


def _set_targets(db: Session, post: SocialPost, channels: list[SocialChannel]) -> None:
    """Reconcile the post's publish targets to exactly `channels` (only while editable)."""
    existing = {t.channel_id: t for t in db.scalars(
        select(SocialPublishTarget).where(SocialPublishTarget.post_id == post.id))}
    wanted = {c.id for c in channels}
    for cid, t in existing.items():
        if cid not in wanted:
            db.delete(t)
    for c in channels:
        if c.id not in existing:
            db.add(SocialPublishTarget(org_id=post.org_id, post_id=post.id, channel_id=c.id))
    db.flush()


def create_post(db: Session, *, org_id: int, created_by: int, channel_ids: list[int],
                body: str = "", source: PostSource = PostSource.human,
                prompt: str = "", org_name: str = "") -> SocialPost:
    channels = _channels(db, org_id, channel_ids)
    provider = ""
    if source == PostSource.llm_assisted and prompt:
        result = llm.draft_copy(prompt=f"a short social media post about: {prompt}",
                                context={"org_name": org_name})
        body = body or result.text
        provider = result.provider
    post = SocialPost(org_id=org_id, created_by_user_id=created_by, body=body, source=source,
                      draft_prompt=prompt, draft_provider=provider)
    db.add(post)
    db.flush()
    _set_targets(db, post, channels)
    return post


def _assert_editable(post: SocialPost) -> None:
    if post.status not in (PostStatus.draft, PostStatus.pending_approval):
        raise SocialError("post can only be edited while it is a draft or awaiting approval")


def update_post(db: Session, *, org_id: int, post_id: int, body: str | None = None,
                channel_ids: list[int] | None = None) -> SocialPost:
    post = _get_post(db, org_id, post_id)
    _assert_editable(post)
    if body is not None:
        post.body = body
    if channel_ids is not None:
        _set_targets(db, post, _channels(db, org_id, channel_ids))
    db.flush()
    return post


def _validate_ready(db: Session, post: SocialPost) -> list[SocialPublishTarget]:
    if not post.body.strip():
        raise SocialError("post body is empty")
    targets = list(db.scalars(
        select(SocialPublishTarget).where(SocialPublishTarget.post_id == post.id)))
    if not targets:
        raise SocialError("select at least one channel")
    for t in targets:
        ch = db.get(SocialChannel, t.channel_id)
        assert ch is not None
        if len(post.body) > ch.char_limit:
            raise SocialError(
                f"post is {len(post.body)} chars; {ch.platform.value} allows {ch.char_limit}")
    return targets


def submit_for_approval(db: Session, *, org_id: int, post_id: int) -> SocialPost:
    post = _get_post(db, org_id, post_id)
    if post.status != PostStatus.draft:
        raise SocialError("only a draft can be submitted for approval")
    _validate_ready(db, post)
    post.status = PostStatus.pending_approval
    db.flush()
    return post


def approve_post(db: Session, *, org_id: int, post_id: int, approver_user_id: int) -> SocialPost:
    post = _get_post(db, org_id, post_id)
    if post.status not in (PostStatus.pending_approval, PostStatus.draft):
        raise SocialError("post is not awaiting approval")
    _validate_ready(db, post)
    post.status = PostStatus.approved
    post.approved_by_user_id = approver_user_id
    db.flush()
    audit.emit(db, org_id=org_id, action="social.approve_post", actor_id=approver_user_id,
               target_type="social_post", target_id=post.id)
    return post


def schedule_post(db: Session, *, org_id: int, post_id: int, scheduled_at: datetime) -> SocialPost:
    post = _get_post(db, org_id, post_id)
    if post.status != PostStatus.approved:
        raise SocialError("only an approved post can be scheduled")
    post.scheduled_at = scheduled_at
    post.status = PostStatus.scheduled
    db.flush()
    return post


def publish_post(db: Session, *, org_id: int, post_id: int, actor_user_id: int) -> SocialPost:
    """THE choke point. Enqueue a publish per non-published target. Refuses anything unapproved."""
    post = _get_post(db, org_id, post_id)
    # The guarantee: nothing publishes without an explicit human approval.
    if post.status not in _PUBLISHABLE or post.approved_by_user_id is None:
        raise SocialError("post must be approved before it can be published")
    targets = _validate_ready(db, post)
    post.status = PostStatus.publishing  # gates concurrent re-entry (a 2nd call sees publishing)
    db.flush()
    for t in targets:
        if t.status == TargetStatus.published:
            continue
        t.status = TargetStatus.pending
        t.attempts += 1
        t.error = ""
        event = enqueue(db, org_id=org_id, event_type="social.publish",
                        idempotency_key=f"social:{post.id}:target:{t.id}:a{t.attempts}",
                        payload={"target_id": t.id})
        if event is not None:
            t.outbox_event_id = event.id
    db.flush()
    audit.emit(db, org_id=org_id, action="social.publish", actor_id=actor_user_id,
               target_type="social_post", target_id=post.id)
    return post


def _recompute_status(db: Session, post: SocialPost) -> None:
    targets = list(db.scalars(
        select(SocialPublishTarget).where(SocialPublishTarget.post_id == post.id)))
    statuses = {t.status for t in targets}
    if statuses == {TargetStatus.published}:
        post.status = PostStatus.published
        post.published_at = post.published_at or utcnow()
    elif TargetStatus.pending in statuses:
        post.status = PostStatus.publishing
    elif TargetStatus.published in statuses:
        post.status = PostStatus.partially_published
    else:
        post.status = PostStatus.failed
    db.flush()


@handler("social.publish")
def _publish_target(db: Session, event: OutboxEvent) -> None:
    target = db.get(SocialPublishTarget, int(event.payload["target_id"]))
    if target is None or target.status == TargetStatus.published:
        return  # idempotent: already done (or gone)
    post = db.get(SocialPost, target.post_id)
    channel = db.get(SocialChannel, target.channel_id)
    assert post is not None and channel is not None
    if not channel.enabled:
        target.status = TargetStatus.failed
        target.error = "channel is disabled"
        db.flush()
        _recompute_status(db, post)
        return
    # Downstream idempotency key is STABLE per target (no attempt suffix) so the receiver dedupes
    # a re-publish of the same target — even if a prior attempt's ambiguous failure (e.g. a
    # timeout the receiver actually processed) got marked failed. The *outbox* event key keeps the
    # attempt suffix so a retry can enqueue a fresh event past the unique constraint.
    result = get_publisher().publish(
        post=post, channel=channel,
        idempotency_key=f"social:{post.id}:target:{target.id}")
    if result.ok:
        target.status = TargetStatus.published
        target.external_ref = result.external_ref
        target.error = ""
    else:
        # Recorded as failed (not raised) so it isn't retried blindly; a human re-triggers
        # publish, which bumps `attempts` and enqueues a fresh event for failed targets only.
        target.status = TargetStatus.failed
        target.error = result.error
    db.flush()
    _recompute_status(db, post)


def publish_due_social_posts(db: Session) -> int:
    """Beat task: publish approved posts whose scheduled time has arrived."""
    due = db.scalars(select(SocialPost).where(
        SocialPost.status == PostStatus.scheduled,
        SocialPost.scheduled_at.is_not(None),
        SocialPost.scheduled_at <= utcnow())).all()
    for post in due:
        publish_post(db, org_id=post.org_id, post_id=post.id,
                     actor_user_id=post.approved_by_user_id or 0)
    return len(due)


def list_posts(db: Session, *, org_id: int) -> list[SocialPost]:
    return list(db.scalars(select(SocialPost).where(SocialPost.org_id == org_id)
                           .order_by(SocialPost.id.desc())))


def post_view(db: Session, post: SocialPost) -> dict:
    targets = db.scalars(
        select(SocialPublishTarget).where(SocialPublishTarget.post_id == post.id))
    return {
        "id": post.id,
        "body": post.body,
        "status": post.status.value,
        "source": post.source.value,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "approved": post.approved_by_user_id is not None,
        "draft_provider": post.draft_provider,
        "targets": [{"channel_id": t.channel_id, "status": t.status.value,
                     "external_ref": t.external_ref, "error": t.error} for t in targets],
    }


def list_channels(db: Session, *, org_id: int) -> list[SocialChannel]:
    return list(db.scalars(select(SocialChannel).where(SocialChannel.org_id == org_id)
                           .order_by(SocialChannel.id)))


def create_channel(db: Session, *, org_id: int, platform: str, handle: str,
                   display_name: str = "", char_limit: int = 280) -> SocialChannel:
    ch = SocialChannel(org_id=org_id, platform=Platform(platform), handle=handle,
                       display_name=display_name or handle, char_limit=char_limit)
    db.add(ch)
    db.flush()
    return ch
