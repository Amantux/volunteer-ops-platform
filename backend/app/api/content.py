"""Website-builder endpoints: admin page CRUD + publish + AI copy assist, and public serving.

Permission model:
- site.edit    — create/edit pages with safe blocks (heading/paragraph/image/button/divider)
- site.develop — additionally use the raw `html`/`embed` blocks and custom CSS (the escape hatch)
- site.publish — publish/unpublish

Custom HTML/CSS is sanitized in the service on every write; the public routes serve only the
published, sanitized snapshot.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.authz import Principal, has_permission
from app.modules.content import llm, service
from app.modules.content.service import ContentError
from app.modules.org.models import Organization

from .deps import get_db, get_public_org, require_permission

admin_router = APIRouter(prefix="/api/admin/pages", tags=["content-admin"])
public_router = APIRouter(prefix="/api/public", tags=["content-public"])


class IdOut(BaseModel):
    id: int


class PageCreateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)


class PageUpdateIn(BaseModel):
    title: str | None = None
    blocks: list | None = None
    custom_css: str | None = None
    show_in_nav: bool | None = None
    nav_order: int | None = None


class AssistIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


def _require_develop_if_privileged(db: Session, principal: Principal,
                                   blocks: list | None, custom_css: str | None) -> None:
    """Raw html/embed blocks and custom CSS require the privileged `site.develop` permission."""
    if service.uses_privileged(blocks or [], custom_css or "") and not has_permission(
        db, principal, "site.develop"
    ):
        raise HTTPException(status_code=403,
                            detail="Custom HTML/CSS requires the site.develop permission")


@admin_router.get("")
def list_pages(db: Session = Depends(get_db),
               principal: Principal = Depends(require_permission("site.edit"))):
    return [service.admin_view(p) for p in service.list_pages(db, org_id=principal.org_id)]


@admin_router.post("", response_model=IdOut, status_code=201)
def create_page(payload: PageCreateIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("site.edit"))):
    try:
        page = service.create_page(db, org_id=principal.org_id, slug=payload.slug,
                                   title=payload.title, actor_user_id=principal.user_id)
    except ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=page.id)


@admin_router.get("/{page_id}")
def get_page(page_id: int, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("site.edit"))):
    try:
        return service.admin_view(service.get_page(db, org_id=principal.org_id, page_id=page_id))
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@admin_router.patch("/{page_id}")
def update_page(page_id: int, payload: PageUpdateIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("site.edit"))):
    _require_develop_if_privileged(db, principal, payload.blocks, payload.custom_css)
    try:
        page = service.update_page(
            db, org_id=principal.org_id, page_id=page_id, actor_user_id=principal.user_id,
            title=payload.title, blocks=payload.blocks, custom_css=payload.custom_css,
            show_in_nav=payload.show_in_nav, nav_order=payload.nav_order)
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return service.admin_view(page)


@admin_router.post("/{page_id}/publish")
def publish_page(page_id: int, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("site.publish"))):
    try:
        page = service.publish_page(db, org_id=principal.org_id, page_id=page_id,
                                    actor_user_id=principal.user_id)
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return service.admin_view(page)


@admin_router.post("/{page_id}/unpublish")
def unpublish_page(page_id: int, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("site.publish"))):
    try:
        page = service.unpublish_page(db, org_id=principal.org_id, page_id=page_id,
                                      actor_user_id=principal.user_id)
    except ContentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return service.admin_view(page)


@admin_router.post("/assist")
def assist(payload: AssistIn, request: Request, db: Session = Depends(get_db),
           principal: Principal = Depends(require_permission("site.edit")),
           org: Organization = Depends(get_public_org)):
    """LLM copy suggestion for a text block. Assist only — the editor keeps/edits/discards it."""
    client = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"assist:{principal.user_id}:{client}", limit=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    result = llm.draft_copy(prompt=payload.prompt, context={"org_name": org.name})
    return {"text": result.text, "provider": result.provider}


# --- Public serving --------------------------------------------------------- #

@public_router.get("/site-nav")
def site_nav(db: Session = Depends(get_db), org: Organization = Depends(get_public_org)):
    return service.published_nav(db, org_id=org.id)


@public_router.get("/pages/{slug}")
def public_page(slug: str, db: Session = Depends(get_db),
                org: Organization = Depends(get_public_org)):
    page = service.get_published_by_slug(db, org_id=org.id, slug=slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return service.public_view(page)
