---
title: Prioritized Backlog
owner: Product
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [phased-plan.md, first-slice.md]
---

# Backlog

Priority: P0 (foundation/first slice) → P3 (later). Each item: id · summary · depends · acceptance.

## Epic F — Foundations (P0)
| id | Summary | Depends | Acceptance |
|---|---|---|---|
| F-1 | Repo skeleton: modular-monolith layout, `pyproject`, ruff/mypy, CI stub | — | `make check` runs; import-guard blocks cross-module ORM imports |
| F-2 | Docker Compose: postgres, redis, minio, api, worker, scheduler, web, proxy | F-1 | `docker compose up` boots; health endpoints 200 |
| F-3 | DB + Alembic + org-scoped repository base; `Organization`, `OrganizationSetting`, feature flags | F-1 | migration up/down; repo auto-filters `org_id`; unit test proves scoping |
| F-4 | Identity: `User`/`Person`/`Role`/`Permission`/scoped `UserRoleAssignment`; `authorize()` service | F-3 | authz unit tests incl. cross-org deny |
| F-5 | Audit: `AuditEvent` + emit helper + log redaction | F-3 | privileged action writes audit; secrets never logged |
| F-6 | Outbox + Celery worker + dev email adapter (inbox table); idempotency keys | F-2,F-3 | integration: state+event one tx; worker replay-safe |

## Epic T — Training slice (P0, first vertical slice)
| id | Summary | Depends | Acceptance |
|---|---|---|---|
| T-1 | `Course`/`TrainingSession` + admin/trainer management (scoped authz) | F-4,F-5 | create course+session; audited |
| T-2 | Public session view (SSR, a11y AA), no login wall | T-1 | axe + keyboard pass |
| T-3 | Guest registration (`Person`+`TrainingRegistration`), minimal fields, rate-limit + bot control | T-1,F-6 | integration: register→confirmation email via outbox |
| T-4 | Email verification (single-use, expiring token) | T-3 | unit: token lifecycle; unverified handled |
| T-5 | Capacity + waitlist (deterministic code) | T-3 | unit: capacity math + waitlist ordering |
| T-6 | Cancel + waitlist promotion (proposal→approval; narrow auto-policy flag) | T-5,F-6 | integration: cancel→promotion→approved email; audited |
| T-7 | Trainer check-in + completion (+ optional qualification) | T-1,F-5 | audited; qualification granted |
| T-8 | Guest→volunteer activation + identity reconciliation (no dup) | T-3,F-4 | integration: attaches to existing Person |
| T-9 | Training funnel + attendance metrics (authz-respecting) | T-1..T-8 | metric matches metric-dictionary defs |
| T-10 | MCP tools `register_training_guest`, `promote_waitlist_candidate` (authz+risk+audit inside tool) | T-3,T-6 | integration: MCP authz + audit; not raw endpoints |
| T-11 | Slice test suite: unit+integration+E2E+a11y+security; CI gate | T-1..T-10 | CI blocks on failure |

## Epic P — Public presence & content (P1)
| id | Summary | Depends | Acceptance |
|---|---|---|---|
| P-1 | `ContentPage` + CMS states (draft→review→scheduled→published→archived→expired) + preview + revisions | F-4,F-5 | non-engineer can publish; audited |
| P-2 | `Update` model + subscriptions by program/location/category/urgency + digest generation | F-6,P-1 | digest job idempotent |
| P-3 | Programs/opportunities/training catalog public pages (SSR) | T-1,P-1 | a11y AA; SEO metadata |
| P-4 | Interest + contact forms (bot-controlled) | F-6 | rate-limited; creates Person/interest |

## Epic S — Scheduling (P2) · Epic C — Communications (P2) · Epic M — Maintenance+Forms (P2) · Epic D — Donations (P3) · Epic A — Agents+MCP (P2→P3) · Epic U — Universalization (P3)
(Expanded per phased-plan.md; each carries the cross-phase invariants: org-scoping, server-side authz incl. workers+MCP, audit on privileged actions, idempotent async, a11y checks, agent-permission review.)

Representative later items:
- S-1 shared scheduling model (`Event`/`Shift`/`ShiftRole`/`ShiftSignup`); S-2 eligibility engine (unit-tested); S-3 self-signup+cancel rules; S-4 check-in+hours; S-5 coordinator dashboard; S-6 ICS feeds; S-7 conflict detection.
- C-1 template system + variable validation; C-2 `EmailAudienceDefinition` + **preview + counts**; C-3 approval workflow + thresholds; C-4 scheduled tz-aware sends + throttling; C-5 delivery/bounce/complaint/unsubscribe processing + suppression; C-6 digests.
- M-1 asset registry + QR/short-code; M-2 work-request lifecycle (configurable statuses); M-3 triage/assign; M-4 recurring maintenance + inspections; M-5 configurable forms + versioned submissions.
- D-1 Stripe test integration; D-2 webhook reconciliation (signature+replay-safe); D-3 receipts; D-4 recurring + failed-payment handling; D-5 refunds (approval); D-6 finance export.
- A-1 read-only agents (staffing summary, weekly report, KB answers); A-2 draft agents (reminders, digests, maintenance classification, onboarding blockers); A-3 narrow approved writes; A-4 MCP client scoping + rate limits.
- U-1 org module config/flags; U-2 configurable terminology; U-3 import tools; U-4 org-scoped MCP clients; U-5 branding; U-6 tenant-isolation test suite; U-7 other-org deploy docs.

## Definition of Done (applies to every backlog item)
Product behavior documented · permissions defined · migrations exist (reversible) · API+UI
implemented · server-side validation · audit where required · idempotent async · useful
error states · a11y checked · unit+integration (+E2E where relevant) pass · security
addressed · metrics/logs added · runbooks updated · MCP exposure reviewed · agent actions
permissioned · deploy+rollback understood · copy is clear and human.
