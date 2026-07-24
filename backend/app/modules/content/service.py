"""Website-builder service: page lifecycle + block sanitization.

Blocks are typed dicts. Safe-by-construction blocks (heading/paragraph/image/button/divider)
render as components; `html`/`embed` are the escape hatches and are the ONLY blocks that need the
privileged `site.develop` permission. Everything servable is sanitized here on every write, and
publishing freezes a sanitized snapshot into `published_*`.
"""

from __future__ import annotations

import html as _htmllib
from datetime import datetime

import nh3
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow

from .models import Page, PageRevision, PageStatus
from .sanitize import sanitize_css, sanitize_html


class ContentError(Exception):
    pass


# Slugs that must not be taken by CMS pages: API + the app's static frontend routes.
RESERVED_SLUGS: frozenset[str] = frozenset({
    "api", "admin", "login", "logout", "activate", "verify", "dashboard",
    "opportunities", "calendar", "trainings", "about", "faq", "contact", "_next", "p",
})

_SAFE_TYPES = frozenset({"heading", "paragraph", "image", "button", "divider"})
_PRIVILEGED_TYPES = frozenset({"html", "embed"})
ALL_TYPES = _SAFE_TYPES | _PRIVILEGED_TYPES


def _safe_url(url: str) -> str:
    """Allow http(s), mailto, and site-relative (/... or #...) URLs; reject everything else."""
    url = (url or "").strip()
    if url.startswith(("https://", "http://", "mailto:", "/", "#")):
        return url
    return ""  # drop javascript:, data:, etc.


def _plain(text: str, limit: int = 500) -> str:
    """Return plain text for a field that must not contain markup (heading, button label, title).

    Strips all tags, then decodes entities so React (which escapes once on render) shows the true
    characters — nh3 alone would leave `&` double-encoded.
    """
    if not text:
        return ""
    return _htmllib.unescape(nh3.clean(str(text), tags=set(), attributes={}))[:limit]


def uses_privileged(blocks: list, custom_css: str) -> bool:
    """True if the content needs `site.develop` (raw html/embed block or any custom CSS)."""
    if custom_css and custom_css.strip():
        return True
    return any(isinstance(b, dict) and b.get("type") in _PRIVILEGED_TYPES for b in blocks)


def sanitize_blocks(blocks: list) -> list:
    """Normalise + sanitize every block. Unknown types are dropped."""
    out: list[dict] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "heading":
            out.append({"type": t, "level": min(max(int(b.get("level", 2)), 1), 4),
                        "text": _plain(b.get("text", ""), 200)})
        elif t == "paragraph":
            # Rich text limited to the sanitizer's inline allowlist.
            out.append({"type": t, "html": sanitize_html(b.get("html", ""))})
        elif t == "image":
            out.append({"type": t, "url": _safe_url(b.get("url", "")),
                        "alt": _plain(b.get("alt", ""), 200)})
        elif t == "button":
            out.append({"type": t, "label": _plain(b.get("label", ""), 80),
                        "href": _safe_url(b.get("href", ""))})
        elif t == "divider":
            out.append({"type": t})
        elif t == "html":
            # Sanitized inline HTML — safe to render directly. Read from the raw `html` field on
            # first save, or the already-sanitized `safe_html` on a re-sanitize (idempotent), so
            # re-running this on stored blocks never drops content.
            out.append({"type": t, "safe_html": sanitize_html(b.get("html") or b.get("safe_html", ""))})
        elif t == "embed":
            # Raw HTML for the privileged sandboxed-iframe path. Kept raw ON PURPOSE; the frontend
            # renders it inside <iframe sandbox srcdoc> so scripts cannot touch the parent page.
            out.append({"type": t, "raw_html": str(b.get("html") or b.get("raw_html", ""))[:20000]})
        # unknown types are silently dropped
    return out


def _get(db: Session, org_id: int, page_id: int) -> Page:
    page = db.get(Page, page_id)
    if page is None or page.org_id != org_id:
        raise ContentError("page not found")
    return page


def create_page(db: Session, *, org_id: int, slug: str, title: str,
                actor_user_id: int) -> Page:
    slug = slug.strip().lower()
    if not slug or "/" in slug or slug in RESERVED_SLUGS:
        raise ContentError(f"invalid or reserved slug: {slug!r}")
    if db.scalar(select(Page).where(Page.org_id == org_id, Page.slug == slug)) is not None:
        raise ContentError("a page with that slug already exists")
    page = Page(org_id=org_id, slug=slug, title=_plain(title, 200) or slug,
                updated_by_user_id=actor_user_id)
    db.add(page)
    db.flush()
    return page


