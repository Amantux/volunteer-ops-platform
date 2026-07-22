"""Identity & access: Person, User, RBAC, and single-use tokens.

Person = a human record (may be a guest with no login). User = an authenticable
identity linked to a Person. This separation makes guest→volunteer conversion clean.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin


class RoleScopeType(str, enum.Enum):
    org = "org"
    program = "program"
    team = "team"
    location = "location"


class Person(Base, TimestampMixin):
    __tablename__ = "person"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_person_org_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str] = mapped_column(String(50), default="", nullable=False)

    user: Mapped[User | None] = relationship(back_populates="person", uselist=False)


class User(Base, TimestampMixin):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    person: Mapped[Person] = relationship(back_populates="user")
    role_assignments: Mapped[list[UserRoleAssignment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Role(Base, TimestampMixin):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_role_org_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "trainer", "org_admin"
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = (UniqueConstraint("role_id", "permission", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)
    permission: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "training.manage_session"

    role: Mapped[Role] = relationship(back_populates="permissions")


class UserRoleAssignment(Base, TimestampMixin):
    """Binds (user, role) with a scope so authority is bounded (org/program/team/location)."""

    __tablename__ = "user_role_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)
    scope_type: Mapped[RoleScopeType] = mapped_column(default=RoleScopeType.org, nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer)  # null = whole org

    user: Mapped[User] = relationship(back_populates="role_assignments")
    role: Mapped[Role] = relationship()


class TokenPurpose(str, enum.Enum):
    email_verification = "email_verification"
    account_activation = "account_activation"


class VerificationToken(Base, TimestampMixin):
    """Single-use, expiring token for email verification and account activation."""

    __tablename__ = "verification_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
