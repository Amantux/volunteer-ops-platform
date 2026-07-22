---
title: Metric Dictionary
owner: Analytics
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [../architecture/domain-model.md, ../architecture/permissions.md, ../product/non-goals.md]
---

# Metric Dictionary

Single source of truth for reporting definitions. A dashboard, export, or agent answer
that disagrees with this file is wrong by definition. Metrics are computed from the
relational domain model (never from logs or provider dashboards) so every aggregate is
traceable to rows.

## Conventions (apply to every metric unless a row says otherwise)

- **Org scoping.** Every metric is computed within one `org_id`. There are no cross-org
  metrics (data non-goal).
- **Timezone.** All date bucketing uses the **organization timezone**
  (`Organization.timezone`), not UTC and not the viewer's browser. Session/shift-based
  metrics use the session's/shift's own stored timezone for "did it happen on day X",
  then roll up in org timezone. DST boundaries follow the org calendar day.
- **Date field.** Stated per metric; "event time" means when the thing happened,
  "record time" means `created_at`. Never mix within one metric.
- **Standard filters** (`STD`): date range, program, chapter/team, location. Extra
  filters are listed per metric; anything not listed is not offered.
- **Refresh:** `RT` = on transaction (live query), `15m` = incremental every 15 minutes,
  `daily` = materialized nightly in org timezone. Refresh interval is about staleness
  tolerance, not importance.
- **Privacy classes:**
  - `P1 aggregate` — counts/rates safe for any authorized report viewer; small-cell
    suppression applies (<5 people → suppressed in shared views).
  - `P2 operational-PII` — drill-down reaches named people; restricted to roles with the
    matching operational permission (capability matrix).
  - `P3 sensitive` — donor identity, blockers/health-adjacent notes, complaint data;
    restricted to the owning role (finance mgr, org admin) and audited on access.
- **Data owner** = the role accountable for the definition and its data quality, per the
  capability matrix ("View operational reports" scopes).

**Authorization rule (binding):** dashboards must let an authorized viewer link any
aggregate back to the underlying records **through the normal API with normal row/role
authorization** — and must never bypass it. A viewer who cannot list the rows does not
get a drill-down, only the (suppression-respecting) aggregate. Reporting is a read
model, not a side door.

## 1. Acquisition & onboarding — owner: Org admin · default refresh 15m

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| New interests | People who raised their hand this period | count(Person with interest submission) | Incl: interest form submissions. Excl: staff-created records, spam-flagged | submission `created_at` | STD + source channel | P1 (drill-down P2) |
| Verified-interest rate | Share of interests that verified contact | verified interests ÷ new interests | Excl: spam-flagged from both terms | verification timestamp (num), submission (den) | STD + channel | P1 |
| Orientation registration rate | Verified interests who register for orientation | orientation TrainingRegistrations ÷ verified interests (cohort) | Incl: sessions of orientation-tagged courses. Excl: cancelled-before-start regs | registration `created_at` | STD + course | P1 |
| Orientation attendance rate | Registrants who actually attended | AttendanceRecords ÷ registrations for sessions ended in period | Excl: sessions cancelled by org; waitlisted-never-promoted | session end time | STD + course, instructor | P1 |
| Training conversion | Orientation attendees who complete required training | completions ÷ orientation attendees (cohort-based) | Incl: completion status on required courses. Excl: optional courses | completion timestamp | STD + course, cohort month | P1 |
| Median time-to-active | How long onboarding takes | median(profile status→active timestamp − interest `created_at`) | Incl: profiles reaching active in period. Excl: reactivated returning volunteers | activation timestamp | STD + cohort month, pipeline | P1 |
| Onboarding-stage drop-off | Where people stall or leave | per OnboardingStage: entered vs progressed within stage SLA | Incl: all OnboardingRecords touching stage in period | stage entered_at | STD + pipeline, stage | P1 (drill-down P2) |
| Common blockers | Most frequent recorded blockers | count by blocker category on OnboardingRecords | Incl: structured blocker categories only. Excl: free-text notes (never aggregated) | blocker recorded_at | STD + pipeline, stage | **P3** (categories P1; any drill-down P3) |

