---
title: Phased Delivery Plan
owner: Product / Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [system-design.md, domain-model.md, first-slice.md]
---

# Phased Delivery Plan

Principle: ship the **smallest useful vertical slice**, validate it, review it, then repeat
with small reversible changes. Each phase has a Definition of Done (see brief §19) and must
leave `main` green (tests + migrations + lint + typecheck + security checks + build).

| Phase | Theme | Key deliverables | Depends on | Exit criteria |
|---|---|---|---|---|
| **0** | Discovery & foundations | Audit; product+arch docs; domain model; permissions matrix; threat model; metric dictionary; UX journeys; ADRs; migration+deploy strategy; backlog; non-goals | — | This doc set complete & internally coherent; skeleton repo + compose boots |
| **1** | Public presence & content | Public site; programs; public opportunities; training catalog; updates/notices; basic CMS workflow; contact + interest forms; a11y + mobile foundation | 0 | Public pages render (SSR), a11y AA on public flows, content draft→publish works |
| **2** | Training & onboarding (**first vertical slice**) | Guest training registration; email verification; confirmation+reminder email via **outbox**; waitlist + promotion; attendance; completion; guest→volunteer conversion; configurable onboarding pipeline; qualifications + expiration | 1 | The 17-step slice (first-slice.md) passes unit+integration+E2E; audit + MCP tools verified |
| **3** | Scheduling & volunteer ops | Events/shifts/projects (shared model); eligibility; self-signup; availability; waitlists; check-in; hours; coordinator dashboard; calendar (ICS); staffing metrics | 2 | A volunteer signs up/cancels; coordinator staffs a gap; conflict detection; metrics |
| **4** | Communications | Template system; transactional service; campaign drafts; **audience definition + preview**; approval; scheduling; delivery records; unsubscribe; digests | 2 | No bulk send without audience preview+approval+suppression+audit+delivery handling |
| **5** | Maintenance & forms | Asset registry; QR/short-code work requests; triage/assign; recurring maintenance; inspections; configurable forms; ops dashboards; reminders | 3 | Public reports issue → triage → assign → close w/ evidence; forms snapshot versions |
| **6** | Donations | Campaigns; Stripe (test) integration; webhook reconciliation; receipts; recurring; refunds (w/ approval); finance exports; donor consent | 1,4 | Test-mode donation → receipt; webhook replay-safe; donor data separated from volunteer ops |
| **7** | Agents & MCP (real) | Read-only + draft agents first (staffing summaries, draft reminders, maintenance classification, onboarding-blocker summaries, weekly reports, KB answers); then narrow approved writes | 2–6 | Agents deterministic-workflow-backed; every action permissioned + audited; approvals enforced |
| **8** | Universalization | Org module config; configurable terminology; reusable templates; import tools; org-scoped MCP clients; branding; tenant-isolation testing; other-org deploy docs | 1–7 | A 2nd org onboards by config only; isolation tests pass |

## Cross-phase invariants (every phase)
- Org-scoping enforced on all new records; authz server-side incl. workers + MCP.
- New privileged actions emit `AuditEvent`; new async work is idempotent + observable.
- Accessibility checked (axe + keyboard) on new user-facing flows.
- New agent/MCP surface reviewed against agent-permissions.md before merge.

## Sequencing rationale
Phase 2 (training + onboarding) is intentionally the first operational vertical slice
because it exercises public content, forms, people/identity, training, a slice of
scheduling, communications+outbox, background jobs, reporting, permissions, audit, and MCP —
without requiring every later module. See `first-slice.md`.
