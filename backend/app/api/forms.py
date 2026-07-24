"""Forms + workflow endpoints: admin definition CRUD, public submission, and transitions.

Public submission is rate-limited + bot-checked. Transitions enforce their OWN declared permission
inside the engine (`workflows.service.perform_transition`), so the route only requires an
authenticated principal; the engine is the authorization boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import botcheck, ratelimit
from app.core.authz import Principal
from app.modules.forms import service as forms
from app.modules.forms.models import Visibility
from app.modules.forms.service import FormError
from app.modules.org.models import Organization
from app.modules.workflows import service as workflows
from app.modules.workflows.service import WorkflowDenied, WorkflowError

from .deps import current_principal, get_db, get_public_org, require_permission

admin = APIRouter(prefix="/api/admin", tags=["forms-admin"])
public = APIRouter(prefix="/api", tags=["forms"])


class IdOut(BaseModel):
    id: int


class FormIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    purpose: str = ""
    default_visibility: str = "internal"
    workflow_key: str = ""


class VersionIn(BaseModel):
    schema_def: dict = Field(alias="schema")

    model_config = {"populate_by_name": True}


class WorkflowIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    subject_type: str = "form_submission"
    initial_state: str
    states: list = Field(default_factory=list)
    transitions: list = Field(default_factory=list)


class SubmitIn(BaseModel):
    answers: dict = Field(default_factory=dict)
    bot_token: str | None = None


class TransitionIn(BaseModel):
    note: str = ""


class DecideIn(BaseModel):
    approve: bool
    note: str = ""


# --- Admin: definitions ----------------------------------------------------- #

@admin.post("/forms", response_model=IdOut, status_code=201)
def create_form(payload: FormIn, db: Session = Depends(get_db),
                principal: Principal = Depends(require_permission("forms.admin"))):
    try:
        d = forms.create_definition(db, org_id=principal.org_id, key=payload.key, name=payload.name,
                                    purpose=payload.purpose,
                                    default_visibility=payload.default_visibility,
                                    workflow_key=payload.workflow_key)
    except (FormError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=d.id)


@admin.post("/forms/{def_id}/versions", status_code=201)
def create_version(def_id: int, payload: VersionIn, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("forms.admin"))):
    try:
        fv = forms.create_draft_version(db, org_id=principal.org_id, def_id=def_id,
                                        schema=payload.schema_def)
    except FormError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"id": fv.id, "version": fv.version}


@admin.post("/forms/{def_id}/versions/{version}/publish", response_model=IdOut)
def publish_version(def_id: int, version: int, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("forms.admin"))):
    try:
        fv = forms.publish_version(db, org_id=principal.org_id, def_id=def_id, version=version,
                                   actor_user_id=principal.user_id)
    except FormError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=fv.id)


@admin.post("/workflows", response_model=IdOut, status_code=201)
def create_workflow(payload: WorkflowIn, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_permission("workflows.admin"))):
    from app.modules.workflows.models import WorkflowDefinition
    wd = WorkflowDefinition(org_id=principal.org_id, key=payload.key, name=payload.name,
                            subject_type=payload.subject_type, initial_state=payload.initial_state,
                            states=payload.states, transitions=payload.transitions)
    db.add(wd)
    db.commit()
    return IdOut(id=wd.id)


# --- Public / volunteer: submission ----------------------------------------- #

@public.get("/forms/{key}")
def get_form(key: str, db: Session = Depends(get_db),
             org: Organization = Depends(get_public_org)):
    """The published, submitter-facing schema. This route is UNAUTHENTICATED, so the caller is
    `public` — a volunteer-tier field is not rendered here (a volunteer form needs an authed path)."""
    try:
        return forms.get_form_for_submission(db, org_id=org.id, key=key, caller=Visibility.public)
    except FormError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@public.post("/forms/{key}/submissions", response_model=IdOut, status_code=201)
def submit_form(key: str, payload: SubmitIn, request: Request, db: Session = Depends(get_db),
                org: Organization = Depends(get_public_org)):
    client = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"formsubmit:{client}", limit=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many submissions. Please try again shortly.")
    if not botcheck.verify(payload.bot_token, remote_ip=client):
        raise HTTPException(status_code=400, detail="Bot check failed. Please try again.")
    try:
        # Unauthenticated route → the submitter is `public`; a volunteer/internal field can't be
        # written here even if its key is POSTed directly.
        sub = forms.submit(db, org_id=org.id, key=key, answers=payload.answers,
                           caller=Visibility.public)
    except FormError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return IdOut(id=sub.id)


# --- Review: submissions, instances, transitions, approvals ----------------- #

@public.get("/submissions")
def list_submissions(key: str | None = None, db: Session = Depends(get_db),
                     principal: Principal = Depends(require_permission("forms.review"))):
    subs = forms.list_submissions(db, org_id=principal.org_id, key=key)
    return [forms.submission_view(s, Visibility.internal) for s in subs]


@public.get("/submissions/{submission_id}")
def get_submission(submission_id: int, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_permission("forms.review"))):
    try:
        sub = forms.get_submission(db, org_id=principal.org_id, submission_id=submission_id,
                                   caller=Visibility.internal)
    except FormError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return forms.submission_view(sub, Visibility.internal)


@public.get("/instances/{instance_id}")
def get_instance(instance_id: int, db: Session = Depends(get_db),
                 principal: Principal = Depends(require_permission("forms.review"))):
    try:
        inst = workflows._get_instance(db, principal.org_id, instance_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": inst.id, "current_state": inst.current_state, "status": inst.status.value,
            "deadline_at": inst.deadline_at.isoformat() if inst.deadline_at else None,
            "allowed_transitions": workflows.allowed_transitions(db, principal, inst)}


@public.post("/instances/{instance_id}/transitions/{name}")
def do_transition(instance_id: int, name: str, payload: TransitionIn,
                  request: Request, db: Session = Depends(get_db),
                  principal: Principal = Depends(current_principal)):
    # The transition's OWN permission is enforced inside the engine.
    nonce = request.headers.get("Idempotency-Key", "")
    try:
        inst = workflows.perform_transition(db, principal, instance_id=instance_id,
                                            transition_name=name, note=payload.note, nonce=nonce)
    except WorkflowDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": inst.id, "current_state": inst.current_state, "status": inst.status.value}


@public.post("/approvals/{approval_id}/decide")
def decide(approval_id: int, payload: DecideIn, db: Session = Depends(get_db),
           principal: Principal = Depends(current_principal)):
    try:
        inst = workflows.decide_approval(db, principal, approval_id=approval_id,
                                         approve=payload.approve, note=payload.note)
    except WorkflowDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": inst.id, "current_state": inst.current_state, "status": inst.status.value}
