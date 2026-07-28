"""Kiosk service: admin CRUD + the device-facing display resolution, check-in, and task toggles.
Display/check-in are authenticated by the kiosk token (a shared-device capability), so these run
without a user session; everything is org-scoped through the token's kiosk."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import utcnow

from .models import Kiosk, KioskTask, KioskTaskCompletion

_PANEL_TYPES = {"schedule", "checkin", "tasks", "fyi", "roster", "camera"}
_DEFAULT_PANELS = [{"type": "fyi", "title": "Welcome", "text": "Thanks for volunteering today!"},
                   {"type": "schedule"}, {"type": "checkin"}, {"type": "tasks"}]


class KioskError(Exception):
    pass


# --- Admin CRUD -------------------------------------------------------------- #

def create_kiosk(db: Session, *, org_id: int, name: str, mode: str = "display",
                 program_id: int | None = None, location: str = "",
                 panels: list | None = None) -> Kiosk:
    name = name.strip()
    if not name:
        raise KioskError("name is required")
    if mode not in ("shared", "display"):
        raise KioskError("mode must be 'shared' or 'display'")
    if db.scalar(select(Kiosk).where(Kiosk.org_id == org_id, Kiosk.name == name)) is not None:
        raise KioskError("a kiosk with that name already exists")
    kiosk = Kiosk(org_id=org_id, name=name, token=secrets.token_urlsafe(24), mode=mode,
                  program_id=program_id, location=location,
                  panels=_validate_panels(panels) if panels is not None else list(_DEFAULT_PANELS))
    db.add(kiosk)
    db.flush()
    audit.emit(db, org_id=org_id, action="kiosk.created", target_type="kiosk", target_id=kiosk.id)
    return kiosk


def _validate_panels(panels: list) -> list:
    if not isinstance(panels, list):
        raise KioskError("panels must be a list")
    for p in panels:
        if not isinstance(p, dict) or p.get("type") not in _PANEL_TYPES:
            raise KioskError(f"invalid panel: {p!r}")
    return panels


def update_kiosk(db: Session, *, org_id: int, kiosk_id: int, **fields) -> Kiosk:
    kiosk = db.get(Kiosk, kiosk_id)
    if kiosk is None or kiosk.org_id != org_id:
        raise KioskError("kiosk not found")
    if "mode" in fields and fields["mode"] not in ("shared", "display"):
        raise KioskError("mode must be 'shared' or 'display'")
    if "panels" in fields and fields["panels"] is not None:
        fields["panels"] = _validate_panels(fields["panels"])
    for k, v in fields.items():
        if k in ("name", "mode", "location", "program_id", "panels", "is_active") and v is not None:
            setattr(kiosk, k, v)
    db.flush()
    audit.emit(db, org_id=org_id, action="kiosk.updated", target_type="kiosk", target_id=kiosk.id)
    return kiosk


def list_kiosks(db: Session, *, org_id: int) -> list[Kiosk]:
    return list(db.scalars(select(Kiosk).where(Kiosk.org_id == org_id).order_by(Kiosk.name)))


def get_by_name(db: Session, *, org_id: int, name: str) -> Kiosk | None:
    return db.scalar(select(Kiosk).where(Kiosk.org_id == org_id, Kiosk.name == name))


def _by_token(db: Session, token: str) -> Kiosk:
    kiosk = db.scalar(select(Kiosk).where(Kiosk.token == token, Kiosk.is_active.is_(True)))
    if kiosk is None:
        raise KioskError("kiosk not found")
    return kiosk


# --- Tasks (day-of checklists) ---------------------------------------------- #

def add_task(db: Session, *, org_id: int, kiosk_id: int, label: str, sort_order: int = 0) -> KioskTask:
    kiosk = db.get(Kiosk, kiosk_id)
    if kiosk is None or kiosk.org_id != org_id:
        raise KioskError("kiosk not found")
    task = KioskTask(org_id=org_id, kiosk_id=kiosk_id, label=label.strip(), sort_order=sort_order)
    db.add(task)
    db.flush()
    return task


def list_tasks(db: Session, *, org_id: int, kiosk_id: int) -> list[KioskTask]:
    return list(db.scalars(select(KioskTask).where(
        KioskTask.org_id == org_id, KioskTask.kiosk_id == kiosk_id, KioskTask.is_active.is_(True))
        .order_by(KioskTask.sort_order, KioskTask.id)))


# --- Device-facing: display, check-in, task toggle -------------------------- #

def kiosk_display(db: Session, *, token: str) -> dict:
    """Resolve the kiosk's configured panels into data for the tablet. Token-authenticated."""
    kiosk = _by_token(db, token)
    return {"name": kiosk.name, "mode": kiosk.mode, "location": kiosk.location,
            "panels": [_resolve_panel(db, kiosk, p) for p in kiosk.panels]}


