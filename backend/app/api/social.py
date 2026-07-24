"""Social media endpoints: channels + the post lifecycle (draft → approve → schedule → publish).

Publishing is human-only and approval-gated; there is no auto-publish path. LLM drafting is an
optional assist on the draft step.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.authz import Principal
from app.modules.org.models import Organization
from app.modules.social import service
from app.modules.social.models import PostSource
from app.modules.social.service import SocialError

from .deps import get_db, get_public_org, require_permission

router = APIRouter(prefix="/api/social", tags=["social"])


class IdOut(BaseModel):
    id: int


class ChannelIn(BaseModel):
    platform: str = "manual"
    handle: str = Field(min_length=1, max_length=120)
    display_name: str = ""
    char_limit: int = Field(default=280, ge=1, le=100000)


class PostIn(BaseModel):
    body: str = ""
    channel_ids: list[int] = Field(default_factory=list)
    use_ai: bool = False
    prompt: str = ""


class PostPatch(BaseModel):
    body: str | None = None
    channel_ids: list[int] | None = None


class ScheduleIn(BaseModel):
    scheduled_at: datetime


def _err(exc: SocialError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/channels")
def list_channels(db: Session = Depends(get_db),
                  principal: Principal = Depends(require_permission("social.manage"))):
    return [{"id": c.id, "platform": c.platform.value, "handle": c.handle,
             "display_name": c.display_name, "enabled": c.enabled, "char_limit": c.char_limit}
            for c in service.list_channels(db, org_id=principal.org_id)]


@router.post("/channels", response_model=IdOut, status_code=201)
def create_channel(payload: ChannelIn, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("social.manage"))):
    try:
        ch = service.create_channel(db, org_id=principal.org_id, platform=payload.platform,
                                    handle=payload.handle, display_name=payload.display_name,
                                    char_limit=payload.char_limit)
    except (SocialError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=ch.id)


@router.get("/posts")
def list_posts(db: Session = Depends(get_db),
               principal: Principal = Depends(require_permission("social.manage"))):
    return [service.post_view(db, p) for p in service.list_posts(db, org_id=principal.org_id)]


@router.post("/posts", response_model=IdOut, status_code=201)
def create_post(payload: PostIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("social.draft")),
                org: Organization = Depends(get_public_org)):
    source = PostSource.llm_assisted if payload.use_ai else PostSource.human
    try:
        post = service.create_post(db, org_id=principal.org_id, created_by=principal.user_id,
                                   channel_ids=payload.channel_ids, body=payload.body,
                                   source=source, prompt=payload.prompt, org_name=org.name)
    except SocialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=post.id)


@router.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("social.manage"))):
    try:
        return service.post_view(db, service._get_post(db, principal.org_id, post_id))
    except SocialError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/posts/{post_id}")
def update_post(post_id: int, payload: PostPatch, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("social.manage"))):
    try:
        post = service.update_post(db, org_id=principal.org_id, post_id=post_id,
                                   body=payload.body, channel_ids=payload.channel_ids)
    except SocialError as exc:
        raise _err(exc) from exc
    db.commit()
    return service.post_view(db, post)


@router.post("/posts/{post_id}/submit")
def submit(post_id: int, db: Session = Depends(get_db),
           principal: Principal = Depends(require_permission("social.manage"))):
    try:
        post = service.submit_for_approval(db, org_id=principal.org_id, post_id=post_id)
    except SocialError as exc:
        raise _err(exc) from exc
    db.commit()
    return service.post_view(db, post)


@router.post("/posts/{post_id}/approve")
def approve(post_id: int, db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("social.approve"))):
    try:
        post = service.approve_post(db, org_id=principal.org_id, post_id=post_id,
                                    approver_user_id=principal.user_id)
    except SocialError as exc:
        raise _err(exc) from exc
    db.commit()
    return service.post_view(db, post)


@router.post("/posts/{post_id}/schedule")
def schedule(post_id: int, payload: ScheduleIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("social.publish"))):
    # Scheduling commits to an unattended publish (the beat runs with no principal), so it
    # requires the publish permission, not just manage.
    try:
        post = service.schedule_post(db, org_id=principal.org_id, post_id=post_id,
                                     scheduled_at=payload.scheduled_at)
    except SocialError as exc:
        raise _err(exc) from exc
    db.commit()
    return service.post_view(db, post)


@router.post("/posts/{post_id}/publish")
def publish(post_id: int, db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("social.publish"))):
    try:
        post = service.publish_post(db, org_id=principal.org_id, post_id=post_id,
                                    actor_user_id=principal.user_id)
    except SocialError as exc:
        raise _err(exc) from exc
    db.commit()
    return service.post_view(db, post)
