---
title: ADR-0002 — Primary datastore: PostgreSQL
owner: Architecture
status: accepted
last_reviewed: 2026-07-22
---

# ADR-0002: Use PostgreSQL as the primary datastore

**Status:** Accepted · **Date:** 2026-07-22

## Context
Concurrent `api` + `worker` access, strong relational integrity for a large domain,
JSONB for extensible form/provider data, and optional row-level security for defense in
depth. The prototype used SQLite, which cannot meet these.

## Decision
Use **PostgreSQL** as the single source of truth. Every org-owned row carries `org_id`;
a repository base enforces the scope filter. Alembic manages reversible migrations.

## Alternatives considered
- **SQLite** (18/25): great for local/simple deploys but weak concurrency and constraints.
- **MySQL** (20/25): capable but weaker JSONB/constraint story than Postgres.

## Consequences
+ Integrity, concurrency, JSONB, and an RLS option for tenant isolation later.
− Requires a running Postgres in every environment (handled by Docker Compose).
