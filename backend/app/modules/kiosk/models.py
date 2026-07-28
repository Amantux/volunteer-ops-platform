"""Kiosk / day-of-operations surfaces: named, admin-configurable tablet displays.

A Kiosk is addressed by an unguessable device token (the tablet opens /kiosk/<token> in kiosk mode)
and by a human name (which the MCP tools and admins use). `panels` is the admin-configured layout:
an ordered list of {type, ...options} where type ∈ schedule | checkin | tasks | fyi | roster |
camera(placeholder). Two modes: "shared" (accepts check-in/task input) or "display" (read-only).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Kiosk(Base, TimestampMixin):
    __tablename__ = "kiosk"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_kiosk_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)  # human/MCP address
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(20), default="display", nullable=False)  # shared|display
    program_id: Mapped[int | None] = mapped_column(ForeignKey("program.id"))
    location: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    panels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KioskTask(Base, TimestampMixin):
    """A recurring day-of checklist item shown on a kiosk (e.g. "Puppies fed — AM")."""

    __tablename__ = "kiosk_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    kiosk_id: Mapped[int] = mapped_column(ForeignKey("kiosk.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KioskTaskCompletion(Base, TimestampMixin):
    """One task marked done for one day. Toggling off deletes the row (a day is done or not)."""

    __tablename__ = "kiosk_task_completion"
    __table_args__ = (UniqueConstraint("task_id", "on_date", name="uq_task_completion_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("kiosk_task.id"), nullable=False, index=True)
    on_date: Mapped[date] = mapped_column(Date, nullable=False)
    done_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    done_note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
