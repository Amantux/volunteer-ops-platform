---
title: Agent Permissions & Hard Constraints
owner: Architecture / Agent Systems
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [agent-control-plane.md, ../architecture/permissions.md, ../product/non-goals.md]
---

# Agent Permissions

Per-agent capabilities and **hard constraints**. Hard constraints are enforced
server-side (authorization + workflow definitions + risk classes from
agent-control-plane.md), never by prompt alone. All agents are org-scoped,
identity-bearing MCP clients; every tool call is authorization-checked and
logged (`MCPToolInvocation`). Risk classes R0–R4 are defined in the control
plane; confidence never changes a gate.

Shared rules for every agent:

- Acts only through its allowlisted MCP tools for the invoked bounded workflow.
- Reads only what the requesting user's scope permits; the org boundary is absolute.
- Cites internal records for any factual claim in drafted output; never invents
  dates, policies, staffing levels, events, or people.
- Escalates to a human on low confidence, missing evidence, or anything
  safety-relevant, instead of guessing.
- No raw DB, shell, Docker, or secret access exists behind MCP (non-goals).

## 1. Scheduling agent

**Capabilities**
- Analyze staffing levels; detect understaffed/overstaffed shifts (R0).
- Recommend volunteers for open shift roles with eligibility explanations (R3 proposal).
- Draft schedule scenarios and swap suggestions for coordinator review (R1).
- Propose waitlist promotions when seats open (R3).

**Hard constraints**
- Recommendations must respect, in full: declared **availability**, required
  **qualifications**, **age** rules, **program** rules, **workload** limits,
  **accessibility** needs, and stated **preferences**. Eligibility is computed
  by deterministic code; the agent ranks only within the eligible set.
- **Never auto-assigns.** Assignment is R3 (human approval) unless the org has
  *narrowly* enabled auto-assign via an explicit `OrganizationSetting` — and
  even then only for the configured low-stakes shift types, always reversible,
  always audited.
- Never schedules anyone outside declared constraints, regardless of urgency
  or confidence (globally prohibited, §9).
- Explanations must not expose one volunteer's private data to justify
  another's selection; non-selected candidates appear only as aggregates.

## 2. Communications agent

**Capabilities**
- Draft campaign and transactional email content from templates and internal
  records (R1).
- Propose audience definitions as explicit, previewable `EmailAudienceDefinition`
  records with counts (R1).
- Send individual templated messages that are on the org's auto-reminder
  allowlist (R2).
- Summarize delivery/engagement outcomes for staff (R0).

**Hard constraints**
- **Never sends to a larger audience than was approved.** The approved
  `EmailAudienceDefinition` is frozen at approval; any change to filters or
  count voids the approval.
- **Never invents dates, policies, staffing details, or events.** Every factual
  claim in a draft must cite an internal record; uncited claims fail review by rule.
- **Preserves unsubscribe and consent**: suppression lists,
  `SubscriptionPreference`, and `ConsentRecord` are enforced at send time and
  cannot be overridden or "reasoned around" by the agent.
- Bulk or sensitive sends are R3 minimum (comms manager within policy
  thresholds; org admin above) — never autonomous.

## 3. Maintenance triage agent

**Capabilities**
- Categorize and prioritize incoming `WorkRequest`s; suggest severity, required
  skills/parts, and routing (R2 for triage-field updates; R3 for assignment proposals).
- Detect probable duplicates and link related requests (R1 flag; human confirms).
- Draft status summaries and vendor-question lists (R1).
- Monitor `MaintenanceSchedule` for overdue items and raise them (R0/R1).

**Hard constraints**
- **Never closes work without evidence.** Closure requires human action with
  attached evidence (`WorkAssignment` resolution notes/photos); the agent may
  only propose "ready_for_verification".
- **Never authorizes spending** — no parts orders, vendor engagements, or cost
  approvals; it may only draft the request for a human.
- **Never issues unsafe instructions.** No repair guidance involving
  electrical, structural, height, chemical, or other safety-sensitive work;
  such requests are routed to qualified humans.
- **Escalates on safety signals or low confidence**: anything tagged or
  inferred as a safety hazard is escalated to the maintenance coordinator
  immediately and is never down-prioritized by the agent.

## 4. Volunteer onboarding agent

**Capabilities**
- Track `OnboardingRecord` progress; identify stalled pipelines and missing
  documents (R0).
- Draft reminder/next-step messages to prospective volunteers (R1; allowlisted
  templated nudges may be R2 where the org enables them).
- Prepare summaries of a candidate's *objective* pipeline status for staff (R0).
- Answer prospects' process questions from published onboarding materials (R0).

**Hard constraints**
- **Never makes acceptance, rejection, suitability, or disciplinary
  decisions** — and never drafts output that functions as one (no scoring
  candidates "fit/unfit", no recommendation to reject).
- **Never triggers, evaluates, or interprets background checks**; it may only
  report the objective status recorded by authorized staff.
- **Never infers protected characteristics** (age beyond rule-required
  verification flags, health, religion, ethnicity, etc.) from names, documents,
  or free text — not for routing, prioritization, or phrasing.
- **Never exposes reviewer notes** or other staff-visibility-restricted fields
  to the candidate or to staff who lack access.

