# Volunteer Operations Platform

An operational system for running a volunteer organization end-to-end: public
engagement, training, onboarding, scheduling, communications, maintenance, donations,
reporting, and **governed** automation (agents + MCP). It is deliberately **not** a
brochure site with a signup form — it supports the full volunteer lifecycle.

Built org-scoped so a second organization onboards by **configuration, not a rewrite**.

> **Status: Phases 1–4 substantially built; deployment is single-tenant per instance.**
> Implemented and tested: passwordless auth + scope-aware RBAC, public site + training/onboarding,
> scheduling + volunteer/coordinator dashboards, communications (approval-gated campaigns +
> suppression), governed agents/MCP, CI. For the **verified** current state see
> `docs/architecture/implemented-state.md`; for status per phase see
> `docs/roadmap/phased-plan.md`. Designed-but-not-built (specs ready): forms/workflow engine,
> donations, internal ops modules, CMS, unified reporting.

## Architecture at a glance
Modular monolith: **FastAPI + PostgreSQL + Redis/Celery**, **Next.js/React + TypeScript**
front-end, S3/MinIO storage, transactional **outbox** for email/events, a **governed MCP**
interface, and an **agent control plane** where confidence never grants authority. Runs on
**Docker Compose**. Rationale and scoring: `docs/architecture/system-design.md`.

## Where to start reading
- **What & why:** `docs/product/vision.md`, `docs/product/non-goals.md`
- **The design:** `docs/architecture/system-design.md`, `docs/architecture/domain-model.md`,
  `docs/architecture/permissions.md`
- **Safety:** `docs/security/threat-model.md`, `docs/agents/agent-permissions.md`
- **The plan:** `docs/roadmap/phased-plan.md`, `docs/roadmap/first-slice.md`,
  `docs/roadmap/backlog.md`
- **Full index:** `docs/README.md`

## Principles (resolve design decisions with these)
Volunteer-first · low-friction public participation (progressive enrollment) · human-controlled
automation (separate confidence from permission to act) · configurable-not-hard-coded ·
modular-monolith-first · accessible & mobile-first.

## Prior art
`/root/volunteer-hub` was a throwaway prototype (React + FastAPI + SQLite, single shared
password). Its stack instincts carry forward; its code and single-org/no-auth/no-async
foundations do not. See `docs/architecture/current-state-audit.md`.
