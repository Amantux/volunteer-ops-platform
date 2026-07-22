---
title: Incident Runbooks
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [deployment.md, backups.md, observability.md, ../architecture/system-design.md]
---

# Incident Runbooks

Each runbook: **Symptoms → Checks → Actions → Verification.** Commands are the intended
commands for this compose stack — adapt paths/names to the actual deployment. Escalate
per your org's on-call policy if actions below don't resolve within a reasonable window.

---

## 1. Queue has no active consumers

**Symptoms:** growing Redis/Celery queue depth; jobs (email, reminders, reconciliation)
not progressing; alert from `observability.md` "queue with no consumers" fires.

**Checks:**
```bash
docker compose ps worker
docker compose exec worker celery -A app inspect active
docker compose exec worker celery -A app inspect ping
docker compose logs --tail=200 worker
```

**Actions:**
- If `worker` container is down/crash-looping: `docker compose up -d worker`, then check
  logs for the crash cause (bad migration, missing env var, provider outage).
- If worker is up but not consuming: check Redis connectivity
  (`docker compose exec worker redis-cli -u "$REDIS_URL" ping`); restart worker
  (`docker compose restart worker`).
- If queue depth is high but workers are healthy: scale workers temporarily
  (`docker compose up -d --scale worker=2 worker`) to drain backlog.

**Verification:** `celery -A app inspect active` shows registered workers; queue depth
metric trending down; spot-check one recent job (e.g. an email send) completed.

---

## 2. Scheduled task hasn't run (stale beat)

**Symptoms:** a recurring job (digest, qualification-expiry check, reconciliation sweep)
missed its expected run; `observability.md` "scheduled task didn't run" alert fires.

**Checks:**
```bash
docker compose ps scheduler
docker compose logs --tail=200 scheduler
docker compose exec scheduler celery -A app inspect scheduled
```

**Actions:**
- Confirm exactly **one** `scheduler` instance is running — duplicate/scaled beat
  instances cause double- or missed-firing (see `deployment.md` §7).
- If `scheduler` crashed: `docker compose up -d scheduler`; check for a corrupted
  beat schedule file/DB entry and clear it if the beat backend persists schedule state.
- If `scheduler` is up but silent: check clock skew on the host (beat is time-based) and
  Redis connectivity.

**Verification:** next scheduled tick appears in `scheduler` logs at the expected time;
the freshness metric for that job resets.

---

## 3. Email failure rate over threshold / provider down (outbox backlog)

**Symptoms:** rising `EmailDeliveryEvent` failure rate or growing unprocessed
`OutboxEvent`/`EmailRecipient` backlog; `observability.md` "email failure over threshold"
alert fires.

**Checks:**
```bash
docker compose logs --tail=200 worker | grep -i email
# Query recent failures (adjust for actual schema/tooling)
docker compose exec api python -m app.cli email-failures --since 1h
```
Check the provider's own status page (`EMAIL_PROVIDER`) for an outage.

**Actions:**
- If provider outage: no action needed beyond monitoring — outbox is durable, jobs will
  retry and drain once the provider recovers. Communicate expected delay to comms managers
  if campaigns are time-sensitive.
- If provider auth/config error (e.g. rotated `EMAIL_PROVIDER_API_KEY` not updated):
  update the secret in the secrets manager, restart `worker` to pick it up.
- If bounces/complaints spike (not an outage): pause active `EmailCampaign`s
  (`status → paused`) to avoid reputation damage before investigating the audience
  definition or template.

**Verification:** failure rate returns below threshold; outbox backlog (`outbox_event
WHERE processed_at IS NULL`) draining; a test send succeeds.

---

## 4. Payment events cannot be reconciled

**Symptoms:** `PaymentEvent` rows unreconciled beyond expected window; `observability.md`
"payment reconciliation gap" alert fires.

**Checks:**
```bash
docker compose exec api python -m app.cli payment-reconciliation-report --since 24h
docker compose logs --tail=200 worker | grep -i webhook
```
Confirm webhook signature verification isn't silently rejecting valid events (check
`STRIPE_WEBHOOK_SECRET` matches what's configured in the provider dashboard).

**Actions:**
- If webhook secret mismatch: correct the secret, then use the provider's dashboard to
  **replay** missed webhook events (idempotency key protects against double-processing —
  `system-design.md` §3).
- If provider outage: wait and monitor; do not manually construct `PaymentEvent` rows
  outside the webhook path (bypasses signature verification and the audit trail).
