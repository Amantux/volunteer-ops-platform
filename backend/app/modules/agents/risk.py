"""Deterministic risk classification for agent-proposed actions.

Confidence is separate from authority: this maps an action to the *authority* it needs.
"""

from __future__ import annotations

from .models import RiskLevel

# Actions an agent may NEVER perform autonomously (map to R4). See agent-permissions.md.
PROHIBITED = frozenset({
    "comms.send_bulk", "comms.send_sensitive", "volunteer.reject", "volunteer.discipline",
    "permissions.change", "donation.refund", "finance.modify", "record.delete",
    "private_data.expose", "schedule.override_constraints", "content.publish_public",
    "social.publish",  # agents may draft social copy, never publish it to a channel
})

APPROVAL_REQUIRED = frozenset({
    "promote_waitlist", "comms.schedule_send", "people.merge", "work.close",
})

LOW_EXECUTE = frozenset({  # explicit allowlist of low-risk autonomous actions
    "comms.send_reminder_approved_template",
})

DRAFT = frozenset({
    "comms.draft", "digest.generate", "report.draft", "maintenance.classify", "social.draft",
})


def classify_action(action: str) -> RiskLevel:
    if action in PROHIBITED:
        return RiskLevel.r4_prohibited
    if action in APPROVAL_REQUIRED:
        return RiskLevel.r3_approval
    if action in LOW_EXECUTE:
        return RiskLevel.r2_low_execute
    if action in DRAFT:
        return RiskLevel.r1_draft
    if action.startswith("read.") or action.endswith(".read") or action.endswith("_metrics"):
        return RiskLevel.r0_read
    # Unknown actions default to requiring approval — fail safe, never silently execute.
    return RiskLevel.r3_approval
