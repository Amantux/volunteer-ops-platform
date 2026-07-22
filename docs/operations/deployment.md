---
title: Deployment
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [../architecture/system-design.md, ../architecture/domain-model.md, ../product/non-goals.md]
---

# Deployment

This describes the Docker Compose baseline for the Volunteer Operations Platform. Per
`system-design.md` §1 and `non-goals.md`, **Docker Compose is the baseline**; Kubernetes
is a non-goal unless operationally justified (see "When Kubernetes would be justified"
below). Commands below assume the standard repo layout (`docker-compose.yml` at repo
root) and are the intended commands for this stack — verify paths/tags against the
actual repo before running in a new environment.

## 1. Compose topology & service responsibilities

| Service     | Image/runtime        | Responsibility                                                                 | Exposed to |
|-------------|-----------------------|---------------------------------------------------------------------------------|------------|
| `proxy`     | Caddy or nginx        | TLS termination, reverse proxy to `web`/`api`, HTTP→HTTPS redirect, static caching | Internet |
| `web`       | Next.js (Node)        | Public site (SSR/SSG) + authenticated app SPA                                    | `proxy` only |
| `api`       | FastAPI (Python)      | Modular monolith: domain services, authz, outbox writes, MCP-adjacent app services | `proxy`, `worker`, `mcp` |
| `worker`    | Celery (Python)       | Idempotent async jobs: email send, reminders, imports, digests, agent jobs, outbox relay | `redis`, `postgres`, `minio`, provider APIs |
| `scheduler` | Celery beat           | Cron-like triggers for recurring jobs (digests, qualification-expiry checks, reconciliation sweeps) | `redis` |
| `mcp`       | FastAPI/MCP server    | Governed narrow tool surface for agents; shares authz + audit with `api`          | `worker`/agent runtime only, never public |
| `postgres`  | PostgreSQL            | Source of truth: all org-scoped domain state + outbox table                     | `api`, `worker`, `scheduler` |
| `redis`     | Redis                 | Celery broker/result backend, cache, distributed locks                          | `api`, `worker`, `scheduler` |
| `minio`     | MinIO (S3-compatible) | Object storage: uploads, generated documents                                    | `api`, `worker` |

`proxy` is the only service that should ever have a host-mapped public port. Everything
else stays on the compose-internal network.

## 2. Environment variables & secrets

Secrets come from a secrets manager or a protected env file injected at deploy time —
**never committed**. `.env` (if used locally) must be gitignored; production secrets are
injected via the host's secrets manager (e.g. Docker secrets, cloud secrets manager, or a
protected CI/CD variable store) and referenced by the compose file, not hardcoded.

### Required by service

**`api` / `worker` / `scheduler` (shared config)**
| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres DSN, e.g. `postgresql+asyncpg://user:pass@postgres:5432/volunteer_ops` |
| `REDIS_URL` | Redis DSN, e.g. `redis://redis:6379/0` (broker); a separate `/1` db recommended for cache |
| `APP_SECRET` / `JWT_SECRET` | Session/token signing key — high-entropy, rotated per rotation policy |
| `S3_ENDPOINT_URL` | MinIO/S3 endpoint |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | Object storage credentials |
| `S3_BUCKET_UPLOADS` / `S3_BUCKET_DOCUMENTS` | Bucket names |
| `EMAIL_PROVIDER` | e.g. `ses` / `sendgrid` / `postmark` |
| `EMAIL_PROVIDER_API_KEY` | Provider credential |
| `EMAIL_FROM_ADDRESS` | Default sender for transactional + campaign mail |
| `STRIPE_SECRET_KEY` | Payment provider server key |
| `STRIPE_WEBHOOK_SECRET` | Verifies inbound webhook signatures (see non-goals: never store card data — provider holds PCI scope) |
| `ORG_BOOTSTRAP_TOKEN` | One-time token consumed by first-run bootstrap (see §5) |
| `LOG_LEVEL` | e.g. `info` in prod |
| `ENVIRONMENT` | `production` / `staging` / `development` — gates debug features |

