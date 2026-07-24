"""Content / website-builder: editable public pages composed of typed blocks.

A page is an ordered list of typed blocks (safe by construction) plus optional custom CSS and
an optional privileged custom-HTML block. Two copies of the servable content are kept:
- the working draft (`blocks`, `custom_css`) that editors mutate, and
- the published snapshot (`published_blocks`, `published_css`) that the public site serves.
Custom HTML/CSS is ALWAYS sanitized before it is stored in a servable field — see
`app/modules/content/sanitize.py`. The public API only ever serves the `published_*` fields.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
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


class PageStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class Page(Base, TimestampMixin):
    """A public website page managed through the builder. Org-scoped; slug unique per org."""

    __tablename__ = "content_page"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_content_page_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[PageStatus] = mapped_column(default=PageStatus.draft, nullable=False)

    # Working draft. `blocks` is an ordered list of typed block dicts (see BLOCK schema in the
    # service). Any custom-html block's body is stored sanitized; `custom_css` is the raw CSS the
    # editor typed and `custom_css_safe` is its sanitized + page-scoped form.
    blocks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    custom_css: Mapped[str] = mapped_column(Text, default="", nullable=False)
    custom_css_safe: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Published snapshot — what the public site serves. Frozen at publish time.
    published_blocks: Mapped[list | None] = mapped_column(JSON)
    published_css: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Navigation / layout.
    show_in_nav: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nav_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class PageRevision(Base, TimestampMixin):
    """A frozen snapshot of a page's content, written on each publish, for rollback/history."""

    __tablename__ = "content_page_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("content_page.id"), nullable=False, index=True)
    blocks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    custom_css: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
