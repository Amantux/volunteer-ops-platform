---
title: Test Strategy
owner: Test Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [../architecture/system-design.md, ../architecture/domain-model.md, ../architecture/permissions.md]
---

# Test Strategy

Testing follows the architecture: deterministic business logic lives in ordinary,
testable code (a non-goal is AI for deterministic logic), authorization is enforced
server-side everywhere, and side effects flow through the transactional outbox. The
pyramid reflects that: most confidence comes from fast unit tests on the rules, a
substantial integration layer proves modules + outbox + workers cooperate, and a thin
E2E layer proves the user-visible flows in a real browser. Security and reliability
suites cut across all layers.

## The pyramid

```
        E2E (browser, few, slow)        — user-visible flows, accessibility
     Integration (API + DB + worker)    — module seams, outbox, webhooks, authz
  Unit (pure rules, many, milliseconds) — eligibility, waitlists, segmentation, …
  ──────────────────────────────────────
  Cross-cutting: security suite · reliability/chaos suite · migration tests
```

Target shape: unit tests dominate in count and run on every save; integration runs on
every push; E2E + security + reliability run on every PR (required subset) and nightly
(full matrix).

## 1. Unit tests

Pure-logic tests with no network, no real DB (in-memory/session-scoped fixtures only).
Every rule that decides something a human will experience is unit tested against a
table of cases, including boundary and timezone cases.

| Area | What is covered |
|---|---|
| Eligibility rules | ShiftRole eligibility (required QualificationTypes, age, program rules) — eligible/ineligible/expired-qualification/missing-prerequisite cases. |
| Scheduling conflict logic | Overlapping signups, buffer/travel-time conflicts, recurrence expansion, cross-timezone overlaps. |
| Waitlist promotion | Position ordering, promotion policy snapshots, seat-available selection, session vs shift polymorphism. |
| Audience segmentation | EmailAudienceDefinition filter evaluation, count correctness, suppression/subscription-preference exclusion, org-scope containment. |
| Template-variable validation | Declared vs used variables, missing/extra variables rejected at draft time, escaping of user-supplied values. |
| Permissions | `authorize(user, action, resource)` truth-table per role × capability matrix (permissions.md), scope binding (program A coordinator ≠ program B), deny logging hook. |
| Donation webhook processing | PaymentEvent parsing, signature-verified flag, idempotency-key dedup, state transitions (succeeded/failed/refunded), never storing card data. |
| Qualification expiration | expires_at computation from validity period, expiring-soon window selection, expired blocks eligibility. |
| Recurring-maintenance generation | MaintenanceSchedule recurrence → next_due, WorkRequest generation without duplicates, checklist propagation. |
| Agent risk classification | Proposal classification into auto-allowed vs approval-required; the high-risk action list (permissions.md) always classifies as approval-required regardless of confidence. |

Conventions: property-based tests (Hypothesis) for waitlist ordering, recurrence, and
segmentation math; frozen clocks for anything time-based; timezone cases always include
a DST transition.

## 2. Integration tests

API + real Postgres (per-test transaction rollback or per-worker schema) + real Redis
where a worker is under test. Providers (email, payments, storage) are faked at the
typed adapter interface — never by patching internals. Every test asserts org scoping
and expected AuditEvents where applicable.

| Flow | Assertion focus |
|---|---|
| Registration → confirmation email | TrainingRegistration + OutboxEvent commit in one transaction; worker relay renders template, creates EmailRecipient with content snapshot; no send when the transaction rolls back. |
| Guest → volunteer conversion | Person-without-User gains User + VolunteerProfile; prior TrainingRegistrations and history remain attached; no duplicate Person. |
| Shift signup + cancel | Eligibility enforced at API; capacity decremented/restored; cancel emits domain event; hours entry lifecycle. |
| Waitlist promotion | Cancel frees seat → waitlist worker promotes correct entry → notification event; concurrent-cancel race yields exactly one promotion. |
| Email approval + scheduling | draft→review→approved→scheduled state machine; approval threshold policy (comms mgr vs org-admin); tz-aware scheduling; audience resolved to EmailRecipients at send time. |
| Delivery webhook processing | Provider delivery/bounce/complaint events update EmailRecipient/EmailDeliveryEvent; bounce/complaint drive suppression; replayed event is a no-op. |
| Donation + receipt | Provider (test mode) intent → PaymentEvent → Donation reconciled → receipt email via outbox; anonymous donor path. |
| Work-request create + assign | Public form → WorkRequest (needs_triage) → triage → WorkAssignment; status machine transitions; attachments stored via storage adapter. |
| MCP authorization | Each MCP tool calls `authorize` internally; a tool invoked with an identity lacking permission returns a deny AND logs it; org boundary enforced inside the tool, not just at the gateway. |
| Audit-event generation | Every privileged action in the high-risk list emits an AuditEvent with actor/action/target/before-after digest; denies on privileged actions are logged. |

