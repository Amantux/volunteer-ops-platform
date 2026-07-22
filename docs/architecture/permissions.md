---
title: Permissions & Authorization Model
owner: Security / Architecture
status: current
last_reviewed: 2026-07-22
applies_to: platform
depends_on: [domain-model.md]
---

# Permissions Model

## Principles
- **Server-side enforcement everywhere.** API routes, worker jobs, and MCP tools all check
  authorization. Frontend role-awareness is UX only.
- **RBAC with scoped assignments.** A `UserRoleAssignment` binds `(user, role, scope)` where
  scope is `org` | `program` | `team` | `location`. A coordinator for Program A cannot act on
  Program B.
- **Least privilege.** Roles grant the minimum. Finance does not get volunteer operational
  records; comms does not get donor PII beyond audience needs.
- **Org boundary is absolute.** No permission crosses `org_id`. Cross-org access does not
  exist outside an explicit (rare) platform-admin path.
- **Separation of confidence and authority (agents).** Agents act only within an explicit
  allowlist and never self-escalate (see agents/agent-permissions.md).

## Enforcement mechanics
- A central `authorize(user, action, resource)` service resolves: org match → scoped role →
  permission. Called by an API dependency, by workers before side effects, and inside each
  MCP tool.
- Object-level checks (e.g. "this coordinator owns this shift's program") layered on top of
  action-level permissions.
- Every **deny** on a privileged action is logged (audit + observability signal).
- Privileged roles require **MFA**; sensitive actions may require re-auth (step-up).

## Capability matrix (baseline roles × capability groups)
Legend: ● full · ◐ scoped/limited · ○ none. Scope column: what the ● is bounded by.

| Capability group | Public | Prospective | Volunteer | Coordinator | Trainer | Maint. coord | Comms mgr | Finance mgr | Org admin |
|---|---|---|---|---|---|---|---|---|---|
| View public content | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Register for public training | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Donate | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Submit interest / onboard self | ○ | ● | ● | ● | ● | ● | ● | ● | ● |
| Manage own profile/availability | ○ | ◐ | ● | ● | ● | ● | ● | ● | ● |
| View eligible opportunities | ○ | ◐ | ● | ● | ● | ● | ● | ● | ● |
| Sign up / cancel own shift | ○ | ○ | ● | ● | ● | ● | ● | ● | ● |
| Log/verify own hours | ○ | ○ | ● | ● | ● | ● | ● | ● | ● |
| Report an issue (maintenance) | ◐ (public form) | ● | ● | ● | ● | ● | ● | ● | ● |
| Create/manage shifts | ○ | ○ | ○ | ◐ program/team | ○ | ○ | ○ | ○ | ● |
| Assign volunteers | ○ | ○ | ○ | ◐ program/team | ○ | ○ | ○ | ○ | ● |
| Review waitlists / attendance | ○ | ○ | ○ | ◐ program/team | ◐ own sessions | ○ | ○ | ○ | ● |
| Approve hours | ○ | ○ | ○ | ◐ program/team | ○ | ◐ maint hours | ○ | ○ | ● |
| Manage training sessions | ○ | ○ | ○ | ○ | ◐ own courses | ○ | ○ | ○ | ● |
| Record training completion | ○ | ○ | ○ | ○ | ◐ own sessions | ○ | ○ | ○ | ● |
| Triage/assign work requests | ○ | ○ | ○ | ◐ if enabled | ○ | ● maint scope | ○ | ○ | ● |
| Close work w/ evidence | ○ | ○ | ○ | ○ | ○ | ● maint scope | ○ | ○ | ● |
| Draft comms / update | ○ | ○ | ○ | ◐ program audience | ◐ course audience | ◐ maint notices | ● | ○ | ● |
| **Approve & send bulk comms** | ○ | ○ | ○ | ○ | ○ | ○ | ◐ per policy | ○ | ● |
| View operational reports | ○ | ○ | ○ | ◐ program/team | ◐ training | ◐ maintenance | ◐ comms | ◐ donations | ● |
| View donation records | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ● |
| Issue refunds | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ◐ w/ approval | ● |
| Manage volunteer PII / merge | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● (merge=approval) |
| Configure org / roles / flags | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| View audit log | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| Manage integrations / secrets | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |

Notes:
- **Comms "approve & send bulk"** is ◐ for the comms manager only within a configured policy
  (size/audience/sensitivity thresholds); above threshold → org-admin approval.
- **Platform admin** (multi-org) is intentionally omitted from the baseline; if enabled it
  must not casually read org data — access is break-glass, logged, and time-boxed.

## High-risk actions (always require explicit human authorization; never agent-autonomous)
Send sensitive/bulk comms · reject/discipline a volunteer · change permissions · issue
refunds · modify financial records · delete records · expose private volunteer data ·
schedule outside declared constraints · publish public content · merge people. These map to
the agent non-goals and each emits an `AuditEvent`.

## First-slice permission surface (training registration)
- Public: `training.view_public`, `training.register_guest`.
- Trainer (scoped to own sessions): `training.manage_session`, `training.record_attendance`,
  `training.record_completion`, `training.view_roster`.
- Org admin: `training.manage_course`, `report.view_training`, `audit.view`.
- Agent (read/draft only in slice): `training.read_metrics`, `comms.draft` (no send authority
  above the auto-reminder allowlist).
