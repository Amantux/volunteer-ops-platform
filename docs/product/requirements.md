---
title: Functional Requirements
owner: Product
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [vision.md, user-journeys.md, non-goals.md, ../architecture/domain-model.md, ../architecture/permissions.md]
---

# Functional Requirements

Conventions: MoSCoW priority (**M**ust / **S**hould / **C**ould). IDs are stable —
never renumber; retire with strikethrough + ADR reference. **Slice ✔** = in the first
vertical slice (public training registration end-to-end, per domain-model.md migration
plan). Scope is bounded by [non-goals.md](non-goals.md).

## Cross-cutting (apply to every area)

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-X-001 | Every protected operation is authorized server-side via the central `authorize()` service — in API routes, worker jobs, and MCP tools. Frontend role-awareness is never the boundary. | M | ✔ |
| REQ-X-002 | Every org-owned record carries `org_id`; repository base enforces the scope filter. No cross-org read or write paths exist. | M | ✔ |
| REQ-X-003 | Privileged/high-risk actions (list in permissions.md) emit an AuditEvent with actor, action, target, before/after digest. Denials on privileged actions are logged. | M | ✔ |
| REQ-X-004 | All outbound email is produced via the transactional outbox: state change + OutboxEvent in one transaction; idempotent worker relay; per-recipient rendered snapshot + delivery events. No email is sent inside a request handler. | M | ✔ |
| REQ-X-005 | All user-facing surfaces meet WCAG 2.1 AA and are keyboard operable. | M | ✔ |
| REQ-X-006 | All user-facing surfaces are mobile-first (public pages SSR/SSG for performance; touch-friendly targets). | M | ✔ |
| REQ-X-007 | Public forms have rate limiting and bot controls. | M | ✔ |
| REQ-X-008 | Org configuration (hierarchy labels, statuses, pipelines, workflows, policies, feature flags) is data (OrganizationSetting), not code branches. | M | — |
| REQ-X-009 | Agents only propose for high-risk actions (AgentProposal → ApprovalRequest); autonomous actions are limited to an explicit allowlist (e.g. scheduled reminders). Deterministic logic (eligibility, waitlist order, audience math) is ordinary tested code, never AI. | M | ✔ |
| REQ-X-010 | All times stored tz-aware and displayed in the org/session timezone. | M | ✔ |

## Public site / CMS

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-CMS-001 | Public site presents org content via ContentPages with draft → review → published lifecycle and revision history. | M | — |
| REQ-CMS-002 | Publishing public content requires an approver distinct from the author (high-risk action). | M | — |
| REQ-CMS-003 | Public pages render server-side (SSR/SSG) for SEO and mobile performance. | M | ✔ (session pages) |
| REQ-CMS-004 | Pages support scheduled publish and expiry. | S | — |
| REQ-CMS-005 | Pages support audience/location targeting. | C | — |

## Volunteer interest & onboarding

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-ONB-001 | A public interest form creates/updates a Person and records consent (ConsentRecord). | M | — |
| REQ-ONB-002 | Progressive enrollment: participation as a guest Person requires no account; account creation (User) links to the existing Person without data re-entry. | M | ✔ |
| REQ-ONB-003 | Orgs define OnboardingPipelines with configurable stages; each VolunteerProfile has an OnboardingRecord showing done / next / blocked. | M | — |
| REQ-ONB-004 | Stages verifiable from system state (e.g. required training completed) auto-complete; others queue for staff verification. | M | — |
| REQ-ONB-005 | Volunteers see exactly one highlighted next action and the stage owner's contact. | M | — |
| REQ-ONB-006 | Stalled onboarding records trigger reminder emails per org policy (outbox). | S | — |
| REQ-ONB-007 | Onboarding stages can require Document upload (validated: type/ext/size/magic-byte) or a FormSubmission. | S | — |

