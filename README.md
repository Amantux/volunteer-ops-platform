# Volunteer Operations Platform

[![CI](https://github.com/Amantux/volunteer-ops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Amantux/volunteer-ops-platform/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Node 20](https://img.shields.io/badge/node-20-blue)

An operational system for running a volunteer organization end-to-end — public engagement,
onboarding, training, scheduling, communications, a website builder, internal workflows, and
**governed** automation (AI agents + MCP). It is deliberately **not** a brochure site with a
signup form: it supports the full volunteer lifecycle, and a second organization onboards by
**configuration, not a rewrite**.

Deployment is **single-tenant per instance** (one org per deployment) — isolation is the
instance boundary, not a `WHERE` clause.

## Features
- **Public site + CMS** — a simplified website builder: block-based pages with a sanitized
  custom-HTML/CSS escape hatch, served at clean URLs. Public opportunities + a unified calendar.
- **Volunteers & scheduling** — passwordless magic-link auth, scope-aware RBAC, events/shifts/
  roles, eligibility, waitlists, check-in, hours, and volunteer + coordinator dashboards.
- **Training & communications** — courses/sessions, qualifications, approval-gated email
  campaigns with audience preview, suppression/unsubscribe — all via a transactional outbox.
- **Forms & workflow engine** — a new operational process (incident reports, maintenance,
  reimbursements) is *config*: a form definition + a state machine, with approvals and audit.
- **Social media** — draft (with optional LLM assist) → approve → schedule → publish, with a
  hard human-approval gate; agents may draft but never publish.
- **Governed automation** — an agent control plane where *confidence never grants authority*
  (R0–R4 risk levels) and an MCP tool layer that splits read from write, all permissioned + audited.

## Tech stack
Modular monolith: **FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic**, **Celery + Redis** for
background work behind a transactional **outbox**, **Next.js 14 + TypeScript** frontend, and a
governed **MCP** interface. Runs on **Docker Compose** (Caddy for TLS in production).

## Quickstart (development)
```bash
# Full stack (API + web + Postgres + Redis + worker + beat)
docker compose up --build          # → web http://localhost:3000 · API http://localhost:8000

# Or run the backend directly:
cd backend
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q      # tests (SQLite, ~4s)
.venv/bin/uvicorn app.main:app --reload
```

## Deploy to production
Single VM + Docker Compose with automatic TLS. See **[docs/operations/deployment.md](docs/operations/deployment.md)**
and the **[launch checklist](docs/operations/launch-checklist.md)**. The app *refuses to start*
with an insecure production configuration (weak secret, non-https, dev email sink, …).

```bash
cp .env.prod.example .env.prod       # fill in secrets
docker compose -f compose.prod.yml --env-file .env.prod up -d --build
```

## Testing & CI
`ruff` + `mypy` + `pytest` + Alembic migration-drift check (backend), `tsc` + `next build`
(frontend), Playwright + axe (e2e), and `pip-audit` + `bandit` + `npm audit` (security) — all
run on every push and PR ([workflow](.github/workflows/ci.yml)).

## Documentation
- **Product:** [vision](docs/product/vision.md) · [requirements](docs/product/requirements.md) · [non-goals](docs/product/non-goals.md)
- **Architecture:** [system design](docs/architecture/system-design.md) · [implemented state](docs/architecture/implemented-state.md) · [domain model](docs/architecture/domain-model.md) · [permissions](docs/architecture/permissions.md) · [multi-tenancy](docs/architecture/multi-tenancy.md)
- **Safety:** [threat model](docs/security/threat-model.md) · [agent permissions](docs/agents/agent-permissions.md)
- **Roadmap:** [phased plan](docs/roadmap/phased-plan.md) · [backlog](docs/roadmap/backlog.md)
- **Operations:** [deployment](docs/operations/deployment.md) · [backups](docs/operations/backups.md) · [observability](docs/operations/observability.md)
- **Full index:** [docs/README.md](docs/README.md)

## Contributing & security
Contributions welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)** and the
**[Code of Conduct](CODE_OF_CONDUCT.md)**. To report a vulnerability, see **[SECURITY.md](SECURITY.md)**
(please do not open a public issue for security reports).

## License
[MIT](LICENSE).
