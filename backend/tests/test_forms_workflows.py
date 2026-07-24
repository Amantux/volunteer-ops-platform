"""Forms + workflow engine: incident flow, immutable versioning, authz, visibility, idempotency."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.authz import Principal
from app.modules.forms import service as forms
from app.modules.forms.models import FormSubmission, Visibility
from app.modules.workflows import service as workflows
from app.modules.workflows.models import (
    ApprovalRequest,
    ApprovalStatus,
    WorkflowInstance,
    WorkflowTransitionEvent,
)


def _user_with_perms(db, org, perms, email):
    from app.core.session import make_session_token
    from app.modules.identity.models import (
        Person,
        Role,
        RolePermission,
        User,
        UserRoleAssignment,
    )
    role = Role(org_id=org.id, key=f"role_{email}", label="T")
    db.add(role)
    db.flush()
    for p in perms:
        db.add(RolePermission(role_id=role.id, permission=p))
    person = Person(org_id=org.id, name=email, email=email, email_verified=True)
    db.add(person)
    db.flush()
    user = User(org_id=org.id, person_id=person.id)
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(org_id=org.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {"Authorization": f"Bearer {make_session_token(user_id=user.id, org_id=org.id)}"}


# --- Public submission + visibility ----------------------------------------- #

def test_public_form_hides_internal_fields(client):
    schema = client.get("/api/forms/incident_report").json()["schema"]
    keys = {f["key"] for f in schema["fields"]}
    assert "category" in keys and "description" in keys
    assert "severity" not in keys and "internal_notes" not in keys  # internal → never rendered


def test_submit_creates_workflow_instance_in_initial_state(client, db):
    r = client.post("/api/forms/incident_report/submissions",
                    json={"answers": {"category": "safety", "description": "wet floor by door 3"}})
    assert r.status_code == 201
    sub = db.get(FormSubmission, r.json()["id"])
    assert sub.workflow_instance_id is not None
    inst = db.get(WorkflowInstance, sub.workflow_instance_id)
    assert inst.current_state == "reported"


def test_public_cannot_write_internal_field(client, db):
    # A public POST that includes an internal field key must have it dropped, not stored.
    r = client.post("/api/forms/incident_report/submissions",
                    json={"answers": {"category": "safety", "description": "x",
                                      "internal_notes": "i should not persist",
                                      "severity": "critical"}})
    sub = db.get(FormSubmission, r.json()["id"])
    assert "internal_notes" not in sub.answers and "severity" not in sub.answers


def test_required_field_rejected(client):
    r = client.post("/api/forms/incident_report/submissions",
                    json={"answers": {"category": "safety"}})  # missing required description
    assert r.status_code == 422 and "description" in r.json()["detail"]


def test_submission_view_filters_by_caller():
    # Unit-level: an internal answer serializes for a reviewer but not for the public submitter.
    class _Sub:
        schema_snapshot = {"fields": [{"key": "a", "visibility": "public"},
                                      {"key": "n", "visibility": "internal"}]}
        answers = {"a": "shown", "n": "secret"}
        id = 1
        status = type("S", (), {"value": "submitted"})()
        workflow_instance_id = None
    pub = forms.submission_view(_Sub(), Visibility.public)
    internal = forms.submission_view(_Sub(), Visibility.internal)
    assert pub["answers"] == {"a": "shown"}
    assert internal["answers"] == {"a": "shown", "n": "secret"}


# --- Workflow lifecycle + governance ---------------------------------------- #

def _new_incident(client):
    return client.post("/api/forms/incident_report/submissions",
                       json={"answers": {"category": "facility", "description": "broken light"}}
                       ).json()["id"]


def test_incident_lifecycle_with_approval_gate(client, db, admin_headers):
    sid = _new_incident(client)
    iid = db.get(FormSubmission, sid).workflow_instance_id

    def transition(name):
        return client.post(f"/api/instances/{iid}/transitions/{name}", headers=admin_headers,
                           json={"note": ""})
    assert transition("triage").json()["current_state"] == "needs_triage"
    assert transition("start").json()["current_state"] == "in_progress"
    # resolve requires approval → state does NOT change, an ApprovalRequest is created.
    assert transition("resolve").json()["current_state"] == "in_progress"
    ar = db.scalar(select(ApprovalRequest).where(ApprovalRequest.workflow_instance_id == iid))
    assert ar is not None and ar.status == ApprovalStatus.pending

    # Deciding the approval performs the gated transition.
    out = client.post(f"/api/approvals/{ar.id}/decide", headers=admin_headers,
                      json={"approve": True}).json()
    assert out["current_state"] == "resolved" and out["status"] == "closed"


def test_transition_requires_the_declared_permission(client, db, org):
    sid = _new_incident(client)
    iid = db.get(FormSubmission, sid).workflow_instance_id
    # A user without incident.triage cannot triage.
    headers = _user_with_perms(db, org, ["forms.review"], "noperm@x.org")
    r = client.post(f"/api/instances/{iid}/transitions/triage", headers=headers, json={"note": ""})
    assert r.status_code == 403


def test_transition_is_idempotent(client, db, admin_headers):
    sid = _new_incident(client)
    iid = db.get(FormSubmission, sid).workflow_instance_id
    h = {**admin_headers, "Idempotency-Key": "abc123"}
    client.post(f"/api/instances/{iid}/transitions/triage", headers=h, json={"note": ""})
    client.post(f"/api/instances/{iid}/transitions/triage", headers=h, json={"note": ""})
    events = db.scalar(select(func.count()).select_from(WorkflowTransitionEvent).where(
        WorkflowTransitionEvent.workflow_instance_id == iid,
        WorkflowTransitionEvent.transition_name == "triage"))
    assert events == 1  # the second call deduped
    assert db.get(WorkflowInstance, iid).current_state == "needs_triage"


def test_agent_cannot_execute_approval_required_transition(client, db, org, admin_user):
    sid = _new_incident(client)
    iid = db.get(FormSubmission, sid).workflow_instance_id
    principal = Principal(user_id=admin_user.id, org_id=org.id)
    workflows.perform_transition(db, principal, instance_id=iid, transition_name="triage")
    workflows.perform_transition(db, principal, instance_id=iid, transition_name="start")
    # 'resolve' maps to work.close (R3). An agent actor is refused.
    with pytest.raises(workflows.WorkflowDenied):
        workflows.perform_transition(db, principal, instance_id=iid, transition_name="resolve",
                                     actor_type="agent")


def test_cross_org_instance_is_404(client, db, org, admin_headers):
    from app.modules.org.models import Organization
    other = Organization(name="Other", slug="other-social")
    db.add(other)
    db.flush()
    inst = WorkflowInstance(org_id=other.id, workflow_definition_id=1, subject_type="x",
                            subject_id=1, current_state="reported")
    db.add(inst)
    db.commit()
    assert client.get(f"/api/instances/{inst.id}", headers=admin_headers).status_code == 404


# --- Immutable versioning + deadline sweep ---------------------------------- #

def test_publishing_a_new_version_does_not_change_past_submissions(client, db, org, admin_headers):
    did = client.post("/api/admin/forms", headers=admin_headers,
                      json={"key": "feedback", "name": "Feedback",
                            "default_visibility": "volunteer"}).json()["id"]
    client.post(f"/api/admin/forms/{did}/versions", headers=admin_headers,
                json={"schema": {"fields": [{"key": "rating", "type": "number", "label": "Rating",
                                             "visibility": "public"}]}})
    client.post(f"/api/admin/forms/{did}/versions/1/publish", headers=admin_headers)
    sub1 = client.post("/api/forms/feedback/submissions", json={"answers": {"rating": 5}}).json()["id"]

    # Edit → a NEW version with a different schema; publish it.
    client.post(f"/api/admin/forms/{did}/versions", headers=admin_headers,
                json={"schema": {"fields": [{"key": "rating", "type": "number", "label": "Rating",
                                             "visibility": "public"},
                                            {"key": "comment", "type": "text", "label": "Comment",
                                             "visibility": "public"}]}})
    client.post(f"/api/admin/forms/{did}/versions/2/publish", headers=admin_headers)

    # The old submission's frozen snapshot is unchanged (still the 1-field v1 schema).
    snap1 = db.get(FormSubmission, sub1).schema_snapshot
    assert [f["key"] for f in snap1["fields"]] == ["rating"]


def test_deadline_sweep_is_idempotent(client, db):
    from datetime import timedelta

    from app.core.db import utcnow
    from app.core.outbox import OutboxEvent
    sid = _new_incident(client)
    inst = db.get(WorkflowInstance, db.get(FormSubmission, sid).workflow_instance_id)
    inst.deadline_at = utcnow() - timedelta(hours=1)  # overdue
    db.commit()
    workflows.sweep_deadlines(db)
    workflows.sweep_deadlines(db)
    db.commit()
    escalations = db.scalar(select(func.count()).select_from(OutboxEvent).where(
        OutboxEvent.idempotency_key.like(f"wf-escalate:{inst.id}:%")))
    assert escalations == 1  # double-run did not double-notify
