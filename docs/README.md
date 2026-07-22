---
title: Documentation Index
owner: Platform
status: current
last_reviewed: 2026-07-22
applies_to: platform
---

# Documentation Index

Docs are written to be useful to both humans and retrieval agents. Every doc carries
frontmatter (title, owner, status, last_reviewed, applies_to, and depends_on where useful).

## Product
- [product/vision.md](product/vision.md) — mission, principles, success signals.
- [product/personas.md](product/personas.md) — user groups, JTBD, must/must-not-see.
- [product/user-journeys.md](product/user-journeys.md) — end-to-end journeys (incl. the first slice).
- [product/requirements.md](product/requirements.md) — MoSCoW functional requirements with IDs.
- [product/non-goals.md](product/non-goals.md) — explicit scope boundaries.

## Architecture
- [architecture/current-state-audit.md](architecture/current-state-audit.md) — prior art + gaps.
- [architecture/system-design.md](architecture/system-design.md) — architecture + **scoring**.
- [architecture/domain-model.md](architecture/domain-model.md) — ERD + entities (org-scoped).
- [architecture/permissions.md](architecture/permissions.md) — RBAC + capability matrix.
- [architecture/data-flow.md](architecture/data-flow.md) — outbox, events, idempotency.
- [architecture/integrations.md](architecture/integrations.md) — provider adapters.
- [architecture/mcp-design.md](architecture/mcp-design.md) — governed MCP resources + tools.

## Agents
- [agents/agent-control-plane.md](agents/agent-control-plane.md) — action records, risk, approval.
- [agents/agent-permissions.md](agents/agent-permissions.md) — per-agent capabilities + hard limits.

## Security
- [security/threat-model.md](security/threat-model.md) — threats → mitigations.
- [security/data-classification.md](security/data-classification.md) — data tiers + handling.

## Operations
- [operations/deployment.md](operations/deployment.md) — compose, env, migrations, rollback.
- [operations/backups.md](operations/backups.md) — backup + tested restore.
- [operations/runbooks.md](operations/runbooks.md) — incident runbooks.
- [operations/observability.md](operations/observability.md) — instrumentation + alerts.

## Testing & Metrics
- [testing/test-strategy.md](testing/test-strategy.md) — test pyramid + CI gate.
- [metrics/metric-dictionary.md](metrics/metric-dictionary.md) — every metric defined.

## Roadmap
- [roadmap/phased-plan.md](roadmap/phased-plan.md) — phases 0–8 with exit criteria.
- [roadmap/first-slice.md](roadmap/first-slice.md) — the first vertical slice spec.
- [roadmap/backlog.md](roadmap/backlog.md) — prioritized backlog with acceptance criteria.

## Decisions
- [adr/](adr/) — ADR-0001 FastAPI · 0002 PostgreSQL · 0003 Celery+Redis+outbox · 0004 Next.js.

## Reading order for a new contributor
1. `product/vision.md` + `product/non-goals.md`
2. `architecture/system-design.md` + `architecture/domain-model.md` + `architecture/permissions.md`
3. `security/threat-model.md` + `agents/agent-permissions.md`
4. `roadmap/first-slice.md` (what we build first)
