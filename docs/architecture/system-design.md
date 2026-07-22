---
title: System Design & Architecture Scoring
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [current-state-audit.md, domain-model.md, permissions.md]
---

# System Design

## 1. Shape: modular monolith + durable workers

```
                         ┌───────────────────────────────────────────┐
   Public / Volunteers   │            Reverse proxy (TLS)             │
   Coordinators / Admins │            (Caddy / nginx)                 │
        (browser)        └───────────────┬───────────────────────────┘
                                          │
                    ┌─────────────────────┴───────────────────────┐
                    │  web (Next.js/React, TS)  — public + app UI  │
                    └─────────────────────┬───────────────────────┘
                                          │  typed API client (HTTPS, JSON)
                    ┌─────────────────────┴───────────────────────┐
                    │  api (FastAPI) — modular monolith            │
                    │  application services + domain modules       │
                    │  authz enforced here (not just routes)       │
                    └───┬─────────────┬──────────────┬─────────────┘
                        │             │              │
                writes  │      events │ (outbox)     │ read
                        ▼             ▼              ▼
                 ┌──────────┐   ┌──────────┐   ┌──────────────┐
                 │ Postgres │   │  Redis   │   │  S3 / MinIO  │
                 │ (source  │   │ queue,   │   │  uploads,    │
                 │ of truth,│   │ cache,   │   │  generated   │
                 │ +outbox) │   │ locks    │   │  docs        │
                 └──────────┘   └────┬─────┘   └──────────────┘
                                     │ consumes
                 ┌───────────────────┴───────────────────┐
                 │  worker (Celery/RQ/Arq) — idempotent   │
                 │  email send, reminders, imports,       │
                 │  scheduled jobs, agent jobs, digests   │
                 └────────────────────────────────────────┘

   ┌───────────────────────────────┐   ┌───────────────────────────────┐
   │ mcp (governed interface)      │   │ Provider adapters:             │
   │ narrow tools over app services│   │ email · payments · storage ·   │
   │ shares authz + audit          │   │ calendar · identity            │
   └───────────────────────────────┘   └───────────────────────────────┘
```

**Deployables:** `web`, `api`, `worker`, `scheduler` (beat), `mcp`, plus infra
(`postgres`, `redis`, `minio`, `proxy`). One `docker-compose.yml` runs them all
locally and for small production deployments.

## 2. Module boundaries (bounded contexts inside the monolith)
Each is a package with its own models, services, and events. **Modules talk through
application services and domain events, never by importing another module's ORM
internals.** A lint/import-guard rule enforces this.

`identity` · `org` (organizations + configuration + feature flags) · `people`
(person + volunteer profile) · `programs` (program/team/location) · `training`
· `scheduling` (events/shifts/projects — one shared model) · `communications`
(templates/campaigns/outbox/delivery) · `content` (pages + updates + subscriptions)
· `maintenance` (assets + work requests) · `donations` · `forms` · `reporting`
· `agents` (orchestration + control plane) · `mcp` · `audit` · `integrations`.

Cross-cutting shared kernel: `org_id` scoping, `AuditEvent`, `DomainEvent`/outbox,
authorization primitives, typed provider interfaces.

## 3. Data & consistency
- **PostgreSQL** is the single source of truth. Every org-owned row carries `org_id`;
  a repository base enforces the filter so a missing scope is a bug, not a silent leak.
- **Explicit relational model** for business state; JSON only for genuinely extensible,
  provider-specific, or form-definition data (never as a substitute for the domain model).
- **Transactional outbox:** state change + `outbox_event` row committed in one DB
  transaction; the worker relays events → side effects (email, webhooks, agent jobs).
  This prevents "DB committed but email/webhook lost" inconsistency.
- **Idempotency:** every worker job and every inbound webhook (payments, email delivery)
  is keyed and safe to replay. Suppression + dedup at the boundary.

## 4. Async / eventing
Durable domain events (see brief §8): registration created/cancelled, waitlist seat
available, training completed, qualification expiring, shift understaffed/changed,
checked-in, work request created, maintenance overdue, donation completed, payment
failed, communication approved/scheduled/sent, delivery failed. Workers are idempotent
and observable (queue depth, consumer count, job freshness alerts).

