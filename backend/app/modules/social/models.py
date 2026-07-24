"""Social media: channels, posts, and per-channel publish targets.

Governance mirrors the communications approval gate but is STRICTER: there is no auto-publish
path — every post requires explicit human approval before it can be published to any channel,
regardless of anything. LLM drafting is assist-only. Publishing side-effects run through the
transactional outbox with a per-target idempotency key (so a multi-channel post can never
double-post a single channel).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Platform(str, enum.Enum):
    manual = "manual"        # dev/default: no external effect, exports copy
    webhook = "webhook"      # POST to an outgoing webhook (Zapier/Make/etc.)
    x = "x"                  # real adapters below are DISABLED in v1 (behind the publisher port)
    linkedin = "linkedin"
    mastodon = "mastodon"
    facebook = "facebook"


class PostStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    publishing = "publishing"
    published = "published"
    partially_published = "partially_published"
    failed = "failed"


class PostSource(str, enum.Enum):
    human = "human"
    llm_assisted = "llm_assisted"


class TargetStatus(str, enum.Enum):
    pending = "pending"
    published = "published"
    failed = "failed"


class SocialChannel(Base, TimestampMixin):
    __tablename__ = "social_channel"
    __table_args__ = (UniqueConstraint("org_id", "platform", "handle", name="uq_social_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    platform: Mapped[Platform] = mapped_column(default=Platform.manual, nullable=False)
    handle: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    connection_status: Mapped[str] = mapped_column(String(20), default="connected", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    char_limit: Mapped[int] = mapped_column(Integer, default=280, nullable=False)


class SocialPost(Base, TimestampMixin):
    __tablename__ = "social_post"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[PostStatus] = mapped_column(default=PostStatus.draft, nullable=False)
    source: Mapped[PostSource] = mapped_column(default=PostSource.human, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    # Provenance for LLM-assisted drafts.
    agent_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("agent_proposal.id"))
    draft_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    draft_provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class SocialPublishTarget(Base, TimestampMixin):
    """One post → N channels. Per-channel result + the idempotency anchor for publishing."""

    __tablename__ = "social_publish_target"
    __table_args__ = (
        UniqueConstraint("post_id", "channel_id", name="uq_social_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("social_post.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("social_channel.id"), nullable=False)
    status: Mapped[TargetStatus] = mapped_column(default=TargetStatus.pending, nullable=False)
    external_ref: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    error: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Bumped once per publish attempt; the idempotency key embeds it so a retry of a failed
    # target uses a fresh key while re-clicks within one attempt dedupe. Concurrent double-
    # publish is separately prevented by the post-level status guard (approved -> publishing).
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outbox_event_id: Mapped[int | None] = mapped_column(Integer)
