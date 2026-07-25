---
title: Deployment (single-VM Docker Compose)
owner: Operations
status: current
last_reviewed: 2026-07-25
applies_to: platform
---

# Deployment — one organization per VM (Docker Compose)

Each organization runs as its **own instance** (single-tenant per instance). This is the
production runbook for a single VM using `compose.prod.yml` + `Caddyfile` + `.env.prod`.

## Topology
Caddy (TLS at the edge) → `web` (Next.js) for pages and → `api` (FastAPI) for `/api/*`.
`worker` + `beat` run Celery against `redis`; data in `postgres`. Postgres/Redis have **no host
ports** (internal only). Schema is applied by the one-shot `migrate` service (`alembic upgrade
head`); `api` starts only after it succeeds — production never runs `create_all`.

## Prerequisites
- A VM (2 vCPU / 4 GB is ample for one org) with Docker + Docker Compose v2.
- A DNS A/AAAA record for `VOP_DOMAIN` → the VM's IP (Caddy needs it to issue the cert).
- Ports 80 + 443 open. A real SMTP relay (Postmark/SES/…) and a Cloudflare Turnstile secret.

## First deploy
1. `git clone` the repo onto the VM.
2. `cp .env.prod.example .env.prod` and fill EVERY value. Generate the app secret:
   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Use a strong DB password.
   `.env.prod` is gitignored — never commit it.
3. `docker compose -f compose.prod.yml --env-file .env.prod up -d --build`.
   - `migrate` runs `alembic upgrade head`; `api` waits for it. First boot seeds the org, roles,
     the admin (`VOP_BOOTSTRAP_ADMIN_EMAIL`), email templates, starter pages, and the incident
     form. **No demo content is seeded in production.**
4. Verify: `curl -fsS https://$VOP_DOMAIN/api/ready` returns `{"status":"ready"}` (DB + Redis OK).
   Visit `https://$VOP_DOMAIN`. The admin signs in via the magic link (passwordless).

**Fail-fast:** if `.env.prod` is incomplete/insecure (weak `VOP_APP_SECRET`, non-redis rate
limiter, bot-check off, non-https base URL, dev email sink) the `api`/`migrate` containers refuse
to start with a clear message (`app/core/production.py`). Fix the env and re-up.

## Upgrades (deploy a new version)
1. `git pull`.
2. `docker compose -f compose.prod.yml --env-file .env.prod up -d --build`.
   - Compose rebuilds images; `migrate` applies any new migrations before `api` restarts. Additive
     migrations make this effectively zero-downtime; a destructive migration needs a maintenance
     window (announce, then deploy).
3. Confirm `/api/ready` is 200 and check `docker compose -f compose.prod.yml logs -f api worker beat`.

## Rollback
1. `git checkout <previous-tag>` and re-`up --build`.
2. **Migrations don't auto-rollback.** If the bad release added a migration, downgrade explicitly:
   `docker compose -f compose.prod.yml run --rm migrate alembic downgrade -1` (only if that
   migration has a safe `downgrade()`), or restore from backup (see `backups.md`). Prefer
   forward-fixes over destructive downgrades.

## Operational commands
- Logs: `docker compose -f compose.prod.yml logs -f <service>`
- Shell: `docker compose -f compose.prod.yml exec api bash`
- Run a migration manually: `docker compose -f compose.prod.yml run --rm migrate alembic <cmd>`
- Restart workers: `docker compose -f compose.prod.yml restart worker beat`

## Health & monitoring
- `/api/health` (liveness) and `/api/ready` (readiness: DB + Redis). Caddy/uptime checks hit
  `/api/ready`. `/api/metrics` exposes outbox backlog — alert on it (see `observability.md`).
- `worker`/`beat` must be up for email, reminders, campaign/social publishing, and workflow
  escalations. Alert if the outbox `pending`/`stuck` count climbs (a dead worker).

## Onboarding a NEW organization = a new instance
Repeat "First deploy" on a fresh VM with that org's `VOP_DOMAIN`, secrets, and bootstrap values.
There is no shared database; isolation is the instance boundary. See `../architecture/multi-tenancy.md`.

See `launch-checklist.md` for the go/no-go gate, `backups.md` for backup/restore, and
`observability.md` for logging/alerting.