## 2. Participation — owner: Org admin (program-scoped views: Coordinator) · refresh daily

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Active volunteers | Volunteers with any participation in trailing window | distinct profiles with shift attendance, approved hours, or maintenance work in trailing 90d (org-configurable) | Excl: registrations without attendance; paused/exited status | activity event time | STD + status, cohort | P1 (drill-down P2) |
| New / returning / paused / inactive | Lifecycle mix | classify each profile by first-activity date, gap length, and status per org policy | Incl: all non-deleted profiles | activity event time + status changed_at | STD | P1 |
| Volunteer hours | Total contributed hours | sum(VolunteerHourEntry.hours, approval=approved) | Excl: pending/rejected entries; auto-estimated unconfirmed hours | entry activity date (not approval date) | STD + source (shift/maintenance/manual) | P1 (per-person P2) |
| Hours by program | Where effort goes | approved hours grouped by program | as above | activity date | STD | P1 |
| Shifts per volunteer | Engagement depth | attended shift signups ÷ active volunteers | Excl: no-shows, cancellations | shift start time | STD | P1 |
| Participation frequency | How often typical volunteers show up | distribution (p25/median/p75) of attended shifts per active volunteer per month | as above | shift start time | STD | P1 |
| Retention by cohort | Do volunteers stay | % of month-N starters still active at month N+3/6/12 | Cohort = first-activity month. Excl: one-event program participants if org flags them | first activity + activity event time | STD + cohort month | P1 |
| Participation concentration | Reliance on a few people | share of hours contributed by top 10% of contributors (period) | approved hours only | activity date | STD | P1 |
| Approaching workload limits | Burnout early-warning | count of profiles ≥80% of configured workload counter limits | Incl: orgs with limits configured; else metric hidden | rolling window end | STD | **P2** (this list is inherently person-level) |

## 3. Scheduling — owner: Coordinator (program scope) / Org admin (org) · refresh 15m

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Fill rate | How full shifts are | confirmed signups ÷ Σ ShiftRole capacity, for shifts starting in period | Excl: cancelled shifts; admin/maintenance-window events unless filtered in | shift start time | STD + event type, role | P1 |
| Time-to-fill | How fast shifts fill | median(last-needed-seat confirmed_at − shift published_at), filled shifts | Excl: never-filled (reported separately), same-day emergency shifts flagged as such | publish + signup timestamps | STD + role | P1 |
| Understaffed shifts | Shifts below min staffing | count(shifts starting in period with confirmed < min_staffing) | Incl: at shift start (final) and current snapshot (upcoming) | shift start time | STD + severity (below min vs below max) | P1 |
| Cancellation rate | Volunteer-initiated cancellations | cancelled signups ÷ (confirmed + cancelled) for shifts in period | Excl: org-cancelled shifts (all their signups excluded); split late (<24h) vs early | cancellation `created_at`, bucketed by shift start | STD + notice window | P1 (per-person P2) |
| No-show rate | Confirmed but absent | no_show signups ÷ confirmed signups on completed shifts | Excl: shifts without attendance taken (reported as "unrecorded") | shift start time | STD + role | P1 (per-person P2) |
| Waitlist conversion | Waitlisted people who end up serving | promoted-and-attended ÷ waitlist entries created | Excl: entries withdrawn before any seat opened | waitlist entry `created_at` | STD | P1 |
| Qualification gaps | Demand unmet for lack of quals | unfilled seats on roles whose eligible pool < 2× capacity, by QualificationType | Incl: forward-looking (next 60d) and historical | shift start time | STD + qualification type | P1 |
| Scheduling conflicts | Prevented double-bookings | count of signup attempts blocked by conflict logic | Incl: blocked attempts (they never become signups) | attempt time | STD | P1 |
| Reminder effectiveness | Do reminders reduce no-shows | no-show rate for reminded vs not-reminded signups (reminder delivered = EmailDeliveryEvent) | Excl: signups created after reminder window | shift start time | STD + reminder offset | P1 |

