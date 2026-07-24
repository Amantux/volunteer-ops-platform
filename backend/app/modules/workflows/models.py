"""Workflow engine: reusable state machines bound polymorphically to any subject record.

A WorkflowDefinition is a declarative state machine (states + transitions as JSON — no code).
A WorkflowInstance is one live run bound to a subject (a form submission, a volunteer profile).
Transitions are the ONLY way current_state changes; each writes an append-only, idempotency-keyed
event and runs governed side-effects (audit + outbox). Approvals gate consequential transitions.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class DefinitionStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class InstanceStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class WorkflowDefinition(Base, TimestampMixin):
    __tablename__ = "workflow_definition"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_workflow_definition_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    initial_state: Mapped[str] = mapped_column(String(60), nullable=False)
    states: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    transitions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[DefinitionStatus] = mapped_column(default=DefinitionStatus.active,
                                                     nullable=False)


class WorkflowInstance(Base, TimestampMixin):
    __tablename__ = "workflow_instance"
    __table_args__ = (
        UniqueConstraint("org_id", "workflow_definition_id", "subject_type", "subject_id",
                         name="uq_workflow_instance_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    workflow_definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definition.id"),
                                                        nullable=False)
    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_state: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[InstanceStatus] = mapped_column(default=InstanceStatus.open, nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkflowTransitionEvent(Base, TimestampMixin):
    """Append-only transition history. The unique idempotency key dedups a double-fired transition."""

    __tablename__ = "workflow_transition_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    workflow_instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instance.id"),
                                                      nullable=False, index=True)
    transition_name: Mapped[str] = mapped_column(String(80), nullable=False)
    from_state: Mapped[str] = mapped_column(String(60), nullable=False)
    to_state: Mapped[str] = mapped_column(String(60), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    actor_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    note: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "workflow_approval_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    workflow_instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instance.id"),
                                                      nullable=False, index=True)
    transition_name: Mapped[str] = mapped_column(String(80), nullable=False)
    required_permission: Mapped[str] = mapped_column(String(80), nullable=False)
    required_scope: Mapped[str] = mapped_column(String(20), default="org", nullable=False)
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[ApprovalStatus] = mapped_column(default=ApprovalStatus.pending, nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