**`web`**
| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Public URL the browser calls (through `proxy`) |
| `API_INTERNAL_BASE_URL` | Server-side (SSR) URL to reach `api` directly on the compose network |

**`mcp`**
| Var | Purpose |
|---|---|
| `MCP_API_BASE_URL` | Internal URL to `api` |
| `MCP_ALLOWED_CLIENTS` | Allowlist of registered MCP client identities (defense in depth alongside DB-backed `MCPClient` records) |

**`proxy`**
| Var | Purpose |
|---|---|
| `TLS_DOMAIN` | Domain for automatic cert (Caddy) or path to cert/key (nginx) |
| `TLS_CERT_EMAIL` | ACME registration contact (Caddy/Let's Encrypt) |

Secrets rotation: rotate `APP_SECRET`/`JWT_SECRET`, provider API keys, and DB credentials
on the org's documented schedule (minimum annually, immediately on suspected compromise);
rotating `APP_SECRET` invalidates existing sessions/tokens by design.

## 3. Database migrations

Alembic migrations are additive and reversible per module (see `domain-model.md`
"Migration plan" for module bring-up order). Intended commands:

```bash
# Apply all pending migrations (run before starting api/worker on a new version)
docker compose run --rm api alembic upgrade head

# Check current DB revision vs. latest
docker compose run --rm api alembic current
docker compose run --rm api alembic heads

# Roll back one revision (see rollback §7 before doing this in prod)
docker compose run --rm api alembic downgrade -1
```

Never run migrations from more than one deploying process concurrently; the deploy
script should run migrations as a single gated step before rolling `api`/`worker`.

## 4. Health / readiness / liveness endpoints

| Service | Endpoint | Checks |
|---|---|---|
| `api` | `GET /healthz` | Process is up (liveness) |
| `api` | `GET /readyz` | DB reachable, Redis reachable, migrations at head (readiness) |
| `worker` | Celery inspect (`celery -A app inspect ping`) | Worker process responsive |
| `scheduler` | beat heartbeat row / log freshness | Beat is ticking (see runbooks.md "stale beat") |
| `mcp` | `GET /healthz` | Process is up |
| `web` | `GET /api/health` (Next.js route) | SSR process up |

Compose healthchecks should point `proxy` and orchestration restart policies at
`/readyz` for `api`, not just `/healthz` — a live-but-not-ready `api` (e.g. DB down)
should not receive traffic.

## 5. Reverse proxy & TLS

`proxy` terminates TLS and routes:
- `/` and app routes → `web`
- `/api/*` (or configured API prefix) → `api`
- MCP surface is **not** proxy-exposed publicly; it's reached only by the agent
  runtime on the internal network.

Caddy: automatic cert issuance/renewal via `TLS_DOMAIN`/`TLS_CERT_EMAIL`, zero manual
cert management. nginx: mount cert/key volumes and run a renewal sidecar (e.g. certbot)
or terminate TLS upstream (load balancer) and run nginx in HTTP-only mode internally.

## 6. First-run bootstrap (create org + admin)

Intended sequence for a brand-new deployment:

```bash
docker compose up -d postgres redis minio
docker compose run --rm api alembic upgrade head
docker compose up -d api worker scheduler mcp proxy web

# Bootstrap the first organization + admin user (one-time; consumes ORG_BOOTSTRAP_TOKEN)
docker compose run --rm api python -m app.cli bootstrap-org \
  --name "Example Volunteer Org" \
  --slug example-org \
  --admin-email admin@example-org.org \
  --token "$ORG_BOOTSTRAP_TOKEN"
```

This creates the `Organization`, an initial `OrganizationSetting` set, the admin `Person`
+ `User` + `Role` assignment (org-scoped `org_admin`), and sends a magic-link email to the
admin. Rotate/invalidate `ORG_BOOTSTRAP_TOKEN` after use — it should only work once per
org (enforced server-side, not just by convention).

## 7. Zero/low-downtime deploy notes

- **Migrations first, additive-only.** Ship a migration in the same release as the code
  that needs it, but make it backward-compatible with the *previous* code version for the
  duration of the rollout (add-column-nullable, expand/contract pattern) so old and new
  `api`/`worker` containers can briefly coexist during a rolling restart.
- **Roll `worker`/`scheduler` before `api`** if a job payload shape changed, so workers can
  handle in-flight messages produced by either version; otherwise roll `api` first.
- **`scheduler` (beat) must run as a single instance.** Scaling it introduces duplicate
  triggers; use compose to guarantee `replicas: 1` (or an external lock) if the orchestrator
  supports scaling.
- Compose itself does rolling restarts sequentially (`docker compose up -d --no-deps
  <service>`); for true zero-downtime on a single VM, run two `api`/`web` containers behind
  `proxy` and restart one at a time (`docker compose up -d --no-deps --scale api=2 api`,
  drain, repeat) — only worth it once traffic justifies it.

## 8. Rollback

- **Pin image tags**, never `:latest`, in the deploy manifest — rollback is
  `docker compose up -d --no-deps <service>` after re-pinning the previous tag.
- **Migration reversibility:** every Alembic migration should have a working `downgrade()`.
  Before rolling back application code past a migration boundary, run
  `alembic downgrade -1` (or to the specific prior revision) *first*, confirm `alembic
  current` matches the prior code's expected head, then redeploy the prior image tags.
  If a migration was destructive (dropped a column/table), it cannot be cleanly reversed —
  destructive migrations must ship in a separate release from the code rollback, behind an
  expand/contract window (see non-goals: no silent data loss).
- Verify after rollback: `GET /readyz` on `api`, `alembic current`, spot-check one write
  path end to end.

## 9. Other-organization deployment checklist (config-only, no code changes)

Standing up a **new organization on shared infrastructure** is a data-layer operation
(create an `Organization` row + settings), not a new deployment — do this via the
bootstrap CLI (§6), not a new compose stack.

Standing up a **new, isolated deployment** (separate infra) for another organization:
- [ ] New `.env`/secrets set: fresh `APP_SECRET`/`JWT_SECRET`, fresh DB credentials,
      fresh MinIO bucket names, org-specific `EMAIL_FROM_ADDRESS`.
- [ ] New TLS domain configured in `proxy` (`TLS_DOMAIN`).
- [ ] Own Postgres volume/instance and MinIO bucket set — no shared storage with other orgs.
- [ ] Own Stripe (or payment provider) account/keys — never share payment credentials
      across organizations.
- [ ] Run migrations to head (§3), then first-run bootstrap (§6) with the new org's details.
- [ ] Confirm no code changes were required — if a change to the codebase seemed necessary
      to onboard this organization, that's a signal it belongs in `OrganizationSetting`
      (feature flags, terminology map, policies), not a fork. Flag it instead of forking.
- [ ] Confirm backup job (see `backups.md`) is configured for the new instance before
      go-live.

## 10. Small deployment (single VM)

The default target: one VM (2-4 vCPU / 4-8GB RAM is enough for a small nonprofit's
volume), Docker + Docker Compose, all services from `docker-compose.yml` on that host,
Postgres/MinIO data on attached persistent disk, offsite backups (see `backups.md`).
This is sufficient for the expected scale of a single or small handful of organizations
per instance.

### When Kubernetes would be justified

Per `non-goals.md`: **no Kubernetes unless operationally justified.** Concrete triggers
that would justify revisiting (record the decision as an ADR if it happens):
- Need to run multiple `api`/`worker` replicas across >1 host for availability or load
  that a single VM (or a couple of VMs behind a simple LB) can no longer serve.
- Need for automated multi-zone failover beyond what a documented manual runbook covers.
- Operating enough separate organization deployments that per-VM management (not the
  app itself) becomes the bottleneck.
Until one of these is actually true, Compose-on-a-VM is the answer — do not introduce
Kubernetes speculatively.