## 5. Data-quality agent

**Capabilities**
- Detect probable duplicate Person/VolunteerProfile records with evidence (R1 flag).
- Flag stale, inconsistent, or invalid data (expired qualifications recorded as
  active, impossible dates, orphaned records) (R0/R1).
- Propose normalization fixes (formatting of phones/addresses, tag hygiene)
  (R2 only for org-allowlisted, reversible normalizations; otherwise R3).

**Hard constraints**
- **Merges always require human approval** (R3, org-admin per the capability
  matrix), executed as staged, reversible operations — the agent never merges,
  and never deletes.
- Duplicate evidence shown to reviewers is limited to fields the reviewer may
  see; no private-field disclosure to make a match "more convincing".
- Fix proposals must show before/after and the source record for the "after".

## 6. Reporting agent

**Capabilities**
- Generate operational reports and summaries (attendance, hours, staffing
  coverage, maintenance backlog, campaign outcomes) (R0).
- Draft recurring digest content for staff (R1).
- Answer ad-hoc analytical questions over data the requester may access (R0).

**Hard constraints**
- **Cannot bypass row-level or role-based authorization.** Every query runs
  under the requesting user's effective scope: a Program A coordinator's report
  can never include Program B rows, and no aggregate may be constructed from
  rows the requester couldn't read individually. Small-cell aggregates that
  would re-identify individuals in restricted data are suppressed.
- Read-only by construction: its tool allowlist contains no write tools.
- Numbers come from deterministic query tools, never model arithmetic over
  remembered data; each figure cites its query.

## 7. Knowledge / support agent

**Capabilities**
- Answer volunteer and staff questions from published content, policies, FAQs,
  and the requester's own records (R0).
- Draft suggested updates to FAQs/content when it detects gaps (R1).
- Perform a small set of explicitly allowlisted low-risk actions (see constraint).

**Hard constraints**
- **Autonomous actions are limited to an explicit low-risk allowlist** (R2),
  maintained per org — e.g. resend a magic link the user requested, surface the
  user's own upcoming shifts, file a support ticket. Anything not on the list
  is a draft or an escalation. The allowlist is configuration reviewed by the
  org admin, never extended by the agent.
- Answers cite the published source; if no source exists it says so and
  escalates — it never invents policy.
- Never reveals one person's data to another; "my records" means the
  authenticated requester's only.

## 8. Agent → tools → risk → approval matrix

Tool names are the governed MCP tool families (each internally
authorization-checked). "Max autonomous" = highest risk class the agent can
execute without a human decision, and only within org allowlists.

| Agent | Allowed MCP tools | Max autonomous | Approval requirement for writes |
|---|---|---|---|
| Scheduling | `shifts.read`, `volunteers.read_scoped`, `eligibility.evaluate`, `schedule.propose_assignment`, `waitlist.read` | R0 (R2 only if org narrowly enables auto-assign) | Assignments & waitlist promotions: R3 → program/team coordinator |
| Communications | `templates.read`, `records.read_scoped`, `comms.draft`, `audience.define_preview`, `comms.send_allowlisted_individual` | R2 (allowlisted individual sends only) | Bulk/sensitive send: R3 → comms manager (in policy) / org admin (above) |
| Maintenance triage | `workrequests.read`, `workrequests.update_triage`, `assets.read`, `maintenance.schedule_read`, `workrequests.propose_assignment`, `comms.draft` | R2 (triage fields only) | Assignment: R3 → maintenance coordinator; closure: human-only with evidence |
| Onboarding | `onboarding.read`, `documents.read_status`, `comms.draft`, `comms.send_allowlisted_individual`, `content.read_published` | R2 (allowlisted nudges only) | Any stage transition: R3 → coordinator; decisions: R4 (prohibited) |
| Data-quality | `records.read_scoped`, `duplicates.flag`, `records.propose_fix`, `records.apply_allowlisted_normalization` | R2 (allowlisted normalizations) | Merge: R3 → org admin; delete: R4 (prohibited) |
| Reporting | `reports.query_scoped`, `metrics.read`, `digest.draft` | R0 | n/a — no write tools |
| Knowledge/support | `content.read_published`, `records.read_own`, `support.allowlisted_action`, `content.draft_suggestion`, `tickets.create` | R2 (explicit allowlist only) | Content changes: R3 → content approver |

## 9. Globally prohibited autonomous actions (R4)

No agent may ever perform these autonomously — at any confidence, under any
workflow, even if a tool nominally exists and even with approval routed through
the agent itself. Humans perform them through the normal UI; an agent may at
most *recommend* one to a human. Each attempt is denied server-side and audited.

1. Send sensitive or bulk communications.
2. Reject a volunteer (or make any acceptance/suitability decision).
3. Discipline a volunteer.
4. Change permissions, roles, or scopes.
5. Issue refunds or move money.
6. Modify financial records.
7. Delete records.
8. Expose private volunteer or donor data.
9. Schedule anyone outside their declared constraints.
10. Publish public content.
11. Merge people records without human approval (staged, reversible, admin-approved when performed).

These mirror the high-risk actions in permissions.md and the agent non-goals in
non-goals.md; changing this list requires an ADR and a review of every
workflow definition that could touch it.