## Public training registration *(first vertical slice)*

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-TRAIN-001 | Public visitors can browse public Courses and upcoming TrainingSessions (schedule, location, capacity remaining, prerequisites, cost, accessibility info, cancellation policy). | M | ✔ |
| REQ-TRAIN-002 | A visitor can register for a session as a guest (name + email); the system finds-or-creates a Person and a TrainingRegistration — no account required. | M | ✔ |
| REQ-TRAIN-003 | Registration, its OutboxEvent, and its AuditEvent commit in one transaction; duplicate registration for the same person+session is idempotently rejected. | M | ✔ |
| REQ-TRAIN-004 | Confirmation email is sent via outbox with session details and a verify/manage link; the registrant can self-cancel from it. | M | ✔ |
| REQ-TRAIN-005 | Reminder emails are sent at configurable offsets before the session; reminder jobs are idempotent. | M | ✔ |
| REQ-TRAIN-006 | Full sessions accept waitlist registrations (WaitlistEntry with position and promotion-policy snapshot); registrant sees their position. | M | ✔ |
| REQ-TRAIN-007 | Cancellation triggers deterministic waitlist promotion (offer + confirm-by deadline; expiry rolls to next). Every promotion is audited. | M | ✔ |
| REQ-TRAIN-008 | Trainers (scoped to own sessions) view rosters and record check-in producing AttendanceRecords (manual; QR method supported). | M | ✔ (QR: S) |
| REQ-TRAIN-009 | Trainers record completion; completion updates registration status and grants the mapped VolunteerQualification once a VolunteerProfile exists. | M | ✔ |
| REQ-TRAIN-010 | Completion email invites guest → volunteer conversion: create User via magic link, attach to existing Person, carry training history forward. | M | ✔ |
| REQ-TRAIN-011 | Org admins manage Courses (prerequisites, capacity defaults, public/internal flag). | M | ✔ |
| REQ-TRAIN-012 | Qualification expiry (validity period on QualificationType) emits a `qualification.expiring` event driving renewal reminders. | S | — |
| REQ-TRAIN-013 | Paid courses take payment through the donations/payment provider path (payment ref on registration). | C | — |
| REQ-TRAIN-014 | Not an LMS: no course authoring, quizzes, or SCORM (non-goal — recorded here to anchor retrieval). | M | ✔ |

## Events / shifts / projects / scheduling

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-SCHED-001 | One shared model: Event (one-time / recurring / project / maintenance window / admin) → Shift → ShiftRole with capacity and eligibility rules. | M | — |
| REQ-SCHED-002 | Volunteers see opportunities filtered by computed eligibility; ineligible shifts explain why and link to the path to eligibility. | M | — |
| REQ-SCHED-003 | Volunteers sign up / cancel self-serve within policy windows; capacity is enforced transactionally. | M | — |
| REQ-SCHED-004 | Full roles offer a waitlist; promotion reuses the deterministic training-waitlist mechanism. | M | — |
| REQ-SCHED-005 | Coordinators (program/team scope) create/manage shifts, assign volunteers, and review attendance. | M | — |
| REQ-SCHED-006 | Understaffed shifts (below min at configured horizon) emit an event and surface on the owning coordinator's dashboard with eligible-and-available candidates. | M | — |
| REQ-SCHED-007 | Check-in and hours: signup check-in produces VolunteerHourEntries; coordinators approve hours in scope. | M | — |
| REQ-SCHED-008 | Recurring shifts via recurrence rules, with per-occurrence overrides. | S | — |
| REQ-SCHED-009 | Volunteers maintain AvailabilityRules used for candidate matching; no one is auto-scheduled outside declared constraints. | S | — |
| REQ-SCHED-010 | Agent staffing assistance is propose-only (ranked candidates, drafted outreach). | S | — |
| REQ-SCHED-011 | Shift change/cancellation notifies affected signups via outbox. | M | — |

## Communications & email ops

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-COMM-001 | EmailTemplates with declared, validated variables and enforced footer/unsubscribe. | M | ✔ (transactional set) |
| REQ-COMM-002 | Campaign lifecycle draft → review → approved → scheduled → sending → sent, with pause/cancel until send; all transitions audited. | M | — |
| REQ-COMM-003 | Audiences are explicit EmailAudienceDefinitions, previewable with resolved counts and samples before approval — never implicit lists. | M | — |
| REQ-COMM-004 | Approval policy: comms manager may approve within configured thresholds (size/audience/sensitivity); above threshold requires org-admin approval. Bulk send is never agent-autonomous. | M | — |
| REQ-COMM-005 | Per-recipient rendered content snapshot (EmailRecipient) and delivery events (bounce/complaint feed suppression). | M | ✔ |
| REQ-COMM-006 | SubscriptionPreferences (topic/program/location/urgency) and suppression are honored at audience-resolution time; unsubscribe is one click. | M | — |
| REQ-COMM-007 | Open/click tracking is opt-in per org, default off. | M | — |
| REQ-COMM-008 | Comms = transactional + campaign email + in-app updates only; no chat/messaging (non-goal). | M | ✔ |
| REQ-COMM-009 | Deliverability dashboard (send/bounce/complaint rates) for comms scope. | S | — |

