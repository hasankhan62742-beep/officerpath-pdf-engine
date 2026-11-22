# Phase 2 M1 — Frontend Architecture

**Date:** 2026-11-22
**Stack (per the Phase 2 prompt §3):** Next.js (App Router) + React +
TypeScript + Tailwind CSS. Data: TanStack Query. Forms: React Hook Form
+ Zod. No Flutter in the new frontend; the Flutter app remains a legacy
client and does not dictate this architecture.

## 1. Where the app lives — `web/` at the repo root

**Decision:** the Next.js app lives in `web/` at the repository root
(`officerpath-pdf-engine/web/`), beside `app/` (the Python engine).

Reasons:

1. **One repo, two deployables.** The engine and the frontend share the
   branch, the PR/CI story, and the API contract, but deploy
   independently (see doc 06). A monorepo folder keeps the contract
   visible; a separate repo would drift.
2. **The Python tooling is untouched.** `app/`, `alembic/`,
   `requirements*.txt`, `Dockerfile`, `render.yaml` keep their paths;
   nothing in Phase 1 moves.
3. **CI can gate both.** The existing `.github/workflows/ci.yml` gains
   a `web` job (lint/typecheck/test/build) alongside the Python jobs —
   one branch, one green gate.
4. **Alternatives rejected:** (a) a separate GitHub repo — loses the
   shared branch and makes the API contract a cross-repo handshake;
   (b) `app/web/` inside the Python package — would confuse the Python
   import tree and the Docker build context; (c) replacing the Flutter
   repo — out of scope, the Flutter app is a separate product surface.

`web/` gets its own `package.json`, `tsconfig.json`,
`tailwind.config.ts`, `next.config.mjs`, `.env.example`, and README.
The Python `.gitignore` gains Node entries (`node_modules/`,
`.next/`) in M2. The Dockerfile does **not** build the frontend —
the frontend deploys separately (doc 06).

## 2. Directory layout (`web/`)

```
web/
  app/                          # Next.js App Router
    (public)/                   # public group — no auth layout
      page.tsx                  # Home (landing)
      about/page.tsx
      features/page.tsx
      how-it-works/page.tsx
      exam-preparation/page.tsx
      pricing/page.tsx
      contact/page.tsx
      privacy/page.tsx
      terms/page.tsx
      login/page.tsx
      register/page.tsx
      forgot-password/page.tsx
      reset-password/page.tsx
    (app)/                      # authenticated group — dashboard layout
      layout.tsx                # sidebar + topbar, auth guard
      dashboard/page.tsx
      documents/page.tsx        # My Documents
      documents/[id]/page.tsx   # document detail + report + review
      questions/page.tsx        # Question Bank
      questions/[id]/page.tsx
      tests/new/page.tsx        # Test Builder
      tests/page.tsx            # My Tests
      tests/[id]/page.tsx       # test detail / start
      exam/[sessionId]/page.tsx # Examination Interface
      results/page.tsx
      results/[id]/page.tsx
      mistakes/page.tsx         # Mistake Notebook
      bookmarks/page.tsx
      profile/page.tsx
      subscription/page.tsx     # read-only status in Phase 2 (Phase 3 owns payments)
      notifications/page.tsx
    admin/                      # admin group — backend-enforced role
      layout.tsx
      page.tsx                  # admin dashboard
      users/page.tsx
      documents/page.tsx
      jobs/page.tsx
      questions/page.tsx
    api/                        # (only if a BFF route is ever needed; default: none)
    globals.css
    layout.tsx                  # root layout, fonts, metadata
    not-found.tsx
    error.tsx
    loading.tsx
  components/
    ui/                         # primitives: Button, Input, Card, Table, Dialog,
                                # Badge, Progress, Tabs, Toast, EmptyState, Spinner
    layout/                     # Header, Footer, Sidebar, Topbar, MobileNav
    landing/                    # Hero, Features, HowItWorks, Pricing, CTA
    dashboard/                  # StatCard, ActivityList, SubjectChart
    documents/                  # UploadDropzone, DocumentCard, JobProgress
    questions/                  # QuestionCard, AnswerStatusBadge, EvidenceTrail
    exam/                       # QuestionPalette, Timer, OptionButton, ExamNav
    results/                    # ScoreRing, SubjectBreakdown, ReviewList
  lib/
    api/                        # typed API client (fetch wrapper, auth header, error mapping)
    queries/                    # TanStack Query hooks per resource
    auth/                       # Supabase browser client, session helpers, guards
    utils/                      # formatting, cn(), marking helpers (display only)
    constants.ts                # routes, exam lists, marking defaults (display only)
    types.ts                    # shared TS types mirroring backend schemas
  hooks/
  public/
    icons/ manifest.webmanifest (M9 — PWA readiness, not a blocker)
  e2e/                          # Playwright tests (M10)
  .env.example
  next.config.mjs
  tailwind.config.ts
  tsconfig.json
```

