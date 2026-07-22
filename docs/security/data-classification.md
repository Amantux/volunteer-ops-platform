---
title: Data Classification & Handling
owner: Security / Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [../architecture/domain-model.md, ../architecture/permissions.md, threat-model.md]
---

# Data Classification

Governing rule (from non-goals, restated because it is the point):
**every sensitive field has a documented purpose and a retention policy, or it is
not collected.** Classification is assigned at the field/category level, travels
with the data (exports, backups, logs, agent context), and the higher tier wins
when categories mix.

## Tiers

| Tier | Definition | Baseline handling |
|---|---|---|
| **Public** | Published deliberately; no harm if copied. | TLS in transit; integrity controls (only approved publishers); no other restriction. |
| **Internal** | Org-operational data; not secret, not for the public. | TLS + at-rest encryption (platform default); org-scoped access; normal logging allowed. |
| **Confidential** | Personal or business data whose exposure causes real but bounded harm. | Tier below + role-restricted access, redacted from logs, included in export/delete workflow. |
| **Sensitive-PII** | Personal data whose exposure causes serious harm to an individual. | Tier below + narrow named-role access, read-access auditable, never in agent context without explicit grant, shortest workable retention. |
| **Restricted** | Data the platform must barely touch or must not hold at all. | Hold a pointer/status only, or hold nothing; provider retains the substance; any exception requires an ADR + security review. |

All tiers: encryption in transit (TLS everywhere) and at rest (disk/DB/S3);
`org_id` boundary absolute; parameterized queries; no tier ever appears in URLs
or query strings.

## Category matrix

Roles reference `permissions.md`. "Access" means the *ceiling* — scoped
assignments (program/team/location) narrow it further. Retention defaults are
org-configurable via `OrganizationSetting` only within the stated bounds.

| Data category | Classification | Purpose | Who may access | Retention default | Handling rules |
|---|---|---|---|---|---|
| Public content (`ContentPage`, `Update`, public course info, campaign progress) | **Public** | Front door of the operational system; recruitment, announcements. | Read: everyone. Write: authors + approvers per content workflow; publishing is a high-risk action. | Until archived/expired per content workflow; revisions kept. | Integrity over confidentiality: approval gate before publish, revision history, no PII in public content (checked at review). |
| Volunteer profile basics (name, status, interests, skills, availability summary) | **Internal** | Matching volunteers to shifts/training; operational coordination. | The volunteer (own); coordinators/trainers within scope; org admin. | Life of the volunteer relationship + 12 months inactive, then anonymize. | Fine in operational UIs and reports within scope; excluded from public surfaces; included in export/delete. |
| Contact info (email, phone, address, verified flags) | **Confidential** | Communications delivery, scheduling logistics, account identity. | The person (own); coordinators within scope (need-to-contact); comms via audience resolution (system-mediated, not browsing); org admin. | Same as profile; suppression entries kept after deletion (hashed) to honor opt-outs. | Redacted in logs (`a***@example.org`); bulk visibility only through `EmailAudienceDefinition` preview, never raw list export without audit; export/delete workflow applies. |
| Emergency contacts | **Sensitive-PII** | Reaching a designated contact if something happens to the volunteer during activity. That is the only purpose. | The volunteer (own); coordinator of an *active* shift/session the volunteer is on; org admin. Never comms, finance, trainers-at-large, or agents. | While an active volunteer + 90 days, then purge. | Third-party PII held on someone else's consent — minimum fields (name, phone, relationship); read access logged; never in exports/reports except the subject's own data export; never in agent context. |
| Accessibility / accommodation requests | **Sensitive-PII** | Providing the requested accommodation; nothing else. | The person (own); the coordinator/trainer delivering the specific session or shift; org admin. | Life of the relevant registration/relationship; purge on withdrawal. | Health-adjacent: store the *need* ("step-free access"), not diagnoses; free-text discouraged by form design; excluded from general reporting and search; read-logged; never agent-readable. |
| Staff notes (on `VolunteerProfile`, visibility-flagged) | **Sensitive-PII** | Legitimate coordination context (reliability, safeguarding-relevant observations). | Authoring role + roles the visibility flag grants (coordinator-scope or admin-only); **never** the subject's peers, never trainers by default, never agents. | 24 months, then review-or-purge; purged on volunteer deletion unless legal hold. | Highest insider-misuse surface (threat T12): write-audited with before/after digest, read-audited; content policy — observed facts, no speculation; subject-access handling defined with counsel per jurisdiction. |
| Consent records (`ConsentRecord`) | **Confidential** (integrity-critical) | Prove lawful basis for contact/processing; honor withdrawal. | System (enforcement); org admin (review); the person (own). | Duration of processing + statutory limitation period — outlives most other data by design. | Append-only (grant/withdraw events, never edited); withdrawal enforced at send time via suppression; included read-only in data-subject export, exempt from deletion while needed as proof. |
| Background-check **status** (a `VolunteerQualification`: pending/cleared/expired + dates) | **Confidential** | Gate eligibility for roles that require clearance. | Coordinators within scope (boolean/eligibility view); org admin (status + dates). | Status history for the relationship; purge with profile. | Status is the only thing the platform stores — a date-stamped outcome, no findings. |
| Background-check **reports** (the actual report/findings) | **Restricted — not stored** | None on-platform. The check provider retains the report; we store the status above and, at most, a provider reference id. | Nobody, because it does not exist here. Provider-side access is org-admin only, outside the platform. | N/A on platform; provider retention per their contract. | Hard rule from the higher-risk review posture: any proposal to ingest report contents requires an ADR + separate stricter review (see threat-model.md) and is expected to be rejected. |
| Donation / donor data (`Donation`, donor Person link, designation, receipt state) | **Confidential** | Payment reconciliation, receipts, donor stewardship, financial reporting. | Finance manager + org admin **only**. Aggregates (campaign totals) may be Internal/Public per campaign flag. | 7 years (financial record-keeping norm), then purge/anonymize per jurisdiction. | **Separated from volunteer operations by design:** coordinators/trainers/comms never see donation records (capability matrix); the donor↔volunteer person link exists in the model but donation facts are not exposed through volunteer-facing views, reports, or agent tools. Refunds: approval + step-up + audit. |
| Payment tokens / card data | **Restricted — not stored** | None. Stripe holds all PCI scope (test-mode today; the rule does not relax in live mode). | Nobody. Platform stores provider intent/event ids only. | N/A. | Non-goal enforced: no PAN, CVV, or raw tokens ever touch our DB, logs, or backups; webhook payloads persisted as `PaymentEvent` are id/status metadata, verified per threat T7. |
| Audit logs (`AuditEvent`) | **Confidential** (integrity-critical) | Accountability for privileged and high-risk actions; incident forensics. | Org admin (own org); security/platform operators under break-glass. | 24 months minimum online; archive per org policy; legal hold overrides. | Append-only, tamper-evident; contain actor/action/target + digests, **not** full sensitive payloads (redaction at write); exempt from data-subject deletion (legitimate interest — accountability), noted in the export response. |
| Agent logs (`AgentRun`, `AgentProposal`, `MCPToolInvocation`) | **Confidential** | Governance of agent behavior; prompt-injection forensics (threat T8/T9); approval trail. | Org admin; security operators. Not general staff. | 12 months, then purge (proposals/approvals that became actions persist via AuditEvent). | May embed untrusted user content and retrieved PII: stored with the same redaction pipeline as app logs; never re-fed to agents as trusted context; access read-logged. |
| Email content (templates, campaign bodies, per-recipient rendered snapshots, delivery events) | **Confidential** | Prove exactly what was sent to whom (compliance snapshot, domain rule 3); delivery troubleshooting. | Comms manager + org admin (campaigns); a recipient may obtain their own rendered copies via data-subject export; delivery events visible to comms within scope. | Rendered snapshots + delivery events 24 months; templates for their lifetime. | Snapshots inherit the classification of their most sensitive merge field — campaigns flagged sensitive get admin-only snapshot access; open/click events exist only where the org opted in (non-goal: no invasive tracking by default); suppression list survives deletion as hashed entries. |