## 4. Training — owner: Trainer (own courses) / Org admin · refresh 15m

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Registrations | Demand for sessions | count(TrainingRegistration) | Excl: cancelled-within-grace duplicates (same person+session) | registration `created_at` | STD + course, session, public/internal, source | P1 |
| Attendance rate | Registrants who showed | AttendanceRecords ÷ non-cancelled registrations, sessions ended in period | Excl: org-cancelled sessions | session end time | STD + course, instructor | P1 |
| Completion rate | Attendees who completed | completion=true ÷ attendance records | Incl: completion recorded within 30d of session | session end time | STD + course | P1 |
| No-show rate | Registered, confirmed, absent | status=no_show ÷ confirmed registrations | Excl: waitlisted-never-promoted | session end time | STD + course | P1 (per-person P2) |
| Waitlist size | Unmet demand right now | current count(WaitlistEntry, target=session, active) | Snapshot metric; no date range | snapshot time | course, session | P1 |
| Capacity utilization | Are sessions sized right | confirmed registrations ÷ session capacity, sessions in period | Excl: cancelled sessions | session start time | STD + course, location | P1 |
| Cert/qualification expirations | Quals lapsing soon | count(VolunteerQualification with expires_at in next 30/60/90d, not renewed) | Excl: already-expired (separate count), manually revoked | expires_at | STD + qualification type, window | P1 (list view P2) |
| Training→volunteer conversion | Public trainees who become volunteers | guests with completed training who gain a VolunteerProfile within 90d ÷ guest completions | Incl: guest-source registrations only | completion timestamp (cohort) | STD + course | P1 |
| Instructor utilization | Instructor load | sessions taught + taught-hours per instructor per period vs configured target | Excl: co-instructor double-counting (split credit) | session start time | STD + instructor | P2 (named-staff metric) |

## 5. Communications — owner: Comms manager · refresh 15m

Open/click metrics exist **only** for orgs that enabled opt-in tracking (data non-goal:
no invasive tracking by default) and are excluded from all default dashboards.

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Sends | Emails handed to provider | count(EmailRecipient reaching sent state) | Excl: suppressed/failed-render recipients | sent_at | STD + campaign, template, transactional/campaign | P1 |
| Delivery rate | Provider-confirmed delivery | delivered events ÷ sends | Excl: sends <24h old (still settling) | delivery event time | STD + campaign | P1 |
| Bounce rate | Undeliverable | bounce events ÷ sends, hard vs soft split | Soft bounces that later deliver count as delivered | delivery event time | STD + bounce type | P1 |
| Complaint rate | Spam complaints | complaint events ÷ delivered | — | delivery event time | STD + campaign | **P3** (complainer identity never in reports) |
| Unsubscribe rate | Opt-outs caused | unsubscribe events ÷ delivered, per campaign | Incl: per-topic unsubscribes attributed to triggering campaign | event time | STD + topic | P1 (per-person P3) |
| Segment size | Audience reach at send | EmailAudienceDefinition resolved count at approval + at send | Both counts shown; drift >10% flags the campaign | resolution time | STD + audience definition | P1 |
| Reminder response | Action after reminder | target action (confirm/attend) within 72h of reminder delivery ÷ reminded | Excl: opt-in open/click data unless org enabled | delivery event time | STD + reminder type | P1 |
| Urgent-request conversion | Urgent asks that got signups | signups attributable (link-through or within 48h by recipient) ÷ recipients of urgent sends | Attribution window documented on the dashboard | send time | STD + campaign | P1 |
| Opens / clicks *(opt-in orgs only)* | Engagement, where consented | opens ÷ delivered; clicks ÷ delivered | Only recipients with tracking consent in both terms | event time | STD + campaign | **P3** |