**Rule:** no page imports the Supabase service-role key, no page talks
to Supabase PostgREST for engine tables, and no page computes marks.
All data flows through `lib/api` → the FastAPI backend (doc 05).

## 3. Design system

### 3.1 Brand and palette

Product: **OfficerPath AI**. Tagline: *"Prepare Smarter. Practice
Better. Become Exam Ready."* CTA: *"Start Your Preparation"*.

Brand palette (prompt §4): **orange, green, blue, purple** — balanced,
not all four everywhere. Token mapping (finalised in M2 with the
design-token file; this is the M1 direction):

| Role | Token | Use |
|---|---|---|
| Primary | Orange (`--brand-primary`) | Main CTA, active states, exam accent |
| Success | Green (`--brand-success`) | Correct answers, passed states, positive deltas |
| Info | Blue (`--brand-info`) | Links, info states, secondary actions |
| Accent | Purple (`--brand-accent`) | Premium highlights, admin accents, sparing use |
| Danger | Red (functional, not brand) | Incorrect answers, destructive actions |
| Neutrals | Slate scale | Text, borders, surfaces |

- **Pakistan map watermark:** decorative, low-contrast SVG in the
  landing hero and brand sections only; `aria-hidden`, never over
  body text, never reducing contrast below WCAG AA. M2 produces the
  asset; if no clean licensed SVG is available, the section ships
  without it rather than with a distorted map.
- **Typography:** one display font + one body font (system stack
  fallback; final choice in M2 — Inter or equivalent; no more than two
  families). Scale: display 40/32, h1 32, h2 24, body 16, small 14.
- **Spacing:** 4 px base scale (4/8/12/16/24/32/48). Cards: 16–24 px
  padding, 12–16 px radius, 1 px border + subtle shadow. No heavy
  glass effects.
- **Motion:** 150–200 ms transitions on interactive elements only;
  `prefers-reduced-motion` respected. No auto-playing animation on the
  exam page.

### 3.2 Components and states

- **Primitives first:** every page is built from `components/ui`
  (Button, Input, Card, Table, Dialog, Badge, Progress, Tabs, Toast,
  EmptyState, Spinner). No one-off buttons or inputs.
- **Every async view has four states:** loading (skeleton, not a
  blank page), error (message + retry), empty (illustration + next
  action), success. A new student sees empty states with real
  guidance, never zeros presented as data.
- **Answer-status labels (from the engine, never invented):**
  `Verified Answer` (manual), `Detected Answer` (key/inline/style/
  visual), `Needs Review` (pending/conflict), `Unknown Answer`
  (`correct_index = -1`), `Conflicting Answer`. UNKNOWN is rendered
  as unanswered — never as a correct option, never with a green tick.
- **No non-functional controls.** Every visible button does something
  real or is labelled unavailable with a reason (prompt §28).

### 3.3 Responsive — mobile-first, mandatory

- Breakpoints: mobile (<640), tablet (640–1024), desktop (>1024).
  Layouts are designed mobile-first; the desktop layout is the
  enhancement, not the other way round.
- Touch targets ≥ 44 px. Exam options are full-width rows on mobile.
  The question palette collapses to a bottom sheet on small screens.
- Sidebar becomes a bottom nav / hamburger on mobile; the exam page
  hides the sidebar entirely (distraction-free).
- Tested on Android Chrome + iPhone Safari viewports in M10
  (Playwright device emulation at minimum; real-device spot check by
  the owner).

## 4. Data fetching

- **TanStack Query** for all server state: query keys per resource
  (`['documents']`, `['documents', id]`, `['jobs', id]`,
  `['questions', filters]`, `['tests', id]`, `['results', id]`).
  Stale times: lists 30 s, job status 0 s (polling — see below),
  results infinite (immutable once submitted).
