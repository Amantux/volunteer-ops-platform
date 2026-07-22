"""Organization + configuration (the tenant root)."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    settings: Mapped[list[OrganizationSetting]] = relationship(
        back_populates="org", cascade="all, delete-orphan"
    )


class OrganizationSetting(Base, TimestampMixin):
    """Typed key/value config: feature flags, terminology, scheduling/retention policy."""

    __tablename__ = "organization_setting"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_org_setting_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    org: Mapped[Organization] = relationship(back_populates="settings")
