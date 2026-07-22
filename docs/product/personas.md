---
title: Personas & User Groups
owner: Product
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [vision.md, ../architecture/permissions.md, ../architecture/domain-model.md]
---

# Personas

Capabilities below are the product-level view of the capability matrix in
[permissions.md](../architecture/permissions.md) — that matrix is authoritative.
"Must NOT see" items are enforced server-side (API, workers, MCP tools), never by
hiding UI alone. All roles are org-scoped; nothing crosses `org_id`.

## 1. Public visitor
- **Who:** Anyone on the public site. No account, no Person record yet.
- **Frequency:** One-off / occasional.
- **Top jobs:** Understand what the org does; find a training or event; report a
  problem they noticed; donate.
- **Must be able to:** Browse public content, register for public training as a guest,
  donate, submit the public maintenance report form (rate-limited, bot-controlled).
- **Must NOT see:** Anything behind login; volunteer PII; internal rosters, reports,
  or comms; non-public courses/events.

## 2. Prospective volunteer
- **Who:** A Person who has expressed interest or completed a public training; may not
  have a User account yet (progressive enrollment stages 2–4).
- **Frequency:** Weekly during onboarding.
- **Top jobs:** Know where they stand in onboarding; complete the next requirement;
  become eligible for real work.
- **Must be able to:** Submit interest, verify contact, create an account, see and
  progress their own OnboardingRecord, manage own profile (limited), see eligible
  public opportunities.
- **Must NOT see:** Shift signup for volunteer-only shifts; other people's records;
  staff notes about themselves (staff-notes visibility flags); internal reports.

## 3. Active volunteer
- **Who:** Person + User + VolunteerProfile in an active status.
- **Frequency:** Weekly; mobile-heavy.
- **Top jobs:** "What's next for me?" — find eligible shifts, sign up/cancel, check in,
  log hours, keep qualifications current, stay informed.
- **Must be able to:** Manage own profile/availability, view eligible opportunities
  (eligibility computed from ShiftRole requirements vs. own qualifications), sign up /
  cancel / join waitlists, log and view own hours, register for training, manage own
  subscription preferences, report maintenance issues.
- **Must NOT see:** Other volunteers' profiles/PII/hours; unpublished content; donor
  records; audit logs; staff notes on their own profile.

## 4. Team lead / Coordinator
- **Who:** Volunteer or staff with a Coordinator role scoped to a program/team.
- **Frequency:** Daily.
- **Top jobs:** Keep shifts staffed; run rosters, waitlists, attendance; approve hours;
  nudge the right volunteers.
- **Must be able to:** Create/manage shifts, assign volunteers, review waitlists and
  attendance, approve hours, draft comms to their program audience, view program-scoped
  reports — **all bounded to their assigned program/team scope**.
- **Must NOT see:** Other programs' operations; donation records; org configuration;
  audit log; volunteer PII beyond operational need. Cannot approve & send bulk comms.

## 5. Trainer
- **Who:** Delivers courses; role scoped to own courses/sessions.
- **Frequency:** Around session dates (bursty).
- **Top jobs:** Run sessions end-to-end: roster, check-in, completion, resulting
  qualifications.
- **Must be able to:** Manage own TrainingSessions, view rosters, record attendance
  and completion (which grants VolunteerQualifications per QualificationType rules),
  review session waitlists, draft comms to their course audience, view training reports
  for own sessions.
- **Must NOT see:** Registrants' data beyond the roster need; shifts/maintenance/
  donations; other trainers' sessions; org configuration.

## 6. Maintenance / ops coordinator
- **Who:** Owns the asset registry and work-request pipeline.
- **Frequency:** Daily.
- **Top jobs:** Triage incoming reports; schedule and assign work; verify and close
  with evidence; keep preventive schedules on track.
- **Must be able to:** Triage/assign WorkRequests, manage Assets/MaintenanceSchedules/
  Inspections, close work with evidence, approve maintenance hours, draft maintenance
  notices, view maintenance reports — within maintenance scope.
- **Must NOT see:** Volunteer PII beyond assignment need; donations; training records;
  bulk-comms send authority; org configuration.

## 7. Communications manager
- **Who:** Owns templates, campaigns, and the update stream.
- **Frequency:** Daily/weekly.
- **Top jobs:** Draft campaigns; define and preview an explicit audience; get approval
  when policy requires; schedule; watch deliverability.
- **Must be able to:** Manage EmailTemplates, draft/review campaigns, build and preview
  EmailAudienceDefinitions (counts before send), approve & send **within configured
  policy thresholds** (above threshold → org-admin approval), publish updates, view
  comms/delivery reports, manage suppression handling.
- **Must NOT see:** Donor giving history or amounts (audience membership only, per
  least-privilege); volunteer operational records beyond audience fields; payments;
  org configuration.

## 8. Finance / donation manager
- **Who:** Handles donations, receipts, reconciliation exports.
- **Frequency:** Weekly + campaign peaks.
- **Top jobs:** Monitor campaigns; reconcile PaymentEvents; handle receipt issues;
  process refunds (with approval).
- **Must be able to:** View donation records and reports, manage DonationCampaigns,
  trigger receipt resend, initiate refunds (◐ — requires approval per matrix), export
  for accounting.
- **Must NOT see:** Volunteer operational records (profiles, hours, onboarding);
  comms audiences; maintenance; card data (never stored — provider holds PCI scope).

## 9. Org administrator
- **Who:** Accountable owner of the org's platform instance. MFA required.
- **Frequency:** Weekly config work; on-call for approvals.
- **Top jobs:** Configure org (hierarchy, terminology, pipelines, flags, policies);
  manage roles and integrations; approve high-risk actions; review audit log.
- **Must be able to:** Everything in the matrix's Org admin column, including person
  merge (with approval step), permission changes, integration/secret management, and
  serving as escalation approver for above-threshold comms and refunds.
- **Must NOT see:** Other organizations' data (org boundary is absolute); raw secrets
  (stored by reference); payment-card data.

## 10. Platform administrator *(conditional — multi-org hosting only)*
- **Who:** Operator of a multi-org deployment. Not part of the baseline matrix.
- **Frequency:** Rare, incident-driven.
- **Must be able to:** Provision orgs, manage platform health.
- **Must NOT see:** Org data in normal operation. Any access is **break-glass**:
  explicitly invoked, time-boxed, and fully logged (AuditEvent) — per the note in
  permissions.md. If this role is not enabled, it does not exist.