def update_page(db: Session, *, org_id: int, page_id: int, actor_user_id: int,
                title: str | None = None, blocks: list | None = None,
                custom_css: str | None = None, show_in_nav: bool | None = None,
                nav_order: int | None = None) -> Page:
    page = _get(db, org_id, page_id)
    if title is not None:
        page.title = _plain(title, 200) or page.slug
    if blocks is not None:
        page.blocks = sanitize_blocks(blocks)
    if custom_css is not None:
        page.custom_css = custom_css[:20000]
        page.custom_css_safe = sanitize_css(page.custom_css, scope_id=str(page.id))
    if show_in_nav is not None:
        page.show_in_nav = show_in_nav
    if nav_order is not None:
        page.nav_order = int(nav_order)
    page.updated_by_user_id = actor_user_id
    db.flush()
    return page


def publish_page(db: Session, *, org_id: int, page_id: int, actor_user_id: int) -> Page:
    """Freeze the current sanitized draft into the public snapshot + write a revision."""
    page = _get(db, org_id, page_id)
    # Re-sanitize defensively at publish time (never trust that the stored draft is clean).
    page.blocks = sanitize_blocks(page.blocks)
    page.custom_css_safe = sanitize_css(page.custom_css, scope_id=str(page.id))
    db.add(PageRevision(org_id=org_id, page_id=page.id, blocks=page.blocks,
                        custom_css=page.custom_css, created_by_user_id=actor_user_id))
    page.published_blocks = page.blocks
    page.published_css = page.custom_css_safe
    page.published_at = utcnow()
    page.status = PageStatus.published
    db.flush()
    audit.emit(db, org_id=org_id, action="content.publish_page", actor_id=actor_user_id,
               target_type="page", target_id=page.id, meta={"slug": page.slug})
    return page


def unpublish_page(db: Session, *, org_id: int, page_id: int, actor_user_id: int) -> Page:
    page = _get(db, org_id, page_id)
    page.status = PageStatus.draft
    page.published_blocks = None
    page.published_css = ""
    page.published_at = None
    db.flush()
    audit.emit(db, org_id=org_id, action="content.unpublish_page", actor_id=actor_user_id,
               target_type="page", target_id=page.id, meta={"slug": page.slug})
    return page


def list_pages(db: Session, *, org_id: int) -> list[Page]:
    return list(db.scalars(select(Page).where(Page.org_id == org_id).order_by(Page.nav_order,
                                                                              Page.id)))


def get_page(db: Session, *, org_id: int, page_id: int) -> Page:
    return _get(db, org_id, page_id)


def get_published_by_slug(db: Session, *, org_id: int, slug: str) -> Page | None:
    page = db.scalar(select(Page).where(Page.org_id == org_id, Page.slug == slug.lower()))
    if page is None or page.status != PageStatus.published or page.published_blocks is None:
        return None
    return page


def get_home(db: Session, *, org_id: int) -> Page | None:
    page = db.scalar(select(Page).where(Page.org_id == org_id, Page.is_home.is_(True)))
    if page is None or page.status != PageStatus.published or page.published_blocks is None:
        return None
    return page


def published_nav(db: Session, *, org_id: int) -> list[dict]:
    pages = db.scalars(
        select(Page).where(Page.org_id == org_id, Page.status == PageStatus.published,
                           Page.show_in_nav.is_(True)).order_by(Page.nav_order, Page.id)
    )
    return [{"slug": p.slug, "title": p.title} for p in pages]


def public_view(page: Page) -> dict:
    """Serialize the PUBLISHED snapshot for the public API — never the working draft."""
    return {
        "slug": page.slug,
        "title": page.title,
        "blocks": page.published_blocks or [],
        "css": page.published_css or "",
        "scope_id": str(page.id),
        "published_at": page.published_at.isoformat() if page.published_at else None,
    }


def admin_view(page: Page) -> dict:
    return {
        "id": page.id,
        "slug": page.slug,
        "title": page.title,
        "status": page.status.value,
        "blocks": page.blocks or [],
        "custom_css": page.custom_css or "",
        "show_in_nav": page.show_in_nav,
        "nav_order": page.nav_order,
        "is_home": page.is_home,
        "published_at": page.published_at.isoformat() if page.published_at else None,
        "updated_at": page.updated_at.isoformat() if isinstance(page.updated_at, datetime)
        else None,
    }
