---
title: Non-Goals
owner: Product
status: current
last_reviewed: 2026-07-22
applies_to: platform
---

# Non-Goals (explicit scope boundaries)

These keep the build honest. Revisit only with a recorded decision (ADR).

## Product non-goals
- **Not a brochure site.** A public marketing page with a signup form bolted on is
  explicitly rejected. The public site is the front door of an operational system.
- **Not a full accounting/GL system.** Donations integrate a payment provider and export
  for accounting; we do not reconcile ledgers or issue tax documents beyond receipts.
- **Not a general HR / payroll / applicant-tracking suite.**
- **Not a full LMS.** Training tracks registration, attendance, completion, and
  qualifications — not course authoring, quizzes, or SCORM.
- **Not a chat/messaging platform.** Communications = transactional + campaign email
  (and in-app updates); real-time chat is out.
- **Not a document-management system.** File attachments are supported; versioned DMS is not.

## Architecture non-goals (for the initial releases)
- **No microservices.** Modular monolith first; split only when scale/ops justify it (ADR).
- **No multi-tenant billing platform** before the core volunteer workflows work end-to-end.
- **No Kubernetes** unless operationally justified; Docker Compose is the baseline.
- **No custom form-builder scripting language.** Start with validated, declarative
  conditions; do not grow a second programming language inside form config.
- **No storing payment-card data.** Ever. The provider holds PCI scope.

## Agent / automation non-goals
- **No autonomous high-impact actions.** Agents never send sensitive/bulk comms, reject or
  discipline volunteers, change permissions, move money, delete records, expose private
  data, or schedule people outside declared constraints — regardless of confidence.
- **No agent-decided authorization.** A tool being *available* never implies permission.
- **No AI for deterministic logic** (eligibility, waitlist order, audience math) that
  should be ordinary, testable code.
- **No raw DB/shell/Docker/secret access via MCP.**

## Data non-goals
- **No collect-because-maybe-useful.** Every sensitive field has a documented purpose and
  retention policy or it is not collected.
- **No invasive tracking by default.** Email open/click tracking is opt-in per org.
- **No cross-organization search or data bleed.**

## Process non-goals
- **No "done" without validation evidence.** Reporting completion without tests/checks is
  an anti-goal (see Definition of Done in the brief).
- **No frontend-only authorization.** Every protected operation is enforced server-side.
