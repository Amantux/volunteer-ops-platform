---
title: ADR-0001 — Backend framework: FastAPI
owner: Architecture
status: accepted
last_reviewed: 2026-07-22
---

# ADR-0001: Use FastAPI (Python) for the backend

**Status:** Accepted · **Date:** 2026-07-22

## Context
We need a typed, testable backend that pairs well with a governed agent/MCP layer and
Python ML tooling, and that matches the team's prior art (`volunteer-hub`).

## Decision
Use **FastAPI** with Pydantic v2 and SQLAlchemy 2.0 over PostgreSQL. Structure as a
modular monolith (see system-design.md).

## Alternatives considered
- **Django** (score 45/55): excellent batteries (ORM/admin/auth) and integrity, but its
  admin-first monolith and ORM "magic" fit poorly with the typed-schema sharing and the
  governed MCP/agent surface we need.
- **Node/NestJS** (42/55): fine, but weaker Python-ML/agent ecosystem and no prior art.

## Consequences
+ Typed request/response, easy schema sharing with the frontend, strong agent/MCP fit.
+ Reuses team competence.
− We build auth/admin/ORM wiring ourselves (mitigated by a shared kernel + templates).
Full scoring in `docs/architecture/system-design.md`.
