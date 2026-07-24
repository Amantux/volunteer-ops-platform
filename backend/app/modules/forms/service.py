"""Forms service: definition/version lifecycle + validated, snapshotted submissions.

Submitting validates answers server-side, freezes a copy of the exact schema version filled, and
(if the form binds a workflow) starts a workflow instance for the new submission. Serialization is
visibility-filtered: an `internal` field never reaches a public/volunteer caller.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.modules.workflows import service as workflows

from .models import (
    FormDefinition,
    FormSubmission,
    FormVersion,
    SubmissionStatus,
    VersionStatus,
    Visibility,
    visible_to,
)
from .validation import ValidationError, validate, validate_schema


class FormError(Exception):
    pass


def _definition(db: Session, org_id: int, key: str) -> FormDefinition:
    d = db.scalar(select(FormDefinition).where(
        FormDefinition.org_id == org_id, FormDefinition.key == key))
    if d is None:
        raise FormError(f"form not found: {key}")
    return d


def _definition_by_id(db: Session, org_id: int, def_id: int) -> FormDefinition:
    d = db.get(FormDefinition, def_id)
    if d is None or d.org_id != org_id:
        raise FormError("form not found")
    return d


def create_definition(db: Session, *, org_id: int, key: str, name: str, purpose: str = "",
                      default_visibility: str = "internal", workflow_key: str = "") -> FormDefinition:
    if db.scalar(select(FormDefinition).where(
            FormDefinition.org_id == org_id, FormDefinition.key == key)) is not None:
        raise FormError("a form with that key already exists")
    d = FormDefinition(org_id=org_id, key=key, name=name, purpose=purpose,
                       default_visibility=Visibility(default_visibility), workflow_key=workflow_key)
    db.add(d)
    db.flush()
    return d


def create_draft_version(db: Session, *, org_id: int, def_id: int, schema: dict) -> FormVersion:
    d = _definition_by_id(db, org_id, def_id)
    try:
        validate_schema(schema)
    except ValidationError as exc:
        raise FormError(str(exc)) from exc
    latest = db.scalar(select(FormVersion).where(FormVersion.form_definition_id == d.id)
                       .order_by(FormVersion.version.desc()))
    version = (latest.version + 1) if latest else 1
    fv = FormVersion(org_id=org_id, form_definition_id=d.id, version=version, schema=schema,
                     status=VersionStatus.draft)
    db.add(fv)
    db.flush()
    return fv


def publish_version(db: Session, *, org_id: int, def_id: int, version: int,
                    actor_user_id: int | None) -> FormVersion:
    from app.core.db import utcnow
    d = _definition_by_id(db, org_id, def_id)
    fv = db.scalar(select(FormVersion).where(
        FormVersion.form_definition_id == d.id, FormVersion.version == version))
    if fv is None:
        raise FormError("version not found")
    if fv.status != VersionStatus.draft:
        raise FormError("only a draft version can be published")
    # Retire any currently-published version — published rows are otherwise immutable.
    for other in db.scalars(select(FormVersion).where(
            FormVersion.form_definition_id == d.id,
            FormVersion.status == VersionStatus.published)):
        other.status = VersionStatus.retired
    fv.status = VersionStatus.published
    fv.published_at = utcnow()
    fv.published_by_user_id = actor_user_id
    db.flush()
    audit.emit(db, org_id=org_id, action="form.publish_version", actor_id=actor_user_id or "",
               target_type="form_version", target_id=fv.id, meta={"key": d.key, "version": version})
    return fv


def _published_version(db: Session, d: FormDefinition) -> FormVersion:
    fv = db.scalar(select(FormVersion).where(
        FormVersion.form_definition_id == d.id, FormVersion.status == VersionStatus.published))
    if fv is None:
        raise FormError("form has no published version")
    return fv


def _filter_schema(schema: dict, caller: Visibility) -> dict:
    return {"fields": [f for f in schema.get("fields", [])
                       if visible_to(f.get("visibility", "internal"), caller)]}


def get_form_for_submission(db: Session, *, org_id: int, key: str, caller: Visibility) -> dict:
    d = _definition(db, org_id, key)
    fv = _published_version(db, d)
    return {"key": d.key, "name": d.name, "purpose": d.purpose,
            "schema": _filter_schema(fv.schema, caller)}


def submit(db: Session, *, org_id: int, key: str, answers: dict,
           caller: Visibility = Visibility.volunteer,
           submitter_person_id: int | None = None,
           submitter_user_id: int | None = None) -> FormSubmission:
    d = _definition(db, org_id, key)
    fv = _published_version(db, d)
    # A submitter can only write fields at or below their visibility class — an internal field
    # can never be set by a public/volunteer POST, even if its key is sent directly.
    fields = {f["key"]: f for f in fv.schema.get("fields", []) if isinstance(f, dict)}
    answers = {k: v for k, v in answers.items()
               if k in fields and visible_to(fields[k].get("visibility", "internal"), caller)}
    try:
        cleaned = validate(fv.schema, answers)
    except ValidationError as exc:
        raise FormError(str(exc)) from exc
    sub = FormSubmission(
        org_id=org_id, form_definition_id=d.id, form_version_id=fv.id,
        schema_snapshot=fv.schema, answers=cleaned, status=SubmissionStatus.submitted,
        submitter_person_id=submitter_person_id, submitter_user_id=submitter_user_id)
    db.add(sub)
    db.flush()
    if d.workflow_key:
        inst = workflows.start_instance(
            db, org_id=org_id, definition_key=d.workflow_key, subject_type="form_submission",
            subject_id=sub.id, actor_id=str(submitter_user_id or ""))
        sub.workflow_instance_id = inst.id
        db.flush()
    return sub


def get_submission(db: Session, *, org_id: int, submission_id: int,
                   caller: Visibility) -> FormSubmission:
    sub = db.get(FormSubmission, submission_id)
    if sub is None or sub.org_id != org_id:
        raise FormError("submission not found")
    return sub


def submission_view(sub: FormSubmission, caller: Visibility) -> dict:
    """Serialize a submission with answers filtered to the caller's visibility class — an
    internal field never appears (not even as a null key) for a public/volunteer caller."""
    fields = {f["key"]: f for f in sub.schema_snapshot.get("fields", []) if isinstance(f, dict)}
    answers = {k: v for k, v in sub.answers.items()
               if visible_to(fields.get(k, {}).get("visibility", "internal"), caller)}
    return {
        "id": sub.id,
        "status": sub.status.value,
        "answers": answers,
        "workflow_instance_id": sub.workflow_instance_id,
    }


def list_submissions(db: Session, *, org_id: int, key: str | None = None) -> list[FormSubmission]:
    stmt = select(FormSubmission).where(FormSubmission.org_id == org_id)
    if key:
        d = _definition(db, org_id, key)
        stmt = stmt.where(FormSubmission.form_definition_id == d.id)
    return list(db.scalars(stmt.order_by(FormSubmission.id.desc())))
