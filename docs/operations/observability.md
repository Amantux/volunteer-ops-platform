---
title: Observability
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [deployment.md, backups.md, runbooks.md, ../architecture/system-design.md]
---

# Observability

This defines what to instrument, the alerts derived from those signals, and the internal
system-status page. Every alert links to the corresponding runbook in `runbooks.md` — an
alert without an actionable runbook is not worth shipping.

## 1. What to instrument

| Area | Signal | Notes |
|---|---|---|
| **API health** | `/healthz`, `/readyz` status; request latency (p50/p95/p99); 5xx rate | `/readyz` failing is more urgent than `/healthz` — see `deployment.md` §4 |
| **Background job health** | Celery task success/failure rate per task name; retry counts; task duration | Per-task-name breakdown, not just aggregate — one noisy task shouldn't mask a silent one |
| **Queue depth** | Redis/Celery queue length per queue | Sustained growth = consumers not keeping up |
| **Consumer count** | Number of active Celery workers registered (`inspect active`) | Zero consumers with nonzero queue depth is the clearest "queue stuck" signal |
| **Scheduled-job freshness** | Time since last successful run, per beat-scheduled job | Compare against expected cadence (e.g. "digest job: expected every 24h") |
| **Email success/failure** | `EmailDeliveryEvent` counts by status (delivered/bounce/complaint/failed) | Rate, not just count — a small org's absolute volume is low |
| **Webhook failures** | Inbound webhook (payment, email-provider) signature-verification failures and processing errors | Distinguish "rejected bad signature" (expected background noise) from "valid signature, processing error" (real bug) |
| **MCP tool use** | `MCPToolInvocation` count, per client, per tool, with authz-denied count | Baseline per client so anomalies are detectable |
| **Agent execution + approval rates** | `AgentRun` outcome distribution, time-in-state, `AgentProposal` approval/rejection rate | Non-goal reminder: agents never self-approve — approval rate should never read as "agent approved itself" |
| **DB performance** | Connection pool saturation, slow-query log, replication lag (if any read replica), lock waits | |
| **Cache health** | Redis memory usage, eviction rate, hit/miss ratio (cache DB, separate from broker DB) | |
| **Auth failures** | Failed login/magic-link attempts, MFA failures, rate by account and by source IP | |
| **Permission denials** | Count of `authorize()` denies, per user/role/action | Every deny is already audit-logged per `permissions.md` — surface the rate here |
| **Public-form abuse** | Submission rate per form/IP, rate-limit trigger count, bot-control (captcha/honeypot) trigger count | |
| **Payment reconciliation** | Count of `PaymentEvent` rows unreconciled beyond expected window, by age bucket | |
| **Backup completion** | Success/failure + timestamp + artifact size of each scheduled backup job (`backups.md` §2) | Size sanity-check catches a "succeeded but empty" backup |
| **Telemetry freshness** | Last-received timestamp per service's metrics/log stream | Self-referential blind spot noted in `runbooks.md` #9 — pair with an external dead-man's-switch style check if possible |

## 2. Alerts

| Alert | Trigger | Runbook |
|---|---|---|
| Queue with no active consumers | Consumer count = 0 **and** queue depth > 0 for > 5 min | `runbooks.md` #1 |
| Scheduled task didn't run | Time-since-last-success exceeds expected cadence + grace window (e.g. cadence + 30 min) | `runbooks.md` #2 |
| Email failure over threshold | Email failure rate > threshold (e.g. >10% over 15 min, tune per org's send volume) **or** unprocessed outbox backlog growing for > 15 min | `runbooks.md` #3 |
| Payment reconciliation gap | Unreconciled `PaymentEvent` count > 0 beyond expected settlement window (e.g. > 1 hour) | `runbooks.md` #4 |
| Repeated job failures | Same task name hits max-retry/dead-letter more than N times in a window (e.g. 5 in 10 min) | `runbooks.md` #5 |
| Stuck agent runs | `AgentRun` in non-terminal state longer than its expected max duration **and** not waiting on a pending `ApprovalRequest` | `runbooks.md` #6 |
| Anomalous MCP client | Tool-invocation volume or denied-action rate for a client deviates sharply from its baseline | `runbooks.md` #7 |
| Backup failure | Scheduled backup job did not report success within its expected window, or artifact size is anomalously small/zero | `runbooks.md` #8 |
| Telemetry stopped | No metrics/logs received from a service for > 10 min | `runbooks.md` #9 |
| Unauthorized-access spike | Auth-failure or permission-denial rate exceeds baseline threshold from one account/source/window | `runbooks.md` #10 |

Alert thresholds above are starting points — tune per the org's actual traffic once a
baseline is established; do not leave placeholder thresholds unreviewed past the first
month of production data.

## 3. Internal system-status page

An internal (not public) status page for staff with limited technical background to
glance at before escalating. Contents:

- **Overall status banner:** green/yellow/red, derived from whether any alert in §2 is
  currently firing.
- **Per-service status:** `web`, `api`, `worker`, `scheduler`, `mcp`, `postgres`, `redis`,
  `minio`, `proxy` — up/degraded/down, sourced from health/readiness checks
  (`deployment.md` §4).
- **Key freshness indicators:** last successful backup timestamp, last scheduled-job run
  per job, current queue depth, last MCP anomaly check.
- **Active incidents:** any currently-firing alert from §2, each linked directly to its
  runbook section in `runbooks.md` so a non-specialist on-call person has a next step
  without needing to search.
- **Recent incident history:** last 30 days of resolved incidents with time-to-resolve,
  for trend visibility (recurring issues should prompt a fix, not repeated firefighting).

The status page reads from the same telemetry in §1 — it is a view, not a separate data
source, so there is only one place metrics need to be correct.