- Never manually mark a donation reconciled without a corresponding verified
  `PaymentEvent` — that's a financial-integrity, not just an ops, decision; escalate to
  whoever holds Finance-manager authority.

**Verification:** reconciliation report shows the gap closed; spot-check a specific
`Donation`'s `PaymentEvent` link.

---

## 5. Background jobs repeatedly failing

**Symptoms:** the same job (by name/type) hits max retries repeatedly; error rate alert
fires; `observability.md` "repeated job failures" alert.

**Checks:**
```bash
docker compose logs --tail=500 worker | grep -i "ERROR\|Retry"
docker compose exec worker celery -A app inspect stats
```

**Actions:**
- Identify whether the failure is data-shaped (one bad row — e.g. malformed import file)
  vs. systemic (a code/config bug affecting all jobs of that type).
- Data-shaped: quarantine/skip the offending item, log it for manual follow-up, let the
  rest of the queue proceed.
- Systemic: stop the affected job type from continuing to retry-storm
  (`celery -A app control revoke <task_id>` for in-flight, or pause the producing
  trigger), roll back the change that introduced it per `deployment.md` §8.

**Verification:** job type resumes succeeding; no new entries in the dead-letter/failure
log for that type over a monitoring window.

---

## 6. Agent runs stuck

**Symptoms:** an `AgentRun` sits in a non-terminal state past its expected duration;
`observability.md` "stuck agent runs" alert fires.

**Checks:**
```bash
docker compose exec api python -m app.cli agent-runs --status in_progress --older-than 30m
docker compose logs --tail=200 worker | grep -i agent
```

**Actions:**
- Confirm the agent run isn't legitimately waiting on a human `ApprovalRequest`
  (expected — agents never self-escalate or bypass approval per `non-goals.md`
  "Agent/automation non-goals"). If it's genuinely blocked on approval, that's not an
  incident — surface it, don't force it through.
- If actually stuck (worker crashed mid-run, no approval pending): mark the run failed/
  cancelled via the CLI, do **not** manually approve or auto-complete its proposal to
  clear the backlog — that would bypass the control plane the non-goals require.
- Restart `worker` if the stall is worker-side.

**Verification:** stuck-run count returns to zero or to only genuinely-pending-approval
runs; no proposals were force-approved to resolve this.

---

## 7. MCP client anomalous behavior

**Symptoms:** unusual volume/pattern of `MCPToolInvocation`s from a client, tool calls
outside the client's normal allowlisted pattern, or repeated authorization denials from
an MCP tool; `observability.md` "anomalous MCP client" alert fires.

**Checks:**
```bash
docker compose exec api python -m app.cli mcp-invocations --client <client_id> --since 1h
docker compose logs --tail=200 mcp
```
Cross-check against `audit_event` for denied actions from that client (authz is enforced
inside MCP tools per `system-design.md` §5 and `permissions.md`).

**Actions:**
- If credential compromise suspected: revoke/rotate that `MCPClient`'s credential
  immediately (`MCP_ALLOWED_CLIENTS` + DB-backed record), forcing re-registration.
- If it's a misbehaving-but-legitimate integration: pause the client's access, review its
  tool-call pattern against its declared allowlist, fix and re-enable.
- Recall the non-goal: MCP never has raw DB/shell/Docker/secret access — anomalous
  behavior should be contained to what a tool *can* do, which is already narrow.

**Verification:** invocation pattern returns to baseline; no further denied actions from
this client; incident logged in `audit_event`/ops log.

---

## 8. Backups failed

**Symptoms:** scheduled backup job (per `backups.md` §2) didn't complete or didn't
upload; `observability.md` "backup failure" alert fires.

**Checks:**
```bash
docker compose logs --tail=200 <backup-runner-service-or-cron-container>
ls -la ./backups/   # or check offsite bucket listing
mc ls offsite/ | tail -5
```

**Actions:**
- Disk-space exhaustion: free space on the host (rotate old local dumps per retention),
  re-run the dump command from `backups.md` §4.
- Offsite upload failure (credential/network): fix credential in secrets manager or
  network path, re-run the upload step.
- Re-run the full backup command manually if the scheduled run failed for any reason —
  do not let more than one backup cycle pass without a successful run.

**Verification:** a fresh dump/snapshot appears offsite with today's timestamp; run the
quarterly-drill restore check (`backups.md` §5) if this is the first failure in a while,
to confirm the *repaired* pipeline actually produces a restorable artifact.

