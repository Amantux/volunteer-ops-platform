---
title: ADR-0003 — Async workers: Celery + Redis, with a transactional outbox
owner: Architecture
status: accepted
last_reviewed: 2026-07-22
---

# ADR-0003: Celery + Redis for async work; outbox for consistency

**Status:** Accepted · **Date:** 2026-07-22

## Context
Email must never be a synchronous request (anti-goal). We need durable reminders,
digests, imports, and agent jobs, plus scheduling (beat), cache, and locks.

## Decision
Use **Celery + Redis** (Celery beat for schedules; Redis also for cache + locks). Use a
**transactional outbox**: a state change and its `outbox_event` commit in one DB
transaction; the worker relays events to side effects. All workers and inbound webhooks
are **idempotent** (keyed, replay-safe).

## Alternatives considered
- **Arq** (15/20): lighter/async-native but less mature retries/beat/tooling.
- **DB-only cron** (15/20): simplest but weak durability/retries.

## Consequences
+ Durable retries, scheduled jobs, no lost-email-after-commit class of bug.
+ The outbox makes the queue technology replaceable later.
− Operational surface (Redis, worker, beat) — covered by runbooks + observability.
