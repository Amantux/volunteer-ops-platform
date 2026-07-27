"""Scheduling: the shared event/shift model + role-based signups and hours.

A single Shift model represents one-time events, recurring activities, projects, and
maintenance windows (distinguished by the parent Event). Eligibility is expressed on
ShiftRole via a required qualification type.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class SignupStatus(str, enum.Enum):
    confirmed = "confirmed"
    waitlisted = "waitlisted"
    cancelled = "cancelled"
    attended = "attended"
    no_show = "no_show"


class Event(Base, TimestampMixin):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    # The program this event belongs to (authorization scope); null = org-level.
    program_id: Mapped[int | None] = mapped_column(ForeignKey("program.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="event", nullable=False)  # event|project|maintenance
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # Opt-in publishing: only public, active events appear on the public site/calendar.
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    shifts: Mapped[list[Shift]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Shift(Base, TimestampMixin):
    __tablename__ = "shift"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    event: Mapped[Event] = relationship(back_populates="shifts")
    roles: Mapped[list[ShiftRole]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )

    def overlaps(self, other: Shift) -> bool:
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at


class ShiftRole(Base, TimestampMixin):
    __tablename__ = "shift_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shift.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Eligibility: volunteers must hold a non-expired qualification of this type (nullable).
    required_qualification_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("qualification_type.id")
    )
    # Eligibility: volunteers must also hold a cleared, non-expired background check.
    requires_background_check: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    shift: Mapped[Shift] = relationship(back_populates="roles")
    signups: Mapped[list[ShiftSignup]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )

    OCCUPYING = (SignupStatus.confirmed, SignupStatus.attended)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for s in self.signups if s.status in self.OCCUPYING)

    @property
    def seats_available(self) -> bool:
        return self.confirmed_count < self.capacity


class ShiftSignup(Base, TimestampMixin):
    __tablename__ = "shift_signup"
    __table_args__ = (
        UniqueConstraint("shift_role_id", "volunteer_profile_id", name="uq_shift_signup_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    shift_role_id: Mapped[int] = mapped_column(ForeignKey("shift_role.id"), nullable=False)
    volunteer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("volunteer_profile.id"), nullable=False
    )
    status: Mapped[SignupStatus] = mapped_column(default=SignupStatus.confirmed, nullable=False)
    waitlist_position: Mapped[int | None] = mapped_column(Integer)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)  # a reminder was sent
    no_show: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    role: Mapped[ShiftRole] = relationship(back_populates="signups")


class VolunteerHourEntry(Base, TimestampMixin):
    __tablename__ = "volunteer_hour_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    volunteer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("volunteer_profile.id"), nullable=False
    )
    shift_signup_id: Mapped[int | None] = mapped_column(ForeignKey("shift_signup.id"))
    source: Mapped[str] = mapped_column(String(30), default="shift", nullable=False)
    hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