## 3. E2E tests (browser)

Playwright against the composed stack (`docker-compose`), seeded fixture org. Few,
stable, user-journey shaped. Each journey includes an axe scan on its key screens
(see Accessibility below).

- Public training registration — guest finds a public session, registers, sees confirmation; email visible in the mailcatcher.
- Volunteer onboarding — interest → verification → onboarding stages → active profile.
- Shift signup — volunteer browses eligible opportunities, signs up, sees it on their schedule; ineligible shift is not offered.
- Coordinator shift management — create shift + roles, review signups/waitlist, record attendance, approve hours (scoped to own program).
- Email campaign create + approve — draft from template, preview audience with counts, submit for approval, approver approves + schedules.
- Maintenance reporting — report issue via public form (incl. QR/short-code entry), maintenance coordinator triages and assigns.
- Donation flow — one-time and recurring donation in provider test mode, receipt shown/emailed; no card data touches our forms beyond the provider element.
- Mobile navigation — key journeys above at a 375px viewport; touch targets and nav usable.
- Keyboard-only usage — training registration and shift signup completed with keyboard alone; focus visible throughout; modals trap and restore focus.
- Permission boundaries — volunteer cannot reach coordinator screens; coordinator for Program A gets 403/absence for Program B resources (asserted at the API response, not just hidden UI — frontend role-awareness is UX only).

## 4. Security tests

Run as pytest suites plus scheduled DAST/dep scans. Every finding class here has a
regression test once fixed.

- **Authz bypass** — every protected route/worker/MCP tool hit with each role from the capability matrix; expected allow/deny generated from the matrix so drift fails the build.
- **Cross-org access** — fixture with two orgs; every list/detail/mutation endpoint probed with the other org's IDs; any non-404/403 fails. Repository-scope lint backs this.
- **CSRF** — cookie-based session endpoints reject missing/invalid tokens.
- **XSS** — template variables, form submissions, content pages, and work-request text rendered with hostile payloads; CSP + output encoding asserted.
- **Malicious uploads** — extension/MIME/magic-byte mismatch, oversize, polyglot files, EICAR through the malware-scan interface; rejected before storage.
- **Webhook replay** — replayed and tampered payment/delivery webhooks: invalid signature rejected, valid duplicate idempotent.
- **Rate-limit enforcement** — public forms (registration, donation, work-request, interest) and auth endpoints throttle; bot-control hooks fire.
- **MCP tool abuse** — tool called outside allowlist, with escalated scope, or against another org's data → denied + audited; no raw DB/shell/secret tools exist (non-goal).
- **Prompt-injection attempts** — agent runs over uploaded/user content containing instructions; assert content is treated as data: no tool call outside allowlist, no high-risk proposal auto-approved.
- **Audience manipulation** — attempts to widen an EmailAudienceDefinition post-approval, or inject filters crossing org/suppression boundaries, invalidate the approval.
- **Unauthorized email sends** — send attempted by a role without approve-authority, or above the comms-manager policy threshold without org-admin approval → blocked + audited.

## 5. Reliability tests

Fault-injection suites against the composed stack; assertions are about *convergence*
(system reaches correct state) and *non-duplication*.

- **Email provider unavailable** — provider adapter errors: outbox events retry with backoff, nothing lost, no duplicate sends after recovery.
- **Payment retry** — transient provider failure on recurring charge → retry policy honored, dunning state correct, single Donation record.
- **Worker crash mid-processing** — kill worker between side effect and ack; on restart the idempotency key prevents a second side effect.
- **Duplicate webhook** — same provider event delivered N times → one PaymentEvent/DeliveryEvent applied.
- **Duplicate job execution** — the same outbox event relayed twice (at-least-once delivery) → exactly-once observable effect.
- **Redis restart** — queue/cache/locks restart under load: no lost outbox events (Postgres is source of truth), locks re-acquire, no double promotion.
- **Migration rollback/recovery** — every Alembic migration upgrades AND downgrades against a data-bearing DB in CI; the module bring-up order (domain-model.md) is replayable from empty.
- **Scheduler downtime** — beat down across a reminder window: on recovery, due jobs run once; stale reminders (event already passed) are skipped, not sent late.
- **Stale agent run** — an AgentRun exceeding its freshness budget is marked stale; its proposals cannot be approved/applied.
- **Telemetry failure** — metrics/trace sink unavailable must never fail a user request or worker job.

