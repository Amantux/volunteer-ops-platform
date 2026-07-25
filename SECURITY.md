# Security Policy

## Reporting a vulnerability
**Please do not report security issues through public GitHub issues.**

Report privately via GitHub's [private vulnerability reporting](https://github.com/Amantux/volunteer-ops-platform/security/advisories/new)
(Security → Report a vulnerability), or email **alex@alexmoyse.com** with details and, if
possible, steps to reproduce. We aim to acknowledge within a few business days and will keep you
updated as we work on a fix.

Please give us a reasonable window to remediate before any public disclosure.

## Supported versions
This project is pre-1.0; security fixes are applied to the `master` branch. Pin to a commit or
release for reproducible deployments.

## Security posture (what's built in)
- Passwordless magic-link auth; scope-aware RBAC; session revocation (logout / forced sign-out).
- A production **startup guardrail** that refuses to boot with an insecure configuration (weak
  secret, in-memory rate limiter, bot-check disabled, non-https base URL, or a dev email sink).
- User-authored page HTML/CSS is server-sanitized (nh3) and page-scoped; embeds run in sandboxed
  iframes; the site sets a strict Content-Security-Policy.
- Governed automation: agents operate under R0–R4 risk levels and cannot perform prohibited or
  approval-required actions; MCP write tools are permissioned, audited, and idempotent.
- CI runs dependency and SAST scanning (`pip-audit`, `bandit`, `npm audit`) on every change.

See [docs/security/threat-model.md](docs/security/threat-model.md) and
[docs/agents/agent-permissions.md](docs/agents/agent-permissions.md) for the full model, and the
[launch checklist](docs/operations/launch-checklist.md) for pre-go-live hardening (incl. deferred
items such as MFA).
