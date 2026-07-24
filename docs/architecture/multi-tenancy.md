---
title: Tenancy Model — Single-Tenant Per Instance
owner: Architecture
status: proposed
last_reviewed: 2026-07-24
applies_to: platform
depends_on: [implemented-state.md, permissions.md, threat-model.md]
supersedes_brief_section: "Multi-tenant architecture (shared deployment)"
---

# Tenancy Model — Single-Tenant Per Instance

**Decision (owner directive, 2026-07-24): each organization runs as its own deployment
instance.** One instance serves exactly one org, with its own database, secrets, object
storage, and domain. This **overrides** the brief's "Multi-tenant architecture — multiple
organizations can use the same deployment" section. The reusable-framework goal is met by
deploying the *same codebase* many times, configured per instance — not by partitioning one
database across orgs.

## Why this is the right call here
- **The isolation boundary becomes infrastructure, not a `WHERE` clause.** Org A and org B
  cannot leak into each other because they share no database, no process, no bucket, no
  secret. This is a far stronger and simpler guarantee than in-app row filtering, and it
  removes the highest-risk failure mode (a forgotten `org_id` predicate) as a *cross-org*
  concern entirely.
- **Blast radius is one org.** A bad migration, a runaway job, a breach, or a noisy-neighbor
  load spike is contained to a single tenant.
- **Compliance & data residency** are per-instance knobs (region, retention, backup policy)
  instead of per-row policy engineering.
- **Operational simplicity** matches the team: no tenant-routing layer, no RLS, no
  shared-schema migration coordination across tenants.

Trade-off accepted: N instances cost more to run and upgrade than one shared cluster. That is
acceptable for the expected number of orgs and is revisited only if the deployment count grows
into the hundreds (see Non-goals).

## What this means for the existing code
The codebase is **already single-org at runtime** (`get_public_org` resolves the one
`bootstrap_org_slug`). That is now the *intended* end state, not a stopgap. Concretely:

- **`get_public_org` stays essentially as-is** — resolve the single org for this instance. No
  `TenantDomain` table, no host/subdomain routing, no `resolve_org(request)` fan-out. (An
  earlier draft of this doc designed that machinery; it is explicitly **dropped**.)
- **Keep `org_id` on every model and `OrgScopedRepository`.** Not for cross-tenant security —
  there is only one tenant per DB — but because:
  1. It is a cheap, already-present invariant that keeps the schema portable, so a future
     shared-tenant mode (if ever needed) does not require a data-model rewrite.
  2. It keeps every query, audit event, and background job explicitly org-anchored, which
     makes seed data, exports, and the eventual "clone this org's config to bootstrap a new
     instance" tooling straightforward.
  Treat removing `org_id` as out of scope: the cost of keeping it is ~zero, the cost of
  ripping it out (and possibly re-adding it) is high.
- **The session token still carries `org_id`** and authz still operates within it. On a
  single-tenant instance this is a consistency check (the token's org must equal the
  instance's org), not a routing decision.

## Isolation model (single-tenant)
Defense now lives at the deployment layer, with a light in-app backstop:

| Layer | Guarantee |
|---|---|
| **Instance** | Separate DB, Redis, object-storage bucket/prefix, secrets, and domain per org. This is the real boundary. |
| **Config** | Each instance is provisioned with exactly one org's identity, branding, and feature flags. No path exists to a second org because none is seeded. |
| **App (backstop)** | Every domain query is still org-scoped; a request whose token `org_id` ≠ the instance's org is rejected `403`. This catches misconfiguration (e.g. a token minted for the wrong instance), not a cross-tenant attacker. |

## Per-instance configuration surface
The brief's "per-organization" knobs become **per-instance** configuration, sourced from two
places:
- **Environment / secrets** (deploy-time): DB URL, email/payment/storage provider credentials,
  the org slug + display name, region, feature flags that gate whole modules.
- **`OrganizationSetting`** rows (run-time, editable by an org admin): branding (logo, colors),
  terminology overrides (display labels only — logic keys stay fixed, per assumption A5),
  custom onboarding track, email templates (already org-scoped rows), opportunity types.

"Configurable without custom code" is satisfied by these two surfaces; standing up a new org
is a **deployment + configuration** exercise, documented in the deployment runbook, not a code
change.

## Onboarding a new organization (replaces "tenant provisioning")
1. Provision infra for the instance (DB, Redis, storage bucket, domain, secrets).
2. Deploy the standard image.
3. Run the bootstrap seed with the org's slug/name/admin (existing `seed_bootstrap`).
4. Apply the org's `OrganizationSetting` config (branding, terminology, enabled modules).
5. Verify: health/readiness green, admin can sign in, public site renders the org's branding.

This belongs in `../operations/deployment.md` as a repeatable "new-instance" checklist.

## Testing implications (revised)
Because cross-tenant leakage is no longer a shared-DB threat, the previously-proposed
**two-org negative-test matrix is dropped as a security gate.** What remains valuable and in
scope:
- **Org-scoping sanity tests** (lightweight): a request carrying a token whose `org_id` ≠ the
  instance's org is rejected; object-fetch-by-id still checks `row.org_id` and returns 404 on
  mismatch. These keep the code honest and prevent misconfiguration bugs, at low cost.
- **A CI lint** for new unscoped `db.query(Model)` in `app/modules/**` — still worth having, as
  cheap insurance and good hygiene, even though the security stakes are lower.

The "2nd org onboards by config only" acceptance criterion (phased-plan Phase 8) is reframed:
**a second org onboards by standing up a second instance from config** — proven by running the
new-instance checklist end-to-end in staging, not by tenant-isolation tests against a shared DB.

## Non-goals
- No shared-database multi-tenancy, no tenant-routing layer, no Row-Level Security.
- No per-tenant billing/metering in the app (per-instance infra billing is an ops concern).
- Revisit a shared-tenant mode **only** if instance count grows large enough that per-org
  operational overhead dominates — at which point the retained `org_id` scoping is what makes
  that pivot feasible without a schema rewrite.
