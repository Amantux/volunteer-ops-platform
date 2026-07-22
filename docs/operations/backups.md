---
title: Backups & Restore
owner: Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [deployment.md, ../architecture/system-design.md]
---

# Backups & Restore

## 1. What to back up

| Item | Why | Where it lives |
|---|---|---|
| **PostgreSQL** (full DB, including `outbox_event`, `audit_event`) | Source of truth for all domain state (`system-design.md` §3) | `postgres` volume |
| **MinIO / object storage** (uploads, generated documents, attachments) | Referenced by `Document`, `WorkRequest` attachments, `FormSubmission` attachments, email assets | `minio` volume/bucket |
| **Secrets inventory** (not the secret values themselves — see below) | So a rebuild knows *which* secrets must be re-provisioned | Secrets manager, documented list |

**Secrets are not stored in the backup artifact.** Back up an *inventory* (names/purposes
of required secrets, per `deployment.md` §2) and rely on the secrets manager's own
backup/replication for the values. Never write secret values into a backup archive that
sits in general storage.

`redis` is not backed up: it holds only the Celery broker/queue, cache, and locks —
transient by design. Losing it loses in-flight (not-yet-committed) job state and cache,
not durable domain data; the outbox pattern means durable events survive in Postgres and
will be re-relayed by a worker restart. A queue-depth/consumer alert (see
`observability.md`) covers detection if this happens.

## 2. Schedule

| Item | Frequency | Retention |
|---|---|---|
| Postgres full dump | Daily (off-peak) | 30 daily + 12 monthly, minimum 1 year for donation/financial records unless local nonprofit record-keeping law requires longer |
| Postgres WAL / continuous archiving (if using `pg_basebackup`+WAL shipping instead of plain dumps) | Continuous | Matches dump retention; enables point-in-time recovery within the retention window |
| MinIO bucket sync/snapshot | Daily | Same as Postgres (documents referenced by DB rows must not outlive or be orphaned from the DB backup they correspond to) |
| Secrets inventory review | Quarterly | N/A — living doc, not a dated artifact |

For a small nonprofit's data volume, daily is sufficient; do not build hourly backups
speculatively (matches the non-goals principle: don't add operational complexity the
scale doesn't justify).

## 3. Encryption at rest

- Postgres dumps and MinIO snapshots are encrypted at rest: encrypt the backup archive
  itself (e.g. `gpg --encrypt` or the storage provider's server-side encryption with a
  key the org controls) before/while it lands in offsite storage.
- Backup storage location must be **separate from** the primary VM/host (offsite or a
  different cloud region/account) so a host compromise or disk failure doesn't take out
  both primary and backup.
- Access to the backup store is itself a privileged credential — treat it like a
  production secret (see `deployment.md` §2 rotation policy).

## 4. Backup commands (verified-style — for this compose stack)

```bash
# --- Postgres: full logical dump (run from the host, against the compose service) ---
docker compose exec -T postgres pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --file=/tmp/backup.dump

docker compose cp postgres:/tmp/backup.dump ./backups/pg_$(date +%Y%m%d).dump

# Encrypt before shipping offsite
gpg --symmetric --cipher-algo AES256 ./backups/pg_$(date +%Y%m%d).dump

# --- MinIO: mirror buckets to offsite storage (using mc, the MinIO client) ---
mc mirror --overwrite local/uploads offsite/uploads-backup-$(date +%Y%m%d)
mc mirror --overwrite local/documents offsite/documents-backup-$(date +%Y%m%d)
```

Automate the above via a scheduled `worker`/cron job or an external backup runner; do
not rely on a human remembering to run it manually day to day (that's what the
"backup completion" observability signal in `observability.md` is for).

## 5. Restore procedure (with test steps)

**Never restore into the live production database directly as a first step.** Restore
into an isolated instance, verify, then cut over.

```bash
# 1. Stand up an isolated Postgres instance (do NOT point at prod data dir)
docker compose -f docker-compose.yml -f docker-compose.restore-test.yml up -d postgres_restore_test

# 2. Restore the dump into it
docker compose exec -T postgres_restore_test pg_restore \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /tmp/pg_YYYYMMDD.dump

# 3. Sanity checks against the restored instance
docker compose exec postgres_restore_test psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*) FROM organization;"
docker compose exec postgres_restore_test psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT max(created_at) FROM audit_event;"   -- confirms recency of restored data
docker compose exec postgres_restore_test psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*) FROM outbox_event WHERE processed_at IS NULL;"  -- expected backlog is small

# 4. Restore MinIO objects into a scratch bucket and spot-check a known Document key
mc mirror offsite/documents-backup-YYYYMMDD local/documents_restore_test
mc stat local/documents_restore_test/<known-object-key>

# 5. Only after (3) and (4) pass: point a maintenance-mode api/worker at the restored
#    DB/bucket (never the live one) for a full application-level smoke check before any
#    real cutover.
```

**Cutover to production** (real incident, not a drill): stop `api`/`worker`/`scheduler`,
restore into the actual `postgres`/`minio` volumes (or promote the verified restored
instance), run `alembic current` to confirm migration state matches the expected code
version, then start services and check `/readyz`.

## 6. RPO / RTO targets (small nonprofit)

| Metric | Target | Rationale |
|---|---|---|
| **RPO** (Recovery Point Objective) | ≤ 24 hours (≤ 15 min if WAL/continuous archiving is enabled) | Daily dump cadence; acceptable loss window for volunteer-ops data, not acceptable for a bank but fine here |
| **RTO** (Recovery Time Objective) | ≤ 4 hours for full service restore on a single-VM deployment | Time to provision, restore, verify, and cut over on modest infra with limited technical staff |

These are targets appropriate to a small nonprofit's risk tolerance and non-goal of
building enterprise HA (`non-goals.md`) — not a contractual SLA unless the org has
committed to one separately.

## 7. Periodic restore-test cadence

- **Quarterly:** full restore drill following §5 steps 1-4 (isolated instance, not
  production), performed by whoever holds the ops role that quarter — this doc plus the
  commands above should be sufficient for a non-specialist to execute.
- **After any schema migration that touches backup-critical tables** (org, person,
  donation, payment_event, outbox_event): an ad hoc restore-test of the latest dump to
  confirm `pg_restore` still succeeds against the new schema.
- Record each drill's outcome (pass/fail, time taken) in the org's ops log — this is
  what makes the RTO target credible rather than aspirational.