---

## 9. Telemetry stopped

**Symptoms:** metrics/logs stop arriving from one or more services;
`observability.md` "telemetry stopped" alert fires (itself dependent on telemetry still
flowing to raise the alert — see note below).

**Checks:**
```bash
docker compose ps
docker compose logs --tail=100 <affected-service>
# Check the metrics/log shipping agent itself, if separate from app containers
docker compose logs --tail=100 <telemetry-agent-service>
```

**Actions:**
- If the affected service itself is down: restart it (see relevant runbook above for
  that service).
- If the service is up but not emitting: restart the telemetry/log-shipping sidecar or
  agent; check its own connectivity to wherever metrics/logs are stored.
- **Note the blind-spot risk:** a telemetry-stopped alert that depends entirely on the
  same telemetry pipeline can't fire during a full pipeline outage — treat "unexpected
  quiet" on the status page (`observability.md`) as itself a signal to check manually,
  not only alert-driven.

**Verification:** metrics/log stream resumes with current timestamps; status page
reflects live data again.

---

## 10. Unauthorized-access-attempt spike

**Symptoms:** spike in authentication failures, permission denials, or repeated access
attempts against protected routes/MCP tools from one source; `observability.md`
"unauthorized-access spike" alert fires.

**Checks:**
```bash
docker compose logs --tail=500 api | grep -i "401\|403\|auth"
docker compose exec api python -m app.cli audit-events --action denied --since 1h
```
Identify: single account (credential stuffing / compromised account) vs. single IP/
source (scanning) vs. distributed (broader attack).

**Actions:**
- Single compromised account: force logout (invalidate sessions/tokens), require
  password/magic-link reset, review that account's recent audit trail for damage.
- Single-source scanning: block at `proxy`/firewall level; confirm rate limiting on
  public routes (`system-design.md` §5) is active and tune if it let this through.
- Broader spike: engage rate limiting/bot controls more aggressively on public forms;
  consider temporarily tightening MFA/step-up requirements for privileged roles.

**Verification:** failure/denial rate returns to baseline; affected accounts confirmed
secured; incident logged in `audit_event` and ops log.

---

## 11. Database migration needs rollback/recovery

**Symptoms:** a deployed migration broke the app (`api`/`worker` failing `/readyz` or
crash-looping post-deploy), or a migration applied incorrect/destructive changes.

**Checks:**
```bash
docker compose run --rm api alembic current
docker compose run --rm api alembic history --verbose | head -20
docker compose logs --tail=200 api
```

**Actions:** follow `deployment.md` §8 (Rollback) precisely:
1. Stop `api`/`worker`/`scheduler` to prevent further writes against the broken schema.
2. `alembic downgrade -1` (or to the last-known-good revision).
3. If the migration was destructive (data already lost — dropped column/table), this is
   a **restore-from-backup** situation, not a downgrade — go to `backups.md` §5 and
   restore into an isolated instance first, confirm, then plan the cutover; do not
   downgrade-and-hope on top of already-lost data.
4. Re-deploy the previous application image tag matching that migration state.
5. Restart services.

**Verification:** `alembic current` matches the expected prior revision; `/readyz`
green; smoke-check one write path; if a restore was needed, follow the restore
verification steps in `backups.md` §5 exactly.

---

## 12. Redis restart

**Symptoms:** `redis` container restarted (crash, OOM, host reboot, manual restart).

**Checks:**
```bash
docker compose ps redis
docker compose logs --tail=100 redis
docker compose exec worker celery -A app inspect ping
```

**Actions:**
- Expected impact: in-flight (unacknowledged) Celery messages and cache entries are
  lost; durable domain state is unaffected (outbox pattern — `system-design.md` §3).
  Committed-but-not-yet-relayed `OutboxEvent` rows will be picked back up by the worker's
  normal outbox-polling/relay logic once `worker` reconnects.
- Confirm `worker`/`api`/`scheduler` reconnect automatically (they should, via standard
  Redis client retry); restart them manually if they don't
  (`docker compose restart worker scheduler api`).
- If restarts are recurring (not a one-off), check Redis memory limits/eviction policy
  and host resource pressure — this is a capacity issue, not just an incident to clear.

**Verification:** `celery -A app inspect ping` responds from all workers; outbox backlog
(`outbox_event WHERE processed_at IS NULL`) drains to its normal baseline within a few
minutes; no data-loss beyond the expected transient-queue/cache scope above.
