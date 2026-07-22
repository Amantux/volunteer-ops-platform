---
title: Current-State Audit
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
---

# Current-State Audit

## Purpose
Document what exists before proposing changes, per the operating model. This
platform is **greenfield** but has one relevant piece of prior art.

## Prior art: `volunteer-hub` (prototype, throwaway)
A small app built as a warm-up. Location: `/root/volunteer-hub`.

| Aspect | Prototype | Verdict for the platform |
|---|---|---|
| Frontend | React 18 + TypeScript (Vite), plain CSS | **Reuse the stack & design instincts**, not the code |
| Backend | FastAPI + **SQLite** (sync SQLAlchemy 2.0) | Stack good; **replace SQLite → PostgreSQL** |
| Domain | `Opportunity`, `Volunteer`, `Signup` only | Seed concepts; superseded by full domain model |
| Auth | Single shared password, **in-memory sessions** | **Reject** — needs real identity, RBAC, MFA |
| Email | none | **Missing foundation** — needs outbox + provider adapter |
| Queue/workers | none | **Missing foundation** — needs Redis + durable workers |
| Multi-org | none (single implicit org) | **Missing** — all records must be org-scoped |
| Audit | none | **Missing** — required for privileged actions |
| Agents / MCP | none | **Missing** — governed layer required |
| Tests | 1 pytest module (7 tests) | Good habit; expand into a real strategy |
| Deploy | single container (build FE → serve via API) | Good pattern; extend to compose w/ Postgres+Redis+worker |

## Technical debt / missing foundations (gap list)
1. **No relational integrity for the real domain** — prototype models can't express
   programs, shifts, qualifications, onboarding, communications, maintenance, donations.
2. **No authorization model** — shared password ≠ least-privilege RBAC scoped by org/program/team.
3. **No async/eventing** — email-as-synchronous-request is an explicit anti-goal; there is
   no outbox, no worker, no scheduler, no idempotency.
4. **No org boundary** — nothing enforces tenant isolation.
5. **No audit/compliance trail.**
6. **No content/CMS workflow** (draft→review→scheduled→published→archived).
7. **No provider abstraction** for email / payments / object storage / calendar / identity.
8. **No agent control plane or MCP governance.**

## Security risks in the prototype (do NOT carry forward)
- In-memory bearer tokens with a single shared secret (no rotation, no per-user identity).
- No rate limiting / bot controls on public forms.
- No upload validation (no uploads exist yet, but none of the guardrails do either).
- No CSRF/CSP posture, no audit.

## Reuse decision
**Start a new repository** (`volunteer-ops-platform`) with the target architecture.
Carry forward: the React+FastAPI+TypeScript competence, the clean design language, the
"one container serves built FE" deployment idea (extended). Carry forward **no code**
that would bolt a signup form onto a brochure site — the explicit anti-goal.

## Documented assumptions (made to avoid blocking)
- **A1**: Initial deployment = a single organization; architecture stays org-scoped so a
  second org needs config, not a rewrite. No multi-tenant billing in scope.
- **A2**: Email provider = pluggable adapter; default dev adapter writes to a local
  "mailpit"-style inbox / DB table; production uses SES/Postmark/etc. via config.
- **A3**: Payments = Stripe (test mode) via webhook reconciliation; **no card data stored**.
- **A4**: Object storage = S3-compatible (MinIO in local dev).
- **A5**: The first real org is a general-purpose community/operations group; terminology
  must stay configurable (no "chapter/shift/crew" hard-coded in logic).
- **A6**: No minors' data, medical data, or background-check *reports* stored in the first
  slice; those trigger the higher-risk review path (see threat-model).
