"""Communications endpoints: audiences, preview, campaigns, approval, send, unsubscribe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.authz import Principal
from app.modules.communications import campaigns
from app.modules.communications.campaigns import CommsError
from app.modules.org.models import Organization

from .deps import get_db, get_public_org, require_permission

router = APIRouter(prefix="/api/comms", tags=["communications"])


class AudienceIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    # e.g. {"segment": "volunteers"} or {"segment": "all_contacts"}
    rule: dict = Field(default_factory=lambda: {"segment": "volunteers"})


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_key: str
    audience_id: int


class IdOut(BaseModel):
    id: int


@router.post("/audiences", response_model=IdOut, status_code=201)
def create_audience(payload: AudienceIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("comms.manage"))):
    try:
        a = campaigns.create_audience(db, org_id=principal.org_id, name=payload.name,
                                      rule=payload.rule)
    except CommsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=a.id)


@router.get("/audiences/{audience_id}/preview")
def preview_audience(audience_id: int, db: Session = Depends(get_db),
                     principal: Principal = Depends(require_permission("comms.manage"))):
    """Show the exact recipient count + a sample BEFORE anyone approves or sends."""
    try:
        return campaigns.preview_audience(db, org_id=principal.org_id, audience_id=audience_id)
    except CommsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/campaigns", response_model=IdOut, status_code=201)
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("comms.manage"))):
    try:
        c = campaigns.create_campaign(db, org_id=principal.org_id, name=payload.name,
                                      template_key=payload.template_key,
                                      audience_id=payload.audience_id)
    except CommsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=c.id)


@router.post("/campaigns/{campaign_id}/submit", response_model=IdOut)
def submit(campaign_id: int, db: Session = Depends(get_db),
           principal: Principal = Depends(require_permission("comms.manage"))):
    try:
        c = campaigns.submit_for_approval(db, org_id=principal.org_id, campaign_id=campaign_id)
    except CommsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=c.id)


@router.post("/campaigns/{campaign_id}/approve", response_model=IdOut)
def approve(campaign_id: int, db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("comms.approve"))):
    try:
        c = campaigns.approve_campaign(db, org_id=principal.org_id, campaign_id=campaign_id,
                                       approver_user_id=principal.user_id)
    except CommsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=c.id)


@router.post("/campaigns/{campaign_id}/send")
def send(campaign_id: int, db: Session = Depends(get_db),
         principal: Principal = Depends(require_permission("comms.manage"))):
    try:
        result = campaigns.send_campaign(db, org_id=principal.org_id, campaign_id=campaign_id,
                                         actor_user_id=principal.user_id)
    except CommsError as exc:
        # 409 when it needs approval / already sent.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return result


class UnsubscribeIn(BaseModel):
    email: EmailStr


@router.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeIn, db: Session = Depends(get_db),
                org: Organization = Depends(get_public_org)):
    """Public unsubscribe — add the address to the org's suppression list."""
    campaigns.suppress(db, org_id=org.id, email=str(payload.email), reason="unsubscribe")
    db.commit()
    return {"message": "You've been unsubscribed."}
