"""Volunteer-operational overlay on a Person."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class VolunteerProfile(Base, TimestampMixin):
    __tablename__ = "volunteer_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    qualifications: Mapped[list[VolunteerQualification]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


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
