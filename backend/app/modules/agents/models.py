"""Agent control-plane records: proposals and approval requests.

Even in the first slice, a waitlist promotion that isn't covered by a narrow org policy
is recorded as an AgentProposal requiring an ApprovalRequest — confidence never grants
authority.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class RiskLevel(str, enum.Enum):
    r0_read = "r0_read"                 # read-only
    r1_draft = "r1_draft"              # produce a draft, no external effect
    r2_low_execute = "r2_low_execute"  # allowlisted low-risk action
    r3_approval = "r3_approval"        # requires human approval
    r4_prohibited = "r4_prohibited"    # never autonomous


class ProposalStatus(str, enum.Enum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    auto_executed = "auto_executed"    # covered by an explicit narrow org policy


class AgentProposal(Base, TimestampMixin):
    __tablename__ = "agent_proposal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(60), nullable=False)          # e.g. "scheduling"
    action: Mapped[str] = mapped_column(String(80), nullable=False)         # e.g. "promote_waitlist"
    risk_level: Mapped[RiskLevel] = mapped_column(nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[ProposalStatus] = mapped_column(default=ProposalStatus.proposed, nullable=False)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