def _today_signups(db: Session, kiosk: Kiosk) -> list[dict]:
    from app.modules.identity.models import Person
    from app.modules.people.models import VolunteerProfile
    from app.modules.scheduling.models import Event, Shift, ShiftRole, ShiftSignup, SignupStatus

    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    q = (select(ShiftSignup, Person.name, ShiftRole.name, Shift.starts_at)
         .join(ShiftRole, ShiftRole.id == ShiftSignup.shift_role_id)
         .join(Shift, Shift.id == ShiftRole.shift_id)
         .join(Event, Event.id == Shift.event_id)
         .join(VolunteerProfile, VolunteerProfile.id == ShiftSignup.volunteer_profile_id)
         .join(Person, Person.id == VolunteerProfile.person_id)
         .where(ShiftSignup.org_id == kiosk.org_id, Shift.starts_at >= start,
                Shift.starts_at <= end,
                ShiftSignup.status.in_([SignupStatus.confirmed, SignupStatus.attended])))
    if kiosk.program_id is not None:
        q = q.where(Event.program_id == kiosk.program_id)
    rows = db.execute(q.order_by(Shift.starts_at)).all()
    return [{"signup_id": s.id, "name": name, "role": role,
             "starts_at": starts.isoformat(),
             "checked_in": s.status == SignupStatus.attended} for s, name, role, starts in rows]


def _resolve_panel(db: Session, kiosk: Kiosk, panel: dict) -> dict:
    ptype = panel.get("type")
    if ptype == "fyi":
        return {"type": "fyi", "title": panel.get("title", ""), "text": panel.get("text", "")}
    if ptype in ("schedule", "checkin"):
        signups = _today_signups(db, kiosk)
        return {"type": ptype, "title": panel.get("title", ""), "signups": signups}
    if ptype == "roster":
        return {"type": "roster", "title": panel.get("title", "Checked in"),
                "signups": [s for s in _today_signups(db, kiosk) if s["checked_in"]]}
    if ptype == "tasks":
        return {"type": "tasks", "title": panel.get("title", "Today's tasks"),
                "tasks": _tasks_today(db, kiosk)}
    if ptype == "camera":
        return {"type": "camera", "title": panel.get("title", "Camera"),
                "status": "not_configured", "note": "Camera feeds are coming soon."}
    return {"type": ptype}


def _tasks_today(db: Session, kiosk: Kiosk) -> list[dict]:
    today = utcnow().date()
    tasks = list_tasks(db, org_id=kiosk.org_id, kiosk_id=kiosk.id)
    done_ids = set(db.scalars(select(KioskTaskCompletion.task_id).where(
        KioskTaskCompletion.org_id == kiosk.org_id, KioskTaskCompletion.on_date == today,
        KioskTaskCompletion.task_id.in_([t.id for t in tasks] or [0]))))
    return [{"id": t.id, "label": t.label, "done": t.id in done_ids} for t in tasks]


def kiosk_checkin(db: Session, *, token: str, signup_id: int) -> dict:
    """Shared-kiosk check-in: mark a volunteer present for their shift. Reuses the scheduling
    check-in so attendance flows through one place. Only works on a 'shared' kiosk."""
    from app.modules.scheduling.service import SchedulingError, check_in
    kiosk = _by_token(db, token)
    if kiosk.mode != "shared":
        raise KioskError("this kiosk is display-only")
    # The signup must be one of today's expected signups for this kiosk (token can't reach others).
    if signup_id not in {s["signup_id"] for s in _today_signups(db, kiosk)}:
        raise KioskError("that check-in isn't available at this kiosk today")
    try:
        s = check_in(db, org_id=kiosk.org_id, signup_id=signup_id, actor_id=f"kiosk:{kiosk.name}")
    except SchedulingError as exc:
        raise KioskError(str(exc)) from exc
    return {"signup_id": s.id, "status": s.status.value}


def toggle_task(db: Session, *, token: str, task_id: int, note: str = "") -> dict:
    kiosk = _by_token(db, token)
    if kiosk.mode != "shared":
        raise KioskError("this kiosk is display-only")
    task = db.get(KioskTask, task_id)
    if task is None or task.org_id != kiosk.org_id or task.kiosk_id != kiosk.id:
        raise KioskError("task not found")
    today = utcnow().date()
    existing = db.scalar(select(KioskTaskCompletion).where(
        KioskTaskCompletion.task_id == task_id, KioskTaskCompletion.on_date == today))
    if existing is not None:
        db.delete(existing)
        done = False
    else:
        db.add(KioskTaskCompletion(org_id=kiosk.org_id, task_id=task_id, on_date=today,
                                   done_at=utcnow(), done_note=note[:200]))
        done = True
    db.flush()
    return {"task_id": task_id, "done": done}


# --- Views (for MCP + admin) ------------------------------------------------ #

def kiosk_summary(db: Session, kiosk: Kiosk) -> dict:
    """A name-addressable summary of what a kiosk is showing — used by the MCP tools so an agent
    can report and reason about each kiosk by name."""
    return {"name": kiosk.name, "mode": kiosk.mode, "location": kiosk.location,
            "active": kiosk.is_active,
            "panels": [p.get("type") for p in kiosk.panels],
            "task_count": len(list_tasks(db, org_id=kiosk.org_id, kiosk_id=kiosk.id))}