## 5. Security posture (summary — full in security/)
Server-side authz on every protected op **and inside MCP tools and workers** (not just
API routes). Passwordless magic-link + optional password; MFA for privileged roles. CSP,
output encoding, parameterized queries, CSRF where cookie-based. Upload validation
(type/ext/size/magic-byte) + malware-scan interface. Rate limiting + bot controls on
public forms. Webhook signature verification + replay protection. Secrets from env/secret
manager, never committed. Audit for privileged actions with log redaction. Agents run on
untrusted content with prompt-injection isolation (uploaded/user content is data, never
instructions).

## 6. Frontend
React/Next.js + TypeScript. SSR/SSG for public content (SEO + mobile performance);
authenticated app is a typed SPA. Shared design system, accessible primitives (WCAG 2.1
AA target), keyboard operable, touch-friendly. Zod schemas shared with backend where
practical. **Role-aware navigation is UX only — never the security boundary.**

---

# Architecture Scoring (brief §18)

Scores 1 (poor) – 5 (excellent). Chosen options in **bold**.

## Backend framework
| Criterion | **FastAPI (Python)** | Django | Node/NestJS |
|---|---|---|---|
| Fit w/ prototype & team | 5 | 3 | 3 |
| Implementation complexity | 4 | 4 | 3 |
| Operational complexity | 4 | 4 | 4 |
| Security | 4 | 5 | 4 |
| Data integrity | 4 | 5 | 4 |
| Extensibility | 5 | 4 | 4 |
| Local-dev quality | 5 | 4 | 4 |
| **Agent/MCP integration** | 5 | 3 | 4 |
| Testing quality | 5 | 4 | 4 |
| Cost (nonprofit) | 5 | 5 | 5 |
| Maintainability by future volunteers | 4 | 4 | 3 |
| **Total (of 55)** | **50** | 45 | 42 |

**Chosen: FastAPI.** Best agent/MCP + Python-ML fit, matches prior art, typed. Django's
batteries (admin/ORM/auth) are tempting but its magic and monolith-first admin are a poor
fit for the governed-agent/MCP surface and typed-schema sharing we need. ADR-0001.

## Primary datastore
| Criterion | **PostgreSQL** | SQLite | MySQL |
|---|---|---|---|
| Data integrity / constraints | 5 | 3 | 4 |
| Concurrency (workers+api) | 5 | 2 | 4 |
| Extensibility (JSONB, RLS-capable) | 5 | 3 | 3 |
| Deployment portability | 4 | 5 | 4 |
| Cost | 5 | 5 | 5 |
| **Total (of 25)** | **24** | 18 | 20 |

**Chosen: PostgreSQL.** SQLite (prototype) cannot serve concurrent api+worker with the
integrity + JSONB + optional row-level-security we want. ADR-0002.

## Async / worker system
| Criterion | **Celery+Redis** | Arq | DB-only cron |
|---|---|---|---|
| Durability / retries | 5 | 4 | 3 |
| Operational maturity | 5 | 3 | 4 |
| Scheduled jobs (beat) | 5 | 4 | 3 |
| Complexity | 3 | 4 | 5 |
| **Total (of 20)** | **18** | 15 | 15 |

**Chosen: Celery + Redis** (beat for scheduling). Arq is lighter but Celery's maturity,
retries, and beat win for reminders/digests. Redis also serves cache + locks. ADR-0003.
Outbox pattern makes the choice replaceable.

## Frontend
| Criterion | **Next.js/React+TS** | Plain Vite/React | HTMX/server |
|---|---|---|---|
| Public SEO/perf (SSR/SSG) | 5 | 3 | 4 |
| Accessible component ecosystem | 5 | 4 | 3 |
| Typed API sharing | 5 | 5 | 3 |
| Complexity | 3 | 4 | 4 |
| **Total (of 20)** | **18** | 16 | 14 |

**Chosen: Next.js/React+TS.** SSR/SSG matters for the public front door + mobile. Plain
Vite (prototype) is fine for the app shell but weaker for public SEO/perf. ADR-0004.

## Rejected alternatives (summary)
- **Supabase/Firebase BaaS:** fast start but weak governed-agent/MCP story, vendor
  lock-in, and RLS-only authz is a poor fit for our role×scope matrix.
- **Microservices from day one:** violates the modular-monolith principle; premature
  operational cost for a small nonprofit.
- **A no-code CMS (Wagtail/Strapi) as the core:** good CMS, wrong center of gravity for an
  operational + agent platform; we build a focused content module instead.

## Guiding rule
Do not select a complex/fashionable technology without a scored reason. Every major choice
above has an ADR in `docs/adr/`.
