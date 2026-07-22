# Volunteer Ops — Public Web

Public-facing training & registration site for the Volunteer Operations Platform.
Built with **Next.js 14 (App Router) + TypeScript + React 18**. Public content is
server-rendered; the registration and email-verification steps are client
components. Styling is a single hand-written design system (`app/globals.css`) —
no Tailwind, no component library.

## Pages

| Route             | Rendering | Purpose                                              |
| ----------------- | --------- | ---------------------------------------------------- |
| `/`               | static    | Welcome / what we do + CTA to browse trainings       |
| `/trainings`      | SSR       | Live list of open sessions (empty + error states)    |
| `/trainings/[id]` | SSR       | Session detail + client registration form            |
| `/verify`         | client    | Reads `?token=` and confirms the email registration  |

## Requirements

- Node 20+
- The FastAPI backend running at `http://localhost:8000` with at least one open,
  public session seeded.

## Develop

```bash
cp .env.local.example .env.local   # optional; sane defaults are built in
npm install
npm run dev                        # http://localhost:3000
```

`next.config.js` proxies `/api/*` → `http://localhost:8000/api/*`, so the browser
talks to the backend same-origin in dev. Server-side fetches (SSR) use
`API_INTERNAL_BASE` (default `http://localhost:8000/api`) since a relative path
has no host on the server.

### Environment variables

| Var                   | Default                       | Used by                     |
| --------------------- | ----------------------------- | --------------------------- |
| `NEXT_PUBLIC_API_BASE`| `/api`                        | Browser fetches             |
| `API_INTERNAL_BASE`   | `http://localhost:8000/api`   | Server-side (SSR) fetches   |

## Build & run (production)

```bash
npm run build     # tsc typecheck + next build  (CI gate)
npm run start     # serves on port 3000
```

- **Build command:** `npm run build`
- **Start command:** `npm run start` (listens on **port 3000**)

## Tests

End-to-end and accessibility tests use Playwright + `@axe-core/playwright`
(`e2e/registration.spec.ts`). They start `next start` automatically via
`playwright.config.ts` and expect the backend (with a seeded open session) at
`:8000`.

```bash
npx playwright install chromium   # one-time browser download (large)
npm run test:e2e
```

The specs cover: browsing `/trainings`, opening a session, submitting the
registration form and seeing the confirmation, a keyboard-only pass, a 404 case,
and axe checks (no serious/critical violations) on `/`, `/trainings`, and a
detail page.

## Accessibility notes

- Semantic landmarks (`header`/`nav`/`main`/`footer`), skip-to-content link, one
  `<h1>` per page.
- All inputs have `<label for>`, correct `type`/`inputmode`/`autocomplete`, and
  `required`/`aria-required`; errors are wired via `aria-describedby` and
  `aria-invalid`.
- Form success/error announced through `aria-live` regions.
- Visible focus outlines, 44px+ touch targets, WCAG AA text contrast, respects
  `prefers-reduced-motion`.