- **Job polling:** `GET /api/v1/async-jobs/{id}` every 5 s while
  `queued`/`processing`, backing off to 15 s after 2 min; stops on a
  terminal state. No webhook exists (doc 02 §4). Polling is disabled
  when the tab is hidden (TanStack `refetchInterval` + visibility).
- **Mutations** (upload, correction, test create, answer save, submit)
  use TanStack mutations with optimistic updates only where safe
  (bookmarks, notes). **Never optimistic for marks, submission, or
  corrections** — those await the server response.
- **Pagination:** server-side, cursor or offset per the backend
  contract (decided when GAP-2/3 land in M4/M5). No unbounded lists.
- **Error mapping:** the API error shape `{error: {code, message}}`
  maps to user-facing copy in `lib/api` (e.g. `file_too_large` →
  "This file is larger than 100 MB"; `rate_limited` → "Too many
  attempts — try again in a minute"). Raw codes are never shown to
  students.

## 5. Auth flow (Supabase Auth — see doc 05 for the security detail)

1. **Register** (`/register`): name, email, password, optional phone,
   preferred exam, education level. Supabase Auth creates the user;
   the frontend then calls `PATCH /api/v1/me` (GAP-1, M3) to create
   the engine-side `student_profiles` row. **Email verification is
   real** — Supabase email verification flow; no fake OTP anywhere.
2. **Login** (`/login`): Supabase Auth session (browser client,
   PKCE flow). The session token is attached as
   `Authorization: Bearer <token>` on every API call.
3. **Protected routes:** `(app)/` and `/admin/` layouts check the
   session server-side (middleware + layout guard); unauthenticated
   users are redirected to `/login?next=...`. The guard is UX only —
   **the backend enforces every rule** (doc 05).
4. **Password reset:** `/forgot-password` → Supabase reset email →
   `/reset-password`. Logout clears the session and the query cache.
5. **Profile/settings:** `/profile` reads/writes the engine profile
   (GAP-1); account settings (password change) go through Supabase
   Auth.

## 6. Public pages (11, prompt §6)

Home, About, Features, How It Works, Exam Preparation, Pricing,
Contact, Login, Register, Privacy Policy, Terms and Conditions.
Content rules: the value proposition and feature list come from the
prompt §6; **no invented testimonials, student numbers, success
rates, or institutional partnerships**; no false accuracy or
guaranteed-success claims; screenshots only of the real implemented
UI (M2 produces them from the built app — placeholder screenshots are
labelled as such until then). Pricing page: Phase 2 has no payment
system (Phase 3) — the page describes the intended plans honestly
and marks payment as coming later, or is deferred to M9 if the owner
prefers. Decision in M2.

## 7. Student app routes (summary)

Dashboard, My Documents (+ detail/report/review), Question Bank (+
detail), Create Test, My Tests (+ detail/start), Exam (`/exam/[id]`),
Results (+ detail), Mistake Notebook, Bookmarks, Profile,
Subscription (read-only status in Phase 2), Notifications.
Admin routes are separate (`/admin/*`, backend-enforced — doc 05 §4).

## 8. PWA readiness (later stage, not a blocker)

- Architecture keeps the door open: `manifest.webmanifest` + icons in
  `public/` (M9), `next-pwa`-style service worker **only** for the
  public shell (landing pages, static assets). **Never** cache private
  documents, student data, or authenticated API responses.
- Installability is evaluated in M9; it must not delay M2–M8. No
  offline exam mode in Phase 2 (answers need the server).

## 9. Version and tooling decisions (M2 to pin)

- Next.js latest stable App Router release available at M2 start;
  React 19-compatible versions; TypeScript strict; Tailwind CSS v4
  (or v3 if v4 conflicts with the chosen component approach — decided
  in M2 with a reason recorded).
- `next.config.mjs`: `NEXT_PUBLIC_API_URL` (dev
  `http://127.0.0.1:8000`, prod the Render URL), image domains (none
  remote in Phase 2 — question assets are served via the backend),
  `reactStrictMode: true`.
- Lint/format: ESLint (Next config) + Prettier; typecheck `tsc
  --noEmit` in CI; unit tests Vitest + Testing Library; E2E Playwright
  (M10).
