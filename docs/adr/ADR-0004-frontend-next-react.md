---
title: ADR-0004 — Frontend: Next.js / React + TypeScript
owner: Architecture
status: accepted
last_reviewed: 2026-07-22
---

# ADR-0004: Next.js / React + TypeScript for the frontend

**Status:** Accepted · **Date:** 2026-07-22

## Context
The public front door needs SEO + strong mobile performance (SSR/SSG); the authenticated
app needs a typed SPA with accessible primitives. Authorization must never rely on the
frontend.

## Decision
Use **Next.js + React + TypeScript**. SSR/SSG for public content; typed API client shared
with backend schemas where practical (Zod). Role-aware navigation is UX only.

## Alternatives considered
- **Plain Vite + React** (16/20): fine for the app shell (the prototype used it) but weaker
  public SEO/performance.
- **HTMX/server-rendered** (14/20): simple but weaker accessible-component ecosystem and
  typed sharing.

## Consequences
+ Fast, accessible, SEO-friendly public site; one language across the stack.
− Slightly higher build complexity than plain Vite; acceptable for the public-facing needs.
