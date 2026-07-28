"""Kiosk endpoints: admin CRUD (session + kiosk.manage/view) and device-facing display/check-in
(authenticated by the kiosk token in the URL — a shared-device capability, no user session)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.authz import Principal
from app.modules.kiosk import service

from .deps import get_db, require_permission

admin_router = APIRouter(prefix="/api", tags=["kiosk-admin"])
device_router = APIRouter(prefix="/api", tags=["kiosk-device"])


class IdOut(BaseModel):
    id: int


def _admin_view(k) -> dict:
    return {"id": k.id, "name": k.name, "token": k.token, "mode": k.mode,
            "program_id": k.program_id, "location": k.location, "panels": k.panels,
            "is_active": k.is_active}


# --- Admin ------------------------------------------------------------------ #

class KioskIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: str = "display"
    program_id: int | None = None
    location: str = ""
    panels: list | None = None


class KioskPatch(BaseModel):
    name: str | None = None
    mode: str | None = None
    program_id: int | None = None
    location: str | None = None
    panels: list | None = None
    is_active: bool | None = None


@admin_router.get("/admin/kiosks")
def list_kiosks(db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("kiosk.view"))):
    return [_admin_view(k) for k in service.list_kiosks(db, org_id=principal.org_id)]


@admin_router.post("/admin/kiosks", response_model=IdOut, status_code=201)
def create_kiosk(payload: KioskIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("kiosk.manage"))):
    try:
        k = service.create_kiosk(db, org_id=principal.org_id, name=payload.name, mode=payload.mode,
                                 program_id=payload.program_id, location=payload.location,
                                 panels=payload.panels)
    except service.KioskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=k.id)


@admin_router.patch("/admin/kiosks/{kiosk_id}", response_model=IdOut)
def update_kiosk(kiosk_id: int, payload: KioskPatch, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("kiosk.manage"))):
    try:
        k = service.update_kiosk(db, org_id=principal.org_id, kiosk_id=kiosk_id,
                                 **payload.model_dump(exclude_unset=True))
    except service.KioskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=k.id)


class TaskIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


@admin_router.get("/admin/kiosks/{kiosk_id}/tasks")
def list_tasks(kiosk_id: int, db: Session = Depends(get_db),
               principal: Principal = Depends(require_permission("kiosk.view"))):
    return [{"id": t.id, "label": t.label, "sort_order": t.sort_order}
            for t in service.list_tasks(db, org_id=principal.org_id, kiosk_id=kiosk_id)]


@admin_router.post("/admin/kiosks/{kiosk_id}/tasks", response_model=IdOut, status_code=201)
def add_task(kiosk_id: int, payload: TaskIn, db: Session = Depends(get_db),
             principal: Principal = Depends(require_permission("kiosk.manage"))):
    try:
        t = service.add_task(db, org_id=principal.org_id, kiosk_id=kiosk_id, label=payload.label,
                             sort_order=payload.sort_order)
    except service.KioskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=t.id)


# --- Device (token-authenticated) ------------------------------------------- #

def _device_limit(request: Request, token: str) -> None:
    client = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"kiosk:{token[:12]}:{client}", limit=120, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests.")


@device_router.get("/kiosk/{token}")
def kiosk_display(token: str, request: Request, db: Session = Depends(get_db)):
    _device_limit(request, token)
    try:
        return service.kiosk_display(db, token=token)
    except service.KioskError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CheckinIn(BaseModel):
    signup_id: int


@device_router.post("/kiosk/{token}/checkin", response_model=IdOut)
def kiosk_checkin(token: str, payload: CheckinIn, request: Request, db: Session = Depends(get_db)):
    _device_limit(request, token)
    try:
        result = service.kiosk_checkin(db, token=token, signup_id=payload.signup_id)
    except service.KioskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=result["signup_id"])


@device_router.post("/kiosk/{token}/tasks/{task_id}/toggle")
def kiosk_toggle_task(token: str, task_id: int, request: Request, db: Session = Depends(get_db)):
    _device_limit(request, token)
    try:
        result = service.toggle_task(db, token=token, task_id=task_id)
    except service.KioskError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result
