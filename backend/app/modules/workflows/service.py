"""Workflow engine service. `perform_transition` is the ONLY way an instance's state changes.

Every transition, in one DB transaction: load (org-scoped) → find legal transition → authorize
(core.authz) → agent risk-gate → evaluate guard → approval gate → apply state + append an
idempotency-keyed event → run governed side-effects (audit + outbox). Notifications never happen
synchronously; they are outbox events with idempotent handlers.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import PermissionDenied, Principal, require, require_scoped
from app.core.db import utcnow
from app.core.outbox import OutboxEvent, enqueue, handler
from app.modules.agents.risk import RiskLevel, classify_action

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    DefinitionStatus,
    InstanceStatus,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTransitionEvent,
)


class WorkflowError(Exception):
    """Illegal transition / bad request (maps to 409)."""


class WorkflowDenied(Exception):
    """Authorization failure (maps to 403)."""


def get_definition(db: Session, *, org_id: int, key: str) -> WorkflowDefinition:
    d = db.scalar(select(WorkflowDefinition).where(
        WorkflowDefinition.org_id == org_id, WorkflowDefinition.key == key,
        WorkflowDefinition.status == DefinitionStatus.active))
    if d is None:
        raise WorkflowError(f"workflow not found: {key}")
    return d


def _state(definition: WorkflowDefinition, name: str) -> dict:
    for s in definition.states:
        if isinstance(s, dict) and s.get("name") == name:
            return s
    return {}


def _deadline_for(definition: WorkflowDefinition, state: str):
    sla = _state(definition, state).get("sla_hours")
    return utcnow() + timedelta(hours=sla) if sla else None


def start_instance(db: Session, *, org_id: int, definition_key: str, subject_type: str,
                   subject_id: int, actor_id: str = "") -> WorkflowInstance:
    definition = get_definition(db, org_id=org_id, key=definition_key)
    inst = WorkflowInstance(
        org_id=org_id, workflow_definition_id=definition.id, subject_type=subject_type,
        subject_id=subject_id, current_state=definition.initial_state,
        deadline_at=_deadline_for(definition, definition.initial_state))
    db.add(inst)
    db.flush()
    _run_actions(db, definition, _state(definition, definition.initial_state).get("on_enter", []),
                 inst)
    audit.emit(db, org_id=org_id, action="workflow.start", actor_id=actor_id,
               target_type="workflow_instance", target_id=inst.id,
               meta={"workflow": definition_key, "state": inst.current_state})
    return inst


def _get_instance(db: Session, org_id: int, instance_id: int) -> WorkflowInstance:
    # Lock the instance row on Postgres so two concurrent (different) transitions from the same
    # state can't both commit and violate the state machine. No-op on SQLite (serial tests).
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        inst = db.scalar(select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
                         .with_for_update())
    else:
        inst = db.get(WorkflowInstance, instance_id)
    if inst is None or inst.org_id != org_id:
        raise WorkflowError("workflow instance not found")
    return inst


def _find_transition(definition: WorkflowDefinition, from_state: str, name: str) -> dict:
    for t in definition.transitions:
        if isinstance(t, dict) and t.get("name") == name and t.get("from") == from_state:
            return t
    raise WorkflowError(f"no transition '{name}' from state '{from_state}'")


def _authorize(db: Session, principal: Principal, transition: dict, program_id: int | None) -> None:
    # NOTE (v1 limitation): callers don't yet resolve a subject's program, so a `scope: "program"`
    # transition with program_id=None is satisfiable only by an org-wide grant holder — fail-safe
    # (never over-grants) but a program-scoped coordinator is denied. Deriving program from the
    # subject (e.g. a form answer) is a follow-up. The seeded incident workflow uses org scope.
    perm = transition.get("permission")
    if not perm:
        return  # unguarded transition (e.g. a public submit-driven start)
    try:
        if transition.get("scope") == "program":
            require_scoped(db, principal, perm, program_id=program_id)
        else:
            require(db, principal, perm)
    except PermissionDenied as exc:
        raise WorkflowDenied(str(exc)) from exc


def _guard_ok(transition: dict, context: dict) -> bool:
    g = transition.get("guard")
    if not g:
        return True
    val = context.get(g.get("field"))
    if "eq" in g:
        return val == g["eq"]
    if "neq" in g:
        return val != g["neq"]
    return True


def _run_actions(db: Session, definition: WorkflowDefinition, actions: list,
                 inst: WorkflowInstance) -> None:
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        if "emit_audit" in action:
            audit.emit(db, org_id=inst.org_id, action=str(action["emit_audit"]),
                       target_type="workflow_instance", target_id=inst.id)
        if "notify" in action:
            # Governed, idempotent side-effect via the outbox — never a synchronous send.
            enqueue(db, org_id=inst.org_id, event_type="workflow.notify",
                    idempotency_key=f"wf-notify:{inst.id}:{inst.current_state}:{action['notify']}",
                    payload={"instance_id": inst.id, "message": str(action["notify"])})


def perform_transition(db: Session, principal: Principal, *, instance_id: int,
                       transition_name: str, note: str = "", nonce: str = "",
                       program_id: int | None = None, context: dict | None = None,
                       actor_type: str = "user") -> WorkflowInstance:
    inst = _get_instance(db, principal.org_id, instance_id)
    definition = db.get(WorkflowDefinition, inst.workflow_definition_id)
    assert definition is not None
    transition = _find_transition(definition, inst.current_state, transition_name)

    _authorize(db, principal, transition, program_id)

    # Agents get no privileged path: an agent may not execute an approval-required / prohibited
    # transition — it can only surface it for a human (the ApprovalRequest below / a proposal).
    action_key = transition.get("action", transition_name)
    if actor_type == "agent" and classify_action(action_key) in (
            RiskLevel.r3_approval, RiskLevel.r4_prohibited):
        raise WorkflowDenied("agents cannot execute an approval-required or prohibited transition")

    if not _guard_ok(transition, context or {}):
        raise WorkflowError("transition guard not satisfied")

    approved = None
    if transition.get("requires_approval"):
        # An approval must be approved AND not yet consumed — a single approval authorizes exactly
        # one execution of the gated transition (matters for cyclic workflows).
        approved = db.scalar(select(ApprovalRequest).where(
            ApprovalRequest.workflow_instance_id == inst.id,
            ApprovalRequest.transition_name == transition_name,
            ApprovalRequest.status == ApprovalStatus.approved,
            ApprovalRequest.consumed_at.is_(None)))
        if approved is None:
            existing = db.scalar(select(ApprovalRequest).where(
                ApprovalRequest.workflow_instance_id == inst.id,
                ApprovalRequest.transition_name == transition_name,
                ApprovalRequest.status == ApprovalStatus.pending))
            if existing is None:
                db.add(ApprovalRequest(
                    org_id=inst.org_id, workflow_instance_id=inst.id,
                    transition_name=transition_name,
                    required_permission=transition.get("permission", ""),
                    required_scope=transition.get("scope", "org"),
                    deadline_at=_deadline_for(definition, inst.current_state)))
                db.flush()
            return inst  # state unchanged — awaiting human approval

    from_state = inst.current_state
    to_state = transition["to"]
    # Append the history event; the unique idempotency key makes a double-fire a no-op.
    sp = db.begin_nested()
    try:
        db.add(WorkflowTransitionEvent(
            org_id=inst.org_id, workflow_instance_id=inst.id, transition_name=transition_name,
            from_state=from_state, to_state=to_state, actor_type=actor_type,
            actor_id=str(principal.user_id), note=note[:500],
            idempotency_key=f"{inst.id}:{from_state}:{transition_name}:{nonce}"))
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        return inst  # already performed (idempotent)

    inst.current_state = to_state
    inst.deadline_at = _deadline_for(definition, to_state)
    if _state(definition, to_state).get("is_terminal"):
        inst.status = InstanceStatus.closed
    if approved is not None:
        approved.consumed_at = utcnow()  # spend the approval — not reusable on a later pass
    _run_actions(db, definition, transition.get("entry_actions", []), inst)
    audit.emit(db, org_id=inst.org_id, action="workflow.transition",
               actor_id=principal.user_id, target_type="workflow_instance", target_id=inst.id,
               meta={"transition": transition_name, "from": from_state, "to": to_state})
    db.flush()
    return inst


def decide_approval(db: Session, principal: Principal, *, approval_id: int,
                    approve: bool, note: str = "") -> WorkflowInstance:
    ar = db.get(ApprovalRequest, approval_id)
    if ar is None or ar.org_id != principal.org_id:
        raise WorkflowError("approval request not found")
    if ar.status != ApprovalStatus.pending:
        raise WorkflowError("approval already decided")
    # The decider must hold the transition's required permission (+ scope).
    inst = _get_instance(db, principal.org_id, ar.workflow_instance_id)
    try:
        if ar.required_scope == "program":
            require_scoped(db, principal, ar.required_permission, program_id=None)
        else:
            require(db, principal, ar.required_permission)
    except PermissionDenied as exc:
        raise WorkflowDenied(str(exc)) from exc
    ar.decided_by_user_id = principal.user_id
    ar.decided_at = utcnow()
    ar.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    db.flush()
    if approve:
        # Approval recorded → perform the gated transition now (it will find the approved request).
        return perform_transition(db, principal, instance_id=inst.id,
                                  transition_name=ar.transition_name, note=note,
                                  nonce=f"approval-{ar.id}")
    return inst


def allowed_transitions(db: Session, principal: Principal, inst: WorkflowInstance) -> list[dict]:
    """Transitions legal from the current state that this caller is permitted to perform (UX)."""
    definition = db.get(WorkflowDefinition, inst.workflow_definition_id)
    assert definition is not None
    out = []
    for t in definition.transitions:
        if not isinstance(t, dict) or t.get("from") != inst.current_state:
            continue
        perm = t.get("permission")
        if perm:
            from app.core.authz import has_permission
            if not has_permission(db, principal, perm):
                continue
        out.append({"name": t["name"], "to": t["to"],
                    "requires_approval": bool(t.get("requires_approval"))})
    return out


def sweep_deadlines(db: Session) -> int:
    """Beat task: enqueue an escalation for instances/approvals past their deadline. Idempotent —
    the outbox key encodes the instance + deadline window, so a double-run does not double-notify."""
    now = utcnow()
    count = 0
    overdue = db.scalars(select(WorkflowInstance).where(
        WorkflowInstance.status == InstanceStatus.open,
        WorkflowInstance.deadline_at.is_not(None),
        WorkflowInstance.deadline_at <= now)).all()
    for inst in overdue:
        assert inst.deadline_at is not None  # filtered by the query above
        ev = enqueue(db, org_id=inst.org_id, event_type="workflow.notify",
                     idempotency_key=f"wf-escalate:{inst.id}:{inst.deadline_at.isoformat()}",
                     payload={"instance_id": inst.id, "message": "escalation: past SLA"})
        if ev is not None:
            count += 1
    return count


@handler("workflow.notify")
def _notify(db: Session, event: OutboxEvent) -> None:
    """Idempotent notification side-effect. v1 records an auditable notification; wiring it to a
    real email template/recipient is a follow-up (kept out of the request path deliberately)."""
    audit.emit(db, org_id=event.org_id, action="workflow.notified", actor_type="service",
               target_type="workflow_instance", target_id=int(event.payload["instance_id"]),
               meta={"message": event.payload.get("message", "")})
