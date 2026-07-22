---
title: Product Vision
owner: Product
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [non-goals.md, ../architecture/system-design.md]
---

# Product Vision

## The problem
Volunteer organizations run on spreadsheets, inboxes, and one overloaded coordinator's
memory. Prospective volunteers hit a brochure site with no clear path in; active
volunteers can't answer "what's next for me?" without emailing someone; coordinators
spend evenings chasing sign-ups, reminders, waitlists, and hour logs by hand. Training,
scheduling, maintenance, comms, and donations live in disconnected tools, so nothing is
auditable and nobody trusts the numbers.

## The outcome
One org-scoped operational platform where:
- The **public front door** converts interest into action: register for a training,
  report an issue, donate — without creating an account first.
- **Volunteers** always see an obvious next action: what's happening, what they're
  eligible for, where to be, what to bring, who to ask.
- **Coordinators and staff** run training, shifts, maintenance, comms, and donations
  from one system with server-enforced permissions and a full audit trail.
- **Governed automation** (reminders, digests, drafts, staffing suggestions) removes
  grunt work while humans keep authority over every high-impact action.

Net effect: admin burden goes down, participation goes up, and every consequential
action is explainable after the fact.

## Product principles
| Principle | What it means in practice |
|---|---|
| **Volunteer-first** | Every surface answers the volunteer's questions (what/when/where/eligible/next action) before it serves an internal reporting need. |
| **Low-friction public participation, progressive enrollment** | Participation deepens in stages: (1) browse anonymously → (2) act as a guest (register/report/donate as a Person, no account) → (3) verify contact → (4) create a User account → (5) build a VolunteerProfile & onboard → (6) hold scoped roles. No stage demands more identity than it needs. |
| **Human-controlled automation** | Separate *confidence* from *permission to act*: an agent may be 99% sure and still only propose. High-risk actions (see permissions.md) always require explicit human authorization. |
| **Configurable, not hard-coded** | Org hierarchy labels, onboarding stages, volunteer statuses, work-request workflows, and policies are org configuration, not code branches. |
| **Modular-monolith-first** | One deployable API with enforced module boundaries; no microservices until an ADR justifies them (see non-goals). |
| **Accessible & mobile-first** | WCAG 2.1 AA, keyboard operable, touch-friendly; volunteers use this standing in a field on a phone. |

## Success signals
| Signal | Direction we expect |
|---|---|
| Guest training registration completion rate (start → confirmed) | High and rising; drop-off points instrumented |
| Guest → volunteer conversion rate after training completion | Rising quarter over quarter |
| Coordinator hours spent on manual reminders/waitlists/rosters | Falling (automation absorbs it) |
| Shift fill rate & time-to-fill for understaffed shifts | Rising / falling respectively |
| Median time from maintenance report → triage decision | Under org SLA target |
| % of bulk comms sent via preview→approval flow (vs. ad hoc) | Approaching 100% |
| Volunteers who can state their next action (survey / "what's next" click-through) | Rising |
| Audit coverage: privileged actions with a matching AuditEvent | 100%, by construction |

What we are **not** building is fixed in [non-goals.md](non-goals.md).