## 6. CI gate policy

Merge to `main` is **blocked** unless all required checks pass. No "done" without
validation evidence (non-goals doc) — a red required check is a hard stop, never
overridden by reviewer approval.

Required on every PR:
1. **Lint** — ruff (api/worker/mcp), eslint (web), import-guard rule (module boundary: no cross-module ORM imports).
2. **Typecheck** — mypy (strict on new modules), tsc.
3. **Unit tests** — full suite, no skips without a linked issue.
4. **Integration tests** — full suite against real Postgres + Redis.
5. **Migrations** — alembic upgrade head from empty AND from the previous release snapshot; downgrade one step; model/migration drift check (autogenerate diff must be empty).
6. **Security checks** — dependency audit (pip-audit/npm audit at high+), secret scan, the authz-matrix and cross-org suites.
7. **Build** — all images build; web production build succeeds.
8. **E2E required subset** — first-slice journeys + permission-boundary journey.

Nightly (failures page the on-call for main): full E2E matrix (mobile + keyboard-only),
full reliability suite, full axe sweep, DAST scan.

Flake policy: a flaky required test is quarantined by moving it to non-blocking **with
an owning issue and a 2-week clock**; it is fixed or deleted, never left flaky-required.

## 7. Test data & fixtures

- **Factory-based, not dump-based.** `factory_boy` factories per entity mirroring the domain model; every factory requires an explicit `org` — there is no default org, so a test that forgets scoping fails loudly.
- **Canonical fixture orgs:** `org_alpha` (fully-featured), `org_beta` (minimal, used as the "other org" in every cross-org probe). Seed script builds both for E2E/compose runs and is the same code path CI and local dev use.
- **Synthetic PII only.** Faker-generated people; no production data in any environment below production, ever (data non-goals).
- **Deterministic time & randomness.** Frozen clock fixture; seeded RNG; fixture orgs pinned to distinct timezones (one US, one non-US, one crossing DST in test windows).
- **Provider fakes at the adapter seam** with recorded golden payloads (Stripe test-mode events, email-provider delivery events) checked into `tests/fixtures/providers/`.
- **Snapshot fixtures for compliance paths:** form_version snapshots and rendered-email snapshots are asserted byte-for-byte where the domain promises immutability.

## 8. Accessibility (axe) integration

WCAG 2.1 AA is the target (system-design.md). Three enforcement points:

1. **Component level** — `jest-axe`/`vitest-axe` on every design-system primitive; a new primitive without an axe test fails review.
2. **E2E level** — every E2E journey runs `@axe-core/playwright` on each distinct screen it visits; serious/critical violations fail the (required) run, moderate ones fail nightly.
3. **Manual journeys** — the keyboard-only and mobile E2E journeys above are the automated proxy; a human screen-reader pass is required before each release of a new public-facing flow.

Public pages (registration, donation, content) are held to the strictest bar — they are
the front door and serve users we cannot pre-screen.

## 9. First-slice test map (training registration slice)

The first slice ships only with this explicit set green:

- **Unit:** template-variable validation; permissions for the first-slice surface (`training.view_public`, `training.register_guest`, trainer scoped perms, `training.manage_course`); qualification expiration (granted via training completion); waitlist promotion (session waitlist); agent risk classification for the reminder-draft allowlist.
- **Integration:** registration → confirmation email via outbox; guest → volunteer conversion; delivery webhook processing; waitlist promotion on cancellation; audit-event generation for trainer/admin actions; MCP authorization for `training.read_metrics` + `comms.draft`.
- **E2E:** public training registration (desktop + mobile viewport + keyboard-only variant); trainer records attendance/completion; permission boundary (trainer limited to own sessions).
- **Security:** cross-org probe of all training + registration endpoints; rate-limit on the public registration form; webhook replay for delivery events; unauthorized email send (agent/trainer cannot send beyond reminder allowlist).
- **Reliability:** email provider unavailable during confirmation; duplicate delivery webhook; worker crash mid-confirmation-send; migration up/down for the first-slice migration set (org+identity, people, training, communications, audit).

This map is the required-check set for PRs touching the slice until the full suites exist.
