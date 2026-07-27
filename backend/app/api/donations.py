"""Donations endpoints — public donate flow (+ webhook) and finance admin.

Money state changes ONLY via the signature-verified webhook (INV-WEBHOOK-AUTHORITATIVE); the
public routes create a PENDING donation and never contact the provider synchronously. Donor
identity is finance/admin-only (INV-DONOR-SEPARATION) and never returned on a public route.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import botcheck, ratelimit
from app.core.authz import Principal
from app.modules.donations import service
from app.modules.donations.payments.factory import get_payment_provider
from app.modules.donations.payments.port import WebhookVerificationError
from app.modules.org.models import Organization

from .deps import get_db, get_public_org, require_permission

public_router = APIRouter(prefix="/api", tags=["donations-public"])
admin_router = APIRouter(prefix="/api", tags=["donations-admin"])


class IdOut(BaseModel):
    id: int


# --- Public: campaign page + donate flow ------------------------------------ #

@public_router.get("/campaigns/{slug}")
def public_campaign(slug: str, db: Session = Depends(get_db),
                    org: Organization = Depends(get_public_org)):
    c = service.get_public_campaign(db, org_id=org.id, slug=slug)
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "slug": c.slug, "title": c.title, "description": c.description, "currency": c.currency,
        "suggested_amounts": c.suggested_amounts, "designations": c.designations,
        "progress": service.campaign_progress(db, org_id=org.id, campaign=c),  # None unless opted-in
    }


class DonateIn(BaseModel):
    campaign_slug: str
    amount_minor_units: int = Field(gt=0)
    kind: str = "one_time"  # one_time | recurring
    donor_name: str = ""
    donor_email: str | None = None
    is_anonymous: bool = False
    designation_code: str = ""
    consent_marketing: bool = False
    bot_token: str | None = None


@public_router.post("/public/donations", status_code=201)
def start_donation(payload: DonateIn, request: Request, db: Session = Depends(get_db),
                   org: Organization = Depends(get_public_org)):
    # Abuse controls (card-testing / bombing): per-IP rate limit + bot check (design §8).
    client = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"donate:{client}", limit=8, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again shortly.")
    if not botcheck.verify(payload.bot_token, remote_ip=client):
        raise HTTPException(status_code=400, detail="Bot check failed. Please try again.")
    campaign = service.get_public_campaign(db, org_id=org.id, slug=payload.campaign_slug)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        d = service.create_donation(
            db, org_id=org.id, campaign_id=campaign.id,
            amount_minor_units=payload.amount_minor_units, kind=payload.kind,
            donor_name=payload.donor_name, donor_email=payload.donor_email,
            is_anonymous=payload.is_anonymous, hard_anonymous=payload.is_anonymous and not payload.donor_email,
            designation_code=payload.designation_code, consent_marketing=payload.consent_marketing)
    except service.DonationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    # The browser polls the status endpoint with this capability token until checkout_url is ready.
    return {"donation_id": d.id, "token": d.public_token, "status": d.status.value}


@public_router.get("/public/donations/status")
def donation_status(token: str, db: Session = Depends(get_db),
                    org: Organization = Depends(get_public_org)):
    result = service.public_donation_status(db, org_id=org.id, public_token=token)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@public_router.post("/webhooks/payments")
async def payments_webhook(request: Request, db: Session = Depends(get_db),
                           org: Organization = Depends(get_public_org)):
    # Verify the signature over the RAW body BEFORE parsing (design §4 rule 1). Bad sig → 401.
    raw = await request.body()
    signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Signature", "")
    provider = get_payment_provider()
    try:
        event = provider.verify_webhook(raw, signature)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail="invalid signature") from exc
    try:
        outcome = service.record_webhook_event(db, org_id=org.id, event=event, provider=provider.name)
    except Exception:  # noqa: BLE001 - return 5xx so the provider retries; reconcile is idempotent
        db.rollback()
        raise HTTPException(status_code=500, detail="reconcile failed") from None
    db.commit()
    return {"outcome": outcome}


# --- Admin: campaigns, donations, in-kind, reporting, export ---------------- #

class CampaignIn(BaseModel):
    slug: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    goal_minor_units: int | None = None
    currency: str = "USD"
    suggested_amounts: list[int] = Field(default_factory=list)
    designations: list[dict] = Field(default_factory=list)


class CampaignPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    goal_minor_units: int | None = None
    status: str | None = None
    is_public: bool | None = None
    publish_progress: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    suggested_amounts: list[int] | None = None
    designations: list[dict] | None = None


def _campaign_view(c) -> dict:
    return {"id": c.id, "slug": c.slug, "title": c.title, "description": c.description,
            "goal_minor_units": c.goal_minor_units, "currency": c.currency,
            "status": c.status.value, "is_public": c.is_public,
            "publish_progress": c.publish_progress,
            "starts_at": c.starts_at.isoformat() if c.starts_at else None,
            "ends_at": c.ends_at.isoformat() if c.ends_at else None,
            "suggested_amounts": c.suggested_amounts, "designations": c.designations}


@admin_router.get("/admin/campaigns")
def list_campaigns(db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("donation.view"))):
    return [_campaign_view(c) for c in service.list_campaigns(db, org_id=principal.org_id)]


@admin_router.post("/admin/campaigns", response_model=IdOut, status_code=201)
def create_campaign(payload: CampaignIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("donation.manage"))):
    try:
        c = service.create_campaign(db, org_id=principal.org_id, slug=payload.slug,
                                    title=payload.title, description=payload.description,
                                    goal_minor_units=payload.goal_minor_units,
                                    currency=payload.currency,
                                    suggested_amounts=payload.suggested_amounts,
                                    designations=payload.designations)
    except service.DonationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=c.id)


@admin_router.patch("/admin/campaigns/{campaign_id}", response_model=IdOut)
def update_campaign(campaign_id: int, payload: CampaignPatch, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("donation.manage"))):
    try:
        c = service.update_campaign(db, org_id=principal.org_id, campaign_id=campaign_id,
                                    **payload.model_dump(exclude_unset=True))
    except service.DonationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=c.id)


@admin_router.get("/admin/donations")
def list_donations(db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("donation.view"))):
    from sqlalchemy import select as _select

    from app.modules.donations.models import Donation, Donor
    rows = db.execute(
        _select(Donation, Donor).join(Donor, Donor.id == Donation.donor_id, isouter=True)
        .where(Donation.org_id == principal.org_id).order_by(Donation.created_at.desc())).all()
    return [{
        "id": d.id, "campaign_id": d.campaign_id, "amount_minor_units": d.amount_minor_units,
        "currency": d.currency, "kind": d.kind.value, "status": d.status.value,
        "is_anonymous": d.is_anonymous, "designation_code": d.designation_code,
        "refunded_minor_units": d.refunded_minor_units,
        "created_at": d.created_at.isoformat(),
        # Donor identity is finance/admin-only (this route requires donation.view).
        "donor_name": ("Anonymous" if d.is_anonymous or donor is None else donor.display_name),
    } for d, donor in rows]


class InKindIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    received_at: datetime
    campaign_id: int | None = None
    donor_name: str = ""
    donor_email: str | None = None
    estimated_value_minor_units: int | None = None
    currency: str = "USD"


@admin_router.post("/admin/in-kind", response_model=IdOut, status_code=201)
def record_in_kind(payload: InKindIn, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("donation.manage"))):
    try:
        ik = service.record_in_kind(db, org_id=principal.org_id, description=payload.description,
                                    received_at=payload.received_at, campaign_id=payload.campaign_id,
                                    donor_name=payload.donor_name, donor_email=payload.donor_email,
                                    estimated_value_minor_units=payload.estimated_value_minor_units,
                                    currency=payload.currency,
                                    recorded_by_user_id=principal.user_id)
    except service.DonationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=ik.id)


@admin_router.get("/admin/donations/metrics")
def metrics(db: Session = Depends(get_db),
            principal: Principal = Depends(require_permission("donation.view"))):
    return service.donation_metrics(db, org_id=principal.org_id)


@admin_router.get("/admin/donations/export.csv")
def export_csv(db: Session = Depends(get_db),
               principal: Principal = Depends(require_permission("finance.export"))):
    from app.core import audit
    csv_text = service.export_rows(db, org_id=principal.org_id)
    audit.emit(db, org_id=principal.org_id, action="donation.exported", actor_id=principal.user_id)
    db.commit()
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=donations.csv"})
