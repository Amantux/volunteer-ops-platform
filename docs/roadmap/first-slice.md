---
title: First Vertical Slice — Public Training Registration
owner: Product / Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [domain-model.md, permissions.md, system-design.md, mcp-design.md]
---

# First Vertical Slice: Public Training Registration → Volunteer Conversion

## Why this slice
It proves the architecture end-to-end while touching the fewest modules: public content,
forms, **people/identity (guest→volunteer)**, training, a slice of scheduling (waitlist),
**communications + transactional outbox + background jobs**, reporting, permissions, audit,
and **MCP** — without needing donations/maintenance/full-scheduling.

## The 17 steps (from the brief §16) → mapped to entities & controls
| # | Step | Entities | Control / note |
|---|---|---|---|
| 1 | Admin creates a public training **course** | Course | authz `training.manage_course`; audit |
| 2 | Trainer creates a **session** w/ capacity + prerequisites | TrainingSession | authz `training.manage_session` (scoped); audit |
| 3 | Public visitor views the session | Course/Session (public) | no login wall; SSR public page |
| 4 | Visitor registers **without** a full account | Person (guest), TrainingRegistration | rate-limit + bot control; minimal fields |
| 5 | System **verifies** email | Person.email verified flag, token | single-use, expiring token |
| 6 | Confirmation email via **outbox** | OutboxEvent → EmailRecipient/DeliveryEvent | email is async, never in the request |
| 7 | Session reaches capacity → **waitlist** | WaitlistEntry | deterministic capacity math (code, not agent) |
| 8 | A registrant **cancels** | TrainingRegistration(cancelled) | emits domain event |
| 9 | System proposes/performs allowed **waitlist promotion** | WaitlistEntry, AgentProposal/ApprovalRequest | auto only if org enables narrow policy; else proposal→approval |
| 10 | Promoted person receives an **approved** email | OutboxEvent → EmailRecipient | approved template; consent respected |
| 11 | Trainer **checks in** attendees | AttendanceRecord | authz `training.record_attendance`; audit |
| 12 | Trainer records **completion** | AttendanceRecord.completed, VolunteerQualification | may grant a QualificationType; audit |
| 13 | Attendee invited to **activate** a volunteer account | User (new), invite token | links to existing Person (no duplicate) |
| 14 | Training record **linked** to the new volunteer profile | VolunteerProfile ← Person | identity reconciliation |
| 15 | Admin views **funnel + attendance** metrics | reporting | metrics from metric-dictionary; authz-respecting |
| 16 | All sensitive actions in the **audit log** | AuditEvent | steps 1,2,9,11,12,13 minimum |
| 17 | Approved functions available via **narrow MCP tools** | MCPToolInvocation | `register_training_guest`, `promote_waitlist_candidate` |

## Identity reconciliation (critical)
A guest registration creates a **Person** with a verified email but no User. When the same
person later activates an account (step 13), the system **matches on verified email** and
attaches a User + VolunteerProfile to the *existing* Person — never creating a duplicate.
Ambiguous matches route to a human merge-review (data-quality), never auto-merged.

## In-scope modules/migrations
`org+identity`, `people` (Person + minimal VolunteerProfile), `training`,
`communications` (EmailTemplate, OutboxEvent, EmailRecipient, EmailDeliveryEvent,
SubscriptionPreference), `audit`, minimal `agents`+`mcp`. Everything org-scoped.

## Explicitly OUT of this slice
Full scheduling/shifts, donations, maintenance, full CMS, campaign bulk email (only
transactional + the single approved promotion email), full agent fleet (only the two MCP
tools + a read-only funnel metric).

## Acceptance criteria (Definition of Done for the slice)
- [ ] Public can view a session and register as a guest with minimal fields; **no account required**.
- [ ] Email verification is single-use + expiring; unverified registrations don't consume a confirmed seat improperly.
- [ ] Confirmation + promotion emails are produced through the **outbox** (state + event in one tx) and sent by an **idempotent** worker; provider-down does not lose or double-send.
- [ ] Capacity + waitlist ordering are deterministic **code** (unit-tested), not agent logic.
- [ ] Waitlist promotion is a proposal requiring approval **unless** the org enables the narrow auto-promote policy; either path is audited.
- [ ] Trainer (scoped) can check in + record completion; completion can grant a qualification; both audited.
- [ ] Guest→volunteer activation attaches to the **existing Person** (no duplicate); training linked.
- [ ] Admin sees the training funnel + attendance metrics (authz-respecting).
- [ ] `AuditEvent` exists for steps 1,2,9,11,12,13.
- [ ] MCP tools `register_training_guest` and `promote_waitlist_candidate` enforce authz + risk/approval + emit the declared audit event; not exposed as raw endpoints.
- [ ] Server-side authz on every protected op; public form rate-limited + bot-controlled.
- [ ] Tests: unit (capacity, waitlist order, verification token, permissions, agent risk class), integration (register→confirmation email via outbox; cancel→promotion→approved email; delivery webhook; guest→volunteer; MCP authz; audit generation), E2E (public registration; keyboard-only; mobile).
- [ ] Accessibility AA on the public registration flow (axe + keyboard); useful error states.
- [ ] Rollback: additive reversible migrations; feature-flag the slice; documented rollback.

## Reversible implementation increments (order)
1. Migrations: org+identity, person, training, outbox/email, audit (additive).
2. Domain services: registration, verification, capacity/waitlist (pure, unit-tested).
3. Outbox + worker + dev email adapter (inbox table); confirmation email.
4. Public registration API + SSR page; rate-limit + verification.
5. Trainer check-in/completion (+ qualification) with authz + audit.
6. Waitlist promotion (proposal + approval; narrow auto policy flag).
7. Guest→volunteer activation + identity reconciliation.
8. Funnel/attendance metric endpoint.
9. Two MCP tools over the services (authz + audit inside the tool).
10. E2E + a11y + security tests; wire CI gate.