## Updates & awareness

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-UPD-001 | Staff publish Updates (title/summary/body, urgency, audience, publish/expire) with author + approver and revision history. | M | — |
| REQ-UPD-002 | Volunteers see a filtered update feed relevant to their programs/locations/subscriptions. | M | — |
| REQ-UPD-003 | Updates can link related records (event/program/location/work request) so "what's happening" carries its next action. | S | — |
| REQ-UPD-004 | Digest emails summarize recent relevant updates per subscription preferences. | C | — |

## Maintenance & operations

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-MAINT-001 | Public issue-report form (anonymous allowed, contact optional, photo attachments, rate-limited) creates a WorkRequest and notifies the maintenance coordinator. | M | — |
| REQ-MAINT-002 | Asset registry with identifiers and QR/short-codes that prefill report and inspection forms. | M | — |
| REQ-MAINT-003 | Work-request workflow with org-configurable statuses (reported → needs_triage → … → closed / rejected / duplicate); triage sets severity, impact, and due. | M | — |
| REQ-MAINT-004 | Assignment (WorkAssignment) with required skills/parts; closing requires resolution notes + evidence, verified by the coordinator. | M | — |
| REQ-MAINT-005 | MaintenanceSchedules generate recurring preventive work; overdue work emits `maintenance.overdue`. | S | — |
| REQ-MAINT-006 | Inspections record checklist results and can spawn follow-up WorkRequests. | S | — |
| REQ-MAINT-007 | Maintenance hours flow into VolunteerHourEntries with maint-coordinator approval. | S | — |
| REQ-MAINT-008 | Contactable reporters are notified on triage decision and closure. | S | — |

## Donations

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-DON-001 | Public one-time donation, guest-capable, via payment-provider hosted fields; card data never touches the platform (non-goal, absolute). | M | — |
| REQ-DON-002 | Recurring donations: provider-managed cycles; each cycle reconciles a Donation via webhook; donor self-serve cancel and payment-method update (provider-hosted). | M | — |
| REQ-DON-003 | Payment webhooks are signature-verified, idempotency-keyed, and replay-safe (PaymentEvent). | M | — |
| REQ-DON-004 | Receipts are emailed via outbox with content snapshot; receipt state tracked; finance can resend. | M | — |
| REQ-DON-005 | DonationCampaigns with goal, designations, suggested amounts, optional public progress. | S | — |
| REQ-DON-006 | Refunds initiated by finance require approval (per matrix) and are audited. | M | — |
| REQ-DON-007 | Payment failure on recurring emits an event → dunning email with provider-hosted fix link. | S | — |
| REQ-DON-008 | Accounting export (CSV) of reconciled donations; no ledger/GL or tax documents beyond receipts (non-goal). | M | — |
| REQ-DON-009 | Donation records visible only to finance scope and org admin. | M | — |

## Internal forms

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-FORM-001 | FormDefinitions with published FormVersions; field types, validation, declarative conditional sections — no scripting language (non-goal). | M | — |
| REQ-FORM-002 | FormSubmissions snapshot the exact FormVersion immutably; identified or anonymous per definition. | M | — |
| REQ-FORM-003 | Forms can be role-restricted and carry a retention policy; no field is collected without documented purpose (data non-goal). | M | — |
| REQ-FORM-004 | Submissions have a review state and support attachments (validated uploads). | S | — |
| REQ-FORM-005 | Forms attachable as onboarding-stage requirements (see REQ-ONB-007). | S | — |

## Reporting (minimum operational set)

| ID | Requirement | Pri | Slice |
|---|---|---|---|
| REQ-RPT-001 | Role-scoped operational reports per the capability matrix (training for trainers/admin; program for coordinators; maintenance; comms; donations for finance). | M | ✔ (training only) |
| REQ-RPT-002 | Training report: registrations, waitlist, attendance, completion, conversion rate per session/course. | M | ✔ |
| REQ-RPT-003 | Org admin dashboard of the vision success signals (fill rates, conversion, comms approval coverage). | S | — |
