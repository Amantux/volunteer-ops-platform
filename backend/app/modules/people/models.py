"""Volunteer-operational overlay on a Person."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class VolunteerProfile(Base, TimestampMixin):
    __tablename__ = "volunteer_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    # Sensitive: internal-only. Never serialized to a volunteer/public caller — only a
    # privileged endpoint (volunteer.manage_background_check) reads/writes it, audited on change.
    # status: none | requested | cleared | expired
    background_check_status: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False
    )
    background_check_expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    qualifications: Mapped[list[VolunteerQualification]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProgramEnrollment(Base, TimestampMixin):
    """A volunteer's *ongoing* commitment to a program in a role (e.g. puppy_raiser) — distinct
    from a dated shift signup. Short-term roles (e.g. puppy_sitter) still use gated shift slots;
    long-term roles are represented here. One non-terminal enrollment per (profile, program, role)
    is enforced in the service, so historical (completed/withdrawn) enrollments can coexist."""

    __tablename__ = "program_enrollment"
    # At most one *non-terminal* enrollment per (profile, program, role); completed/withdrawn
    # rows are excluded so history can accumulate. Backs the service's idempotency race-safely.
    __table_args__ = (
        Index(
            "uq_active_program_enrollment", "profile_id", "program_id", "role",
            unique=True,
            sqlite_where=text("status NOT IN ('completed', 'withdrawn')"),
            postgresql_where=text("status NOT IN ('completed', 'withdrawn')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("volunteer_profile.id"), nullable=False, index=True
    )
    program_id: Mapped[int] = mapped_column(ForeignKey("program.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. puppy_raiser, puppy_sitter
    # active | paused | completed | withdrawn  (completed/withdrawn are terminal → ended_at set)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class QualificationType(Base, TimestampMixin):
    __tablename__ = "qualification_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    validity_days: Mapped[int | None] = mapped_column(Integer)  # null = never expires


class VolunteerQualification(Base, TimestampMixin):
    __tablename__ = "volunteer_qualification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("volunteer_profile.id"), nullable=False)
    qualification_type_id: Mapped[int] = mapped_column(
        ForeignKey("qualification_type.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(40), default="training", nullable=False)

    profile: Mapped[VolunteerProfile] = relationship(back_populates="qualifications")
