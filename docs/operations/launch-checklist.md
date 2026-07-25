---
title: Production Launch Checklist (go / no-go)
owner: Operations
status: current
last_reviewed: 2026-07-25
applies_to: platform
---

# Production launch checklist

Gate for taking one organization instance live. Everything under **Must pass** is a hard blocker.

## Must pass (blockers)
- [ ] `.env.prod` complete; `VOP_ENVIRONMENT=prod`; `VOP_APP_SECRET` is a fresh ≥32-char random
      value (not the default). DB password is strong. Secrets are stored in a secret manager, not
      in git.
- [ ] The instance **boots** with the real env — the production guard (`app/core/production.py`)
      passes (redis rate-limiter, Turnstile bot-check, https base URL, real SMTP).
- [ ] TLS is live (Caddy issued a cert for `VOP_DOMAIN`); http → https; HSTS present.
- [ ] `alembic upgrade head` ran clean via the `migrate` service; `/api/ready` returns 200.
- [ ] `worker` + `beat` are running; a test email (magic link) is delivered end-to-end via the real
      SMTP relay; the outbox drains (no growing `pending`).
- [ ] Bootstrap admin can sign in; a smoke of each surface (public site, a training registration,
      a page edit+publish, an incident report → triage) works.
- [ ] **Backups** configured AND a restore has been tested at least once (`backups.md`).
- [ ] Monitoring wired: uptime check on `/api/ready`; an alert on `/api/metrics`
      `outbox_stuck`/`outbox_pending` and on worker/beat being down (`observability.md`).
- [ ] CI is green on the release commit, including the `security` job (pip-audit / bandit / npm audit).
- [ ] Off-host DB backups + retention set; VM disk encryption / managed-DB encryption-at-rest on.

## Should do (strongly recommended before real user data)
- [ ] Rotate the bootstrap admin to a real person; remove/disable the seed admin if placeholder.
- [ ] Turnstile keys are production keys for `VOP_DOMAIN`.
- [ ] Log shipping + retention configured; error tracking (`VOP_SENTRY_DSN`) if used.
- [ ] A staging instance mirrors prod for rehearsing upgrades/migrations.

## Deferred — track with an owner + date before handling sensitive data at scale
These are known gaps (see `../architecture/implemented-state.md` and the threat model):
- [ ] **MFA** for privileged users (TOTP) — admins currently rely on single-use magic links.
- [ ] **Application-level field encryption** for sensitive PII **once those fields exist**
      (emergency contact, background-check status). Today: TLS in transit + DB encryption-at-rest.
- [ ] **Object storage + file uploads** (waivers, incident photos) — the forms engine is designed
      for it; not yet wired.
- [ ] **Data-subject rights**: self-serve data export + account deletion/anonymisation.
- [ ] **Load test** the two spikes: registration-open and mass campaign/social send.
- [ ] Refresh `../security/threat-model.md` for CMS custom-HTML, social publishing, and the forms
      engine surfaces.

## Rollback readiness
- [ ] Previous image tag is known and re-deployable; a recent backup is restorable within the RTO.
