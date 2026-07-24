---
title: Implemented-State Audit
owner: Architecture
status: current
last_reviewed: 2026-07-24
applies_to: platform
supersedes: current-state-audit.md (the "greenfield" framing)
---

# Implemented-State Audit

## Why this document exists
`current-state-audit.md` describes the platform as **greenfield** with only a throwaway
`volunteer-hub` prototype as prior art. That was true at Phase 0. It is **no longer true**:
the modular-monolith backend, the public + authenticated frontend, CI, and a governed
agent/MCP layer are now **implemented and tested**. This document is the verified record of
what actually exists, so design work builds on reality instead of the original plan.

Everything below was verified against the repository on the review date (module/model/route
inventories, test counts), not asserted from memory. Where the brief asks for something that
does **not** yet exist, it is listed under [Gaps](#gaps-verified-absent).

## System shape (as built)
Modular monolith, exactly as the ADRs intended:

- **Backend** — FastAPI, SQLAlchemy 2.0 **sync**, Alembic. PostgreSQL in prod/CI; SQLite for
  the test suite (models are written portably; datetimes naive-UTC). Single app, thin
  routers → service modules → models.
- **Async** — Celery + Redis worker/beat. Beat jobs: `relay-outbox`, `expire-holds`,
  `send-due-campaigns`. All email/side-effects go through a **transactional outbox** with an
  idempotent relay (`app/core/outbox.py`).
- **Frontend** — Next.js 14 (App Router) + TypeScript, plain CSS design system. Public site
  **and** authenticated dashboards (see below). Playwright + axe E2E.
- **Governed automation** — an agent control plane (`app/modules/agents`) with a deterministic
  R0–R4 risk classifier, and an MCP layer (`app/mcp`) splitting read vs write tools, each
  bound to a permission.
- **Deploy** — Docker Compose: `postgres`, `redis`, `api`, `worker`, `beat`, `web`.
- **CI** — GitHub Actions: ruff + mypy + pytest + `alembic upgrade head && alembic check`
  (migration-drift gate) + frontend build + Playwright/axe E2E.

## Modules and domain model (as built)
All models derive from `Base` + `TimestampMixin` and carry an indexed `org_id` FK.
`OrgScopedRepository` (`app/core/db.py`) centralises org-scoped querying.

| Module | Models (verified) |
|---|---|
| `org` | `Organization`, `Program`, `OrganizationSetting` |
| `identity` | `Person`, `User`, `Role`, `RolePermission`, `UserRoleAssignment`, `VerificationToken` (+ `RoleScopeType`, `TokenPurpose` enums) |
| `people` | `VolunteerProfile`, `QualificationType`, `VolunteerQualification` |
| `scheduling` | `Event`, `Shift`, `ShiftRole`, `ShiftSignup`, `VolunteerHourEntry` (+ `SignupStatus`) |
| `training` | `Course`, `TrainingSession`, `TrainingRegistration` (+ `RegistrationStatus`) |
| `communications` | `EmailTemplate`, `EmailMessage`, `EmailDeliveryEvent`, `InboxMessage`, `AudienceDefinition`, `EmailCampaign`, `Suppression` (+ `CampaignStatus`) |
| `agents` | `AgentProposal` (+ `RiskLevel`, `ProposalStatus`) |
| core | `AuditEvent` (`app/core/audit.py`), `OutboxEvent` (`app/core/outbox.py`) |

The domain concepts from the brief that are **modelled today**: Organization, Program, User,
Person, VolunteerProfile, Role, Permission, Qualification, Course, TrainingSession,
Registration, Event, Shift, (Shift)Role, Signup/Assignment, VolunteerHourEntry, EmailTemplate,
EmailCampaign, Message, Suppression/consent, AuditEvent, AgentProposal (≈ Agent action /
Approval request). See `domain-model.md` for the intended full model; this table is the
subset that has tables and migrations behind it.

## Authorization (as built)
- **Passwordless** magic-link auth: `POST /api/auth/request-login` → emailed one-time token
  → `POST /api/auth/login`; guest→volunteer `POST /api/auth/activate`. Session = a signed
  bearer token carrying `(user_id, org_id)`.
- **Scope-aware RBAC** (`app/core/authz.py`): a `Grant` = (permission, scope_type, scope_id).
  `has_permission`/`require` = coarse (any scope); `authorize`/`require_scoped` = fine (the
  grant's scope must cover the target's `program_id`). Org-scoped grant covers all programs;
  a program-scoped grant covers only its program and does **not** cover org-level resources.
- **Permissions in use** (seeded in `app/seed.py`): `training.*` (manage_course/session,
  record_attendance/completion, view_roster, approve_promotion, register_guest),
  `shift.*` (manage, view_roster, view_eligible, signup, record_attendance),
  `hours.approve`, `report.view_staffing`/`view_training`, `comms.manage`/`comms.approve`,
  `audit.view`. Denials emit an `authz.denied` `AuditEvent`.
- Seeded roles: `org_admin`, `trainer`, `coordinator`, `volunteer`, `comms_manager`. The
  model already supports **custom roles / permission bundles** (roles are rows, permissions
  are rows) — the brief's "create custom roles later" is a data operation, not a code change.

## API surface (as built)
Verified route inventory (prefixes omitted):

- **Public**: `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/register`,
  `POST /verify`.
- **Auth**: `POST /request-login`, `POST /login`, `POST /activate`, `GET /me`.
- **Volunteer**: `GET /shifts/eligible`, `GET /shifts/mine`, `POST /shifts/signup`,
  `POST /shifts/signups/{id}/cancel`, `GET /shifts/calendar.ics`.
- **Coordinator**: `POST /coordinator/{events,shifts,roles}`, `POST /coordinator/checkin`,
  `POST /coordinator/hours`, `GET /coordinator/board`, `GET /coordinator/metrics/staffing`.
- **Trainer**: `POST /courses`, `POST /sessions`, `POST /registrations/{id}/checkin`,
  `POST /registrations/{id}/complete`.
- **Communications**: `POST /audiences`, `GET /audiences/{id}/preview`, `POST /campaigns`,
  `POST /campaigns/{id}/{submit,approve,send}`, `POST /unsubscribe`.
- **Admin/agents**: `GET /metrics/training-funnel`, `POST /proposals/{id}/approve`.
- **Ops**: `GET /ready` (DB+Redis, 503 on failure), `GET /metrics` (outbox backlog).

## Frontend (as built)
Public: home, trainings list/detail, register, verify. **Authenticated app** (added this
session): magic-link `/login`, `/activate`, and `/dashboard` that branches on the caller's
permission set into a **volunteer** view (my shifts + eligible shifts, signup/cancel) and a
**coordinator** view (staffing metrics + roster board with check-in/hours). Accessibility is
a first-class concern (labelled fields, `aria-invalid`, live regions, axe in E2E).

## Tests (as built)
**60 backend tests** across 13 files (unit + API + integration), plus Playwright/axe E2E.
Coverage includes: RBAC scope (`test_rbac_scope`), outbox idempotency/rollback
(`test_registration_outbox`, `test_review_fixes`), waitlist promotion, holds/limits,
communications approval-gate + suppression, MCP tool contracts + server, dashboard read APIs,
ops endpoints. The suite runs on shared in-memory SQLite (~4s).

**Testing debt vs. the brief**: there are **no explicit cross-tenant negative tests** (a user
of org A proving they cannot read org B) and no load tests for registration-open / mass-send.
These are the highest-value test gaps — see `test-strategy.md` and [Gaps](#gaps-verified-absent).

## Governed automation (as built)
- `app/modules/agents/risk.py` maps actions to **R0 read → R1 draft → R2 low-execute
  (allowlist) → R3 approval-required → R4 prohibited**, and **fails safe**: unknown actions
  default to R3. R4 set includes `comms.send_bulk`, `record.delete`, `donation.refund`,
  `permissions.change`, etc. `AgentProposal` + `POST /proposals/{id}/approve` implement the
  human-in-the-loop path.
- `app/mcp` exposes tool **contracts** (name + permission + args), separates read from write,
  and routes writes through the same authz + audit path as humans. Tools today are
  training/reporting-oriented (`register_training_guest`, `promote_waitlist_candidate`,
  `get_training_funnel_metrics`, `list_training_sessions`).

## Gaps (verified absent)
Ordered by structural leverage. None of these have code today.

1. **Tenancy — resolved by decision, not a gap.** Per owner directive, deployment is
   **single-tenant per instance** (one org per DB/instance). So the single-org
   `get_public_org` is the intended design, host/subdomain routing is out of scope, and
   cross-tenant isolation is an *infrastructure* boundary rather than a shared-DB concern.
   `org_id` scoping is retained as a cheap internal invariant. What remains: light org-scoping
   sanity tests + a "new-instance" onboarding checklist. → `multi-tenancy.md` (this batch).
2. **Forms & workflow builder.** No shared form/workflow engine; onboarding is bespoke code in
   `people/service.py`. This is the substrate the brief wants reused by incidents, maintenance,
   reimbursements, feedback. → `forms-workflow-engine.md` (this batch).
3. **Donations & fundraising.** Entirely absent. → `donations-design.md` (this batch).
4. **Internal ops modules** — maintenance requests, inventory/equipment, incident reports,
   reimbursements. All should be *consumers* of gap #2, not new bespoke modules.
5. **Content management** for public pages (pages are hardcoded React; brief wants
   draft→review→publish CMS).
6. **Unified reporting/exports** — metrics exist per-module (`staffing`, `training-funnel`);
   no cross-cutting reporting layer, saved views, scheduled reports, or CSV export.
7. **Object storage / documents** — no S3/MinIO wiring, no document/waiver upload pipeline
   (needed by onboarding, incidents, reimbursements).
8. **Certification expiry & renewal reminders** — `VolunteerQualification` has `expires_at`
   but no beat job that warns before expiry.
9. **Security hardening** the brief names: MFA for privileged users, SSO, encryption of
   sensitive stored fields (emergency contacts, background-check status), malware scanning for
   uploads. `threat-model.md` names these; none are implemented.
10. **Comms depth** — visual email editor, delivery/bounce status surfacing, SMS/push.
11. **Calendar integration** beyond the read-only ICS feed (no Google/Outlook sync).

## What NOT to rebuild
The following are sound and should be **extended, not replaced**: the outbox + idempotent
relay, the scope-aware RBAC model, `OrgScopedRepository`, the R0–R4 agent classifier, the MCP
contract split, the audit emitter, and the CI drift gate. New modules should reuse these
primitives rather than introduce parallel mechanisms.
