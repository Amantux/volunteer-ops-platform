"""Training: courses, sessions, registrations, waitlist, attendance."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class RegistrationStatus(str, enum.Enum):
    registered = "registered"      # created, email may be unverified
    confirmed = "confirmed"        # verified + holds a seat
    waitlisted = "waitlisted"
    cancelled = "cancelled"        # cancelled by the person/coordinator
    expired = "expired"            # unverified hold reclaimed by the system
    attended = "attended"
    completed = "completed"
    no_show = "no_show"


class Course(Base, TimestampMixin):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # QualificationType granted on completion (nullable).
    grants_qualification_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("qualification_type.id")
    )

    sessions: Mapped[list[TrainingSession]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class TrainingSession(Base, TimestampMixin):
    __tablename__ = "training_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id"), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    location: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)  # null = unlimited
    trainer_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    course: Mapped[Course] = relationship(back_populates="sessions")
    registrations: Mapped[list[TrainingRegistration]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    # Statuses that occupy a seat (a provisional "registered" holds one until verified/cancelled).
    OCCUPYING = (
        RegistrationStatus.registered,
        RegistrationStatus.confirmed,
        RegistrationStatus.attended,
        RegistrationStatus.completed,
    )

    @property
    def occupied_count(self) -> int:
        return sum(1 for r in self.registrations if r.status in self.OCCUPYING)

    @property
    def seats_available(self) -> bool:
        return self.capacity is None or self.occupied_count < self.capacity

    def next_waitlist_position(self) -> int:
        positions = [r.waitlist_position or 0 for r in self.registrations if r.waitlist_position]
        return (max(positions) + 1) if positions else 1


class TrainingRegistration(Base, TimestampMixin):
    __tablename__ = "training_registration"
    __table_args__ = (
        UniqueConstraint("session_id", "person_id", name="uq_registration_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_session.id"), nullable=False)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        default=RegistrationStatus.registered, nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), default="public", nullable=False)
    waitlist_position: Mapped[int | None] = mapped_column(Integer)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    session: Mapped[TrainingSession] = relationship(back_populates="registrations")
