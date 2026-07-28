"""Forms engine: definitions, immutable versions, and submissions.

A FormDefinition is the stable identity; each edit publishes a new immutable FormVersion. A
FormSubmission stores a full *snapshot* of the version's schema it was filled against, so a
submission is self-describing and audit-reproducible even if the definition is later changed or
archived. Field schema lives as JSON (read/written as a whole version), never a per-field table.
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


class Visibility(str, enum.Enum):
    public = "public"
    volunteer = "volunteer"
    internal = "internal"


# Who may see less should never see more: ordering for the serialization boundary.
_ORDER = {Visibility.public: 0, Visibility.volunteer: 1, Visibility.internal: 2}


def visible_to(field_visibility: str, caller: Visibility) -> bool:
    """True if a caller of class `caller` may see a field marked `field_visibility`."""
    try:
        fv = Visibility(field_visibility)
    except ValueError:
        fv = Visibility.internal  # unknown → most restrictive
    return _ORDER[caller] >= _ORDER[fv]


class FormDefinitionStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class VersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    retired = "retired"


class SubmissionStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class FormDefinition(Base, TimestampMixin):
    __tablename__ = "form_definition"
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_form_definition_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    default_visibility: Mapped[Visibility] = mapped_column(default=Visibility.internal,
                                                           nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    # Optional submit acknowledgement: email `ack_template_key` to the address in the answer field
    # named `ack_recipient_field` as soon as the form is submitted. Both empty = no ack.
    ack_template_key: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    ack_recipient_field: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[FormDefinitionStatus] = mapped_column(default=FormDefinitionStatus.active,
                                                         nullable=False)


class FormVersion(Base, TimestampMixin):
    """An IMMUTABLE published snapshot of a form's field schema. Editing a published form creates
    a new version; published rows are never mutated."""

    __tablename__ = "form_version"
    __table_args__ = (
        UniqueConstraint("org_id", "form_definition_id", "version", name="uq_form_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    form_definition_id: Mapped[int] = mapped_column(ForeignKey("form_definition.id"),
                                                    nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(default=VersionStatus.draft, nullable=False)
    schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))


class FormSubmission(Base, TimestampMixin):
    __tablename__ = "form_submission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    form_definition_id: Mapped[int] = mapped_column(ForeignKey("form_definition.id"),
                                                    nullable=False, index=True)
    form_version_id: Mapped[int] = mapped_column(ForeignKey("form_version.id"), nullable=False)
    # Frozen copy of the schema the submitter actually filled — self-describing + audit-safe.
    schema_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    submitter_person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    submitter_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    answers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(default=SubmissionStatus.submitted,
                                                     nullable=False)
    workflow_instance_id: Mapped[int | None] = mapped_column(Integer)