## Data minimization in practice

- **Field admission test:** a new field on any Confidential+ entity ships only with
  (1) a one-line documented purpose, (2) a retention entry in this file or the org
  policy, (3) an access row (which roles). No entry → the migration is rejected in
  review.
- **Forms:** `FormDefinition` supports role-restriction and retention per form;
  form authors get a warning when adding free-text fields to forms in sensitive
  contexts (they collect PII by accident).
- **Aggregation preferred:** reporting uses counts/aggregates wherever the question
  allows; person-level report rows require the same authz as the underlying records.
- **Agents:** agent context is assembled from allowlisted, tier-checked fields only;
  Sensitive-PII and Restricted never enter agent context (threat-model.md T8/T9).

## Donor / volunteer separation (explicit)

The same `Person` may donate and volunteer. The **facts are separated by module
and by role**: donation records are reachable only through the donations module
(finance manager, org admin), volunteer operational data only through
people/scheduling/training (coordinators etc.). No view, report, export, or MCP
tool joins the two audiences, and comms audience definitions cannot filter
volunteers by donation behavior (or vice versa) without an org-admin-approved,
audited campaign flagged sensitive.

## Export & deletion (data subject) — workflow summary

**Export ("give me my data"):**
1. Request by the subject (self-service, verified session or verified email for
   guest Persons) or recorded manually by org admin.
2. Worker assembles the export across modules via the same `authorize` path
   (subject-scope), covering: Person, profile, qualifications, registrations,
   signups/hours, consent records, own form submissions, own donation records,
   rendered emails received. Excludes: other people's data (e.g. staff notes are
   handled per counsel/jurisdiction; emergency-contact entries where the subject
   is the *contact* are disclosed to them, not to the volunteer who listed them),
   and audit-log internals (existence acknowledged).
3. Delivered as a time-limited, authenticated download from S3; the export event
   itself is audited; artifact auto-deleted after 7 days.

**Deletion ("forget me"):**
1. Request verified as above; org admin confirms (step-up) because deletion is a
   high-risk action — never agent-executable.
2. Worker runs an idempotent erasure job: purge Sensitive-PII and Confidential
   personal fields; **anonymize** rather than delete where integrity requires the
   row (hours, attendance, donation lines → "deleted person #hash" to keep
   operational/financial history true).
3. **Retained despite deletion**, with documented lawful basis: consent/withdrawal
   proof, hashed suppression entries (so we keep honoring the opt-out), financial
   records within the 7-year window, audit events.
4. Backups: erasure is not retro-applied to encrypted backups; instead backup
   retention is bounded (see C-BACKUP) so deleted data ages out on schedule, and
   any restore replays the erasure ledger before the restored dataset serves
   traffic.
5. Completion is recorded as an `AuditEvent` and confirmed to the requester.