## 6. Maintenance — owner: Maintenance coordinator · refresh 15m

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Open work requests | Current backlog | count(WorkRequest not in closed/rejected/duplicate) | Snapshot + trend | snapshot time | STD + status, severity, category, asset, location | P1 |
| Time-to-triage | Report → triage decision | median(first status-change out of needs_triage − `created_at`) | Excl: duplicates | request `created_at` | STD + severity | P1 |
| Time-to-assign | Triage → owner | median(WorkAssignment `created_at` − triage time) | Excl: rejected | triage time | STD + severity | P1 |
| Time-to-resolve | Report → closed | median(closed_at − `created_at`), by severity | Excl: rejected/duplicate; blocked time reported separately, not subtracted | closed_at | STD + severity, category | P1 |
| Overdue requests | Past due and open | count(open with due < now) | — | due date | STD + severity | P1 |
| Repeat failures | Same asset failing again | assets with ≥2 closed requests in same category within 90d | Excl: preventive-schedule requests | request `created_at` | STD + asset, category | P1 |
| Preventive completion rate | Scheduled maintenance done on time | schedule occurrences completed by due ÷ occurrences due in period | Excl: schedules paused by admin | next_due | STD + asset, schedule | P1 |
| Requests by asset/location | Hotspots | count grouped by asset and by location | — | request `created_at` | STD + category | P1 |
| Blocked work | Stuck items | count(status in blocked/waiting_parts/waiting_vendor) + median age in blocked state | — | status entered_at | STD + blocked reason | P1 |
| Volunteer maintenance hours | Volunteer effort on upkeep | sum(approved VolunteerHourEntry, source=maintenance) | Excl: vendor/staff hours | activity date | STD + asset, location | P1 (per-person P2) |

## 7. Donations — owner: Finance manager · refresh 15m (volume RT on campaign pages)

All donor-identifying drill-downs are P3: finance manager + org admin only, access
audited. Public campaign-progress widgets show only P1 aggregates the campaign has
opted to publish.

| Metric | Meaning | Formula | Included / Excluded | Date field | Filters | Privacy |
|---|---|---|---|---|---|---|
| Donation volume | Money raised | sum(amount, status=succeeded) | Excl: failed/pending; refunds netted in a separate "net" variant, never silently | provider succeeded event time | STD + campaign, designation, one-time/recurring | P1 (rows P3) |
| Donor count | Distinct donors | distinct donor person (anonymous donations counted as donations, not donors) | Excl: fully-failed donors | succeeded event time | STD + campaign | P1 |
| Average donation | Typical gift | volume ÷ succeeded donation count; median shown alongside | Excl: refunded-in-full donations | succeeded event time | STD + campaign | P1 |
| Recurring donor count | Active recurring supporters | distinct donors with an active recurring plan at period end | Excl: cancelled/failed-terminal plans | plan status at snapshot | STD + campaign | P1 (rows P3) |
| Campaign performance | Progress vs goal | succeeded volume ÷ DonationCampaign.goal | Incl: only if campaign has a goal | succeeded event time | campaign | P1 |
| Failed recurring payments | At-risk recurring revenue | count(PaymentEvent failed on recurring) + affected plan count, retry outcomes | Excl: failures later succeeded within retry window (shown as recovered) | failure event time | STD + failure reason | P1 (rows P3) |
| Refunds | Money returned | count + sum(refund PaymentEvents) | Incl: partial refunds at refunded amount | refund event time | STD + campaign, reason | **P3** |
| Donor retention | Donors who give again | donors from period N with a succeeded donation in N+1 (year-over-year default) | Excl: anonymous (unlinkable) donations | succeeded event time (cohort) | STD + cohort year | P1 (rows P3) |

## First-slice metrics (training funnel + attendance)

Shipped with the training-registration slice, before any other dashboard:

1. **Registrations** (§4) — per course/session, public vs internal, by source.
2. **Attendance rate** (§4).
3. **Completion rate** (§4).
4. **No-show rate** (§4).
5. **Waitlist size** (§4).
6. **Capacity utilization** (§4).
7. **Verified-interest rate → Orientation registration rate → Orientation attendance
   rate** (§1) as the single funnel view.
8. **Training→volunteer conversion** (§4) — the slice's headline outcome metric.

Slice dashboards obey the same authorization rule: trainers see their own sessions'
metrics with roster drill-down; org admins see all; nobody gets a drill-down their role
could not list directly.
