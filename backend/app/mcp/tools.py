"""Governed MCP tool layer.

Narrow, task-oriented tools over application services. Every tool declares a contract
(authorization, risk, approval, reversibility, idempotency, audit event) and enforces
authorization + audit *inside* the tool — never assuming the caller was already checked.
The MCP server transport (stdio/HTTP) wraps `invoke_tool`; the tools never expose raw DB,
shell, secrets, or cross-org access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.authz import PermissionDenied, Principal, require
from app.modules.agents.models import AgentProposal, ProposalStatus
from app.modules.agents.risk import RiskLevel
from app.modules.social import service as social
from app.modules.social.models import PostSource
from app.modules.training.models import TrainingSession
from app.modules.training.service import (
    TrainingError,
    propose_waitlist_promotion,
    register_guest,
    training_funnel,
)


@dataclass(frozen=True)
class ToolContract:
    name: str
    permission: str
    risk: RiskLevel
    approval_required: bool
    reversible: bool
    idempotent: bool
    audit_action: str
    data_classification: str  # e.g. "Sensitive-PII", "Internal"


class ToolError(Exception):
    pass


_REGISTRY: dict[str, tuple[ToolContract, Callable[[Session, Principal, dict], dict]]] = {}


def tool(contract: ToolContract):
    def register(fn: Callable[[Session, Principal, dict], dict]):
        _REGISTRY[contract.name] = (contract, fn)
        return fn

    return register


def contracts() -> list[ToolContract]:
    return [c for c, _ in _REGISTRY.values()]


def invoke_tool(db: Session, principal: Principal, name: str, args: dict) -> dict:
    """The single governed entry point. Enforces org scope, permission, and audit."""
    entry = _REGISTRY.get(name)
    if entry is None:
        raise ToolError(f"unknown tool: {name}")
    contract, fn = entry
    # Governance gate: prohibited-risk tools never execute through MCP, regardless of
    # permission. Approval-required tools must themselves return a proposal rather than
    # perform the side effect (enforced by the underlying service, e.g. promotion).
    if contract.risk == RiskLevel.r4_prohibited:
        audit.emit(db, org_id=principal.org_id, action="mcp.prohibited", actor_type="agent",
                   actor_id=name, target_type="tool", target_id=name)
        db.commit()
        raise ToolError("prohibited action")
    try:
        require(db, principal, contract.permission)
    except PermissionDenied:
        audit.emit(db, org_id=principal.org_id, action="mcp.denied", actor_type="agent",
                   actor_id=name, target_type="tool", target_id=name)
        db.commit()
        raise ToolError("permission denied") from None
    result = fn(db, principal, args)
    audit.emit(db, org_id=principal.org_id, action=contract.audit_action, actor_type="agent",
               actor_id=name, target_type="tool", target_id=name, meta={"args_keys": list(args)})
    db.commit()
    return result


# --- Tools ------------------------------------------------------------------ #

@tool(ToolContract(
    name="register_training_guest", permission="training.register_guest",
    risk=RiskLevel.r2_low_execute, approval_required=False, reversible=True, idempotent=True,
    audit_action="mcp.register_training_guest", data_classification="Sensitive-PII",
))
def _register_training_guest(db: Session, principal: Principal, args: dict) -> dict:
    try:
        result = register_guest(
            db, org_id=principal.org_id, session_id=int(args["session_id"]),
            name=str(args["name"]), email=str(args["email"]), phone=str(args.get("phone", "")),
            source="mcp",
        )
    except (TrainingError, KeyError) as exc:
        raise ToolError(str(exc)) from exc
    return {"registration_id": result.registration.id,
            "status": result.registration.status.value, "waitlisted": result.waitlisted}


@tool(ToolContract(
    name="promote_waitlist_candidate", permission="training.approve_promotion",
    risk=RiskLevel.r3_approval, approval_required=True, reversible=True, idempotent=False,
    audit_action="mcp.promote_waitlist_candidate", data_classification="Internal",
))
def _promote_waitlist_candidate(db: Session, principal: Principal, args: dict) -> dict:
    """Create a promotion proposal. It executes only if the org enabled the narrow
    auto-promote policy; otherwise it awaits human approval (approval_required=True)."""
    proposal = propose_waitlist_promotion(
        db, org_id=principal.org_id, session_id=int(args["session_id"]),
        requested_by_user_id=principal.user_id,
    )
    if proposal is None:
        return {"promoted": False, "reason": "no eligible waitlisted candidate or no free seat"}
    return {"proposal_id": proposal.id, "status": proposal.status.value,
            "executed": proposal.status == ProposalStatus.auto_executed}


@tool(ToolContract(
    name="draft_social_post", permission="social.draft",
    risk=RiskLevel.r1_draft, approval_required=False, reversible=True, idempotent=False,
    audit_action="mcp.draft_social_post", data_classification="Internal",
))
def _draft_social_post(db: Session, principal: Principal, args: dict) -> dict:
    """Draft social-post copy (assist only). Produces a DRAFT a human must review, approve, and
    publish — there is deliberately no MCP tool that can publish. `social.publish` is R4."""
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        raise ToolError("prompt is required")
    channel_ids = [int(c) for c in args.get("channel_ids", [])]
    proposal = AgentProposal(
        org_id=principal.org_id, agent="social", action="social.draft",
        risk_level=RiskLevel.r1_draft, goal=prompt[:500],
        requested_by_user_id=principal.user_id, status=ProposalStatus.proposed)
    db.add(proposal)
    db.flush()
    post = social.create_post(
        db, org_id=principal.org_id, created_by=principal.user_id, channel_ids=channel_ids,
        source=PostSource.llm_assisted, prompt=prompt)
    post.agent_proposal_id = proposal.id
    db.flush()
    return {"post_id": post.id, "status": post.status.value, "body": post.body,
            "proposal_id": proposal.id}


@tool(ToolContract(
    name="get_training_funnel_metrics", permission="report.view_training",
    risk=RiskLevel.r0_read, approval_required=False, reversible=True, idempotent=True,
    audit_action="mcp.get_training_funnel_metrics", data_classification="Internal",
))
def _get_training_funnel_metrics(db: Session, principal: Principal, args: dict) -> dict:
    session_id = int(args["session_id"]) if args.get("session_id") else None
    return {"funnel": training_funnel(db, org_id=principal.org_id, session_id=session_id)}


@tool(ToolContract(
    name="list_training_sessions", permission="report.view_training",
    risk=RiskLevel.r0_read, approval_required=False, reversible=True, idempotent=True,
    audit_action="mcp.list_training_sessions", data_classification="Internal",
))
def _list_training_sessions(db: Session, principal: Principal, args: dict) -> dict:
    rows = db.scalars(
        select(TrainingSession).where(TrainingSession.org_id == principal.org_id)
    ).all()
    return {"sessions": [
        {"id": s.id, "course": s.course.title, "capacity": s.capacity,
         "seats_available": s.seats_available, "is_open": s.is_open}
        for s in rows
    ]}


@tool(ToolContract(
    name="get_donation_metrics", permission="donation.view",
    risk=RiskLevel.r0_read, approval_required=False, reversible=True, idempotent=True,
    audit_action="mcp.get_donation_metrics", data_classification="Confidential",
))
def _get_donation_metrics(db: Session, principal: Principal, args: dict) -> dict:
    """Aggregates ONLY — never donor identity (INV-DONOR-SEPARATION). No write/refund tool
    exists; donation.refund is R4-prohibited so it can never execute through MCP."""
    from app.modules.donations.service import donation_metrics

    return {"metrics": donation_metrics(db, org_id=principal.org_id)}
