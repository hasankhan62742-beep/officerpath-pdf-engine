# Phase 2 Milestone 2 Report — Frontend Foundation and Design System

**Date:** 2026-11-22
**Branch:** `officerpath-phase2-web` (from Phase 1 head `69ca62d`, M1 `dee2f06`)
**Gate verdict: MET** — Next.js foundation, design system and all 11
public pages built, verified locally. No deploy, no push, no Phase 1
code touched.

All numbers below are measured in this run (VM numbers); anything
unmeasured is labelled UNVERIFIED.

## Gate evidence (actually run, this session)

| Gate | Result |
|---|---|
| `npm run build` (production) | **PASS** — 15 static routes, compiled in ~2–28 s (Turbopack) |
| `npm run lint` (ESLint 9, flat config) | **clean, 0 problems** (after 1 fix — see §4) |
| `npx tsc --noEmit` (TypeScript strict) | **clean, exit 0** |
| Python engine gates (unchanged code) | pytest **492 passed / 0 failed** (636.5 s under contention), ruff check + format clean (186 files), mypy CI gate **SUCCESS** (68 files) |
| Page render check (prod server, curl) | **14/14 HTTP 200** — 11 public pages + `/forgot-password` + `/robots.txt` + `/sitemap.xml`; unknown path returns the 404 page |
| Mobile check (Playwright Chromium, 360×800) | **12/12 pages, no horizontal overflow** (`scrollWidth` 360), mobile menu opens (9 links), contact + register validation errors shown |

## 1. What was built

### A. Scaffold — `web/` at the repo root (per M1 doc 04)

- **Next.js 16.4.6** (App Router, Turbopack by default) + **React 19.3.0**,
  **TypeScript 5.9.3** (strict), **Tailwind CSS 4.3.3** (CSS-first),
  **ESLint 9.39.5** (`eslint-config-next`, flat config).
- **TanStack Query 5.108.2** (wired in `components/providers.tsx`),
  **React Hook Form 7.92.0 + Zod 4.6.7 + `@hookform/resolvers` 7.0.8**.
- Node **v24.22.1** / npm **10.9.4** were already on the VM — nothing
  was installed at system level.
- `npm install` completed cleanly (361 packages at scaffold, +9 for
  the data/form libraries, +1 for Playwright test tooling).
- `web/.env.example` — placeholders only (API URL, site URL, Supabase
  URL + anon key). **No real secret anywhere in `web/`** (grep-verified;
  the only "service-role" mention is the comment forbidding it).
- `web/README.md` (install/run/build/test, honest not-connected list),
  `web/docs/design-tokens.md`, `app/icon.svg` (orange OP mark).

### B. Design system

- Tokens in `app/globals.css` (`@theme`): brand orange primary,
  green success, blue info, purple accent (sparing), functional red,
  slate neutrals; Inter via `next/font/google`; 4 px spacing scale;
  `--shadow-card` / `--shadow-lift`; 150–200 ms transitions;
  `prefers-reduced-motion` respected.
- **17 reusable components** in `components/ui/`: Button, Input,
  Textarea, Card, Badge, Modal, Toast, Spinner (+ LoadingState),
  EmptyState, ErrorState, Table, Pagination, Progress, Tabs, Accordion,
  Alert, SectionHeading — all with loading/error/empty states where
  applicable. No decorative dead controls.
- **Header** (sticky, desktop nav + mobile hamburger, 44 px targets,
  `aria-expanded`/`aria-current`) and **Footer**.
- **Pakistan map watermark** (`components/landing/pakistan-map.tsx`):
  simplified inline SVG outline, `aria-hidden`, 5–7% opacity, hero and
  CTA sections only, never over body text.

### C. Public pages — all 11, real content, no placeholders

| Page | Status |
|---|---|
| `/` Home | Hero "Prepare Smarter. Practice Better. Become Exam Ready." + Start Your Preparation CTA, features, 4 steps, 8 exams, CTA band |
| `/about` | Product story, traceability, honest measurement |
| `/features` | 12 features + FAQ accordion |
| `/how-it-works` | 7 steps, register → analyse |
| `/exam-preparation` | 8 exams + 13 subjects |
| `/pricing` | Free during Phase 2; paid plans Phase 3, **no prices invented** |
| `/contact` | Working validated form; states plainly submissions are **not sent anywhere yet** |
| `/login`, `/register` | Real forms, Zod validation; submit shows "authentication is not yet connected — coming in M3", nothing sent, no fake login |
| `/privacy`, `/terms` | Complete, product-specific pages (no lorem ipsum) |
| `/forgot-password` (extra) | Same honest not-connected state |

- **SEO:** per-page title/description + Open Graph, `robots.txt`,
  `sitemap.xml` (public pages only). Every page has exactly one `<h1>`
  (verified by Playwright — see §4 for the fix this required).
- **No fabricated content:** no testimonials, student numbers, success
  rates, partnerships or screenshots. The only email shown is the
  real `hello@abdulqadeerml.com`.

### D. CI + deployment decision

- `.github/workflows/ci.yml`: branch `officerpath-phase2-web` added to
  push + pull_request triggers; new `web` job (Node 24, `npm ci`,
  typecheck, lint, build). Python jobs untouched. (CI has never run on
  GitHub — no remote is configured; the job is verified locally only.)
- **Vercel free CONFIRMED** for frontend hosting (dated note in
  `docs/phase2/06-deployment-plan.md` §7): standard Next.js 16 build,
  nothing Vercel-specific, reversible; free tier needs no card; Netlify
  remains the fallback. **No account created, nothing deployed, no
  charge.** The owner still confirms before any account is connected.

## 2. Deviations from M1 doc 04 (recorded, not silent)

1. **Tailwind v4 has no `tailwind.config.ts`.** Tokens live in CSS
   (`@theme` in `app/globals.css`) — the v4 CSS-first model. The
   design-tokens doc records this.
2. **No `src/` directory.** `create-next-app` scaffolded `web/app/`
   at the package root, matching the M1 layout (`web/app/`).
3. **CORS was NOT added to the engine in M2.** Doc 06 §5 suggested
   M2 adds it, but the M2 brief forbids modifying Phase 1 Python code
   and no browser→API call exists in M2 (all pages are static; auth
   forms are not connected). CORS is deferred to **M3**, when the
   first browser call is made.
4. **`next lint` does not exist in Next 16** (removed) — lint runs via
   the ESLint CLI, as the scaffold configures it.
5. **Middleware is `proxy.ts` in Next 16** (the `middleware` filename
   is deprecated). No middleware/proxy was added in M2; the auth guard
   in M3 must use the new `proxy.ts` convention.
6. **Canonical domain is a placeholder** (`https://officerpath.ai`,
   via `NEXT_PUBLIC_SITE_URL`) until the owner confirms the production
   domain — stated in `lib/site.ts`, the sitemap, robots.txt and the
   web README.

## 3. Verification detail

### Page render table (production server, `curl`, final build)

| Path | HTTP | Notes |
|---|---|---|
| `/` | 200 | Hero headline + CTA text present in HTML |
| `/about` | 200 | |
| `/features` | 200 | |
| `/how-it-works` | 200 | |
| `/exam-preparation` | 200 | |
| `/pricing` | 200 | |
| `/contact` | 200 | |
| `/login` | 200 | |
| `/register` | 200 | |
| `/privacy` | 200 | |
| `/terms` | 200 | |
| `/forgot-password` | 200 | |
| `/robots.txt`, `/sitemap.xml` | 200 | |
| `/does-not-exist` | 404 | Custom not-found page renders |

### Mobile check (Playwright, Chromium, viewport 360×800)

Method: `node` script (scratch, `/tmp/m2-mobile-check.mjs`) driving the
production server on port 3100. Chromium binary: the cached
`chromium-1254` build via `executablePath` (see §4).

- 12/12 pages: HTTP 200, `document.documentElement.scrollWidth` = 360,
  **no horizontal overflow**.
- Every page has exactly one `<h1>` (after the §4 fix).
- Mobile menu button visible at 360 px; opens to show 9 links (7 nav +
  Log in + Start Your Preparation).
- Contact form: empty submit shows "Please enter your name."
  Register form: empty submit shows "Please enter your full name."
- Screenshots: `/tmp/m2-mobile-home-360.png`,
  `/tmp/m2-mobile-register-360.png` (verification artefacts, not in the
  repo).

### Python gates (engine untouched, re-run for the record)

pytest 492/0 (636.5 s — VM contention; M8's run was 469.8 s), ruff
clean, mypy SUCCESS (68 files). No Python file was modified in M2.

## 4. Defects found and fixed in M2

1. **Build failure — `new Date()` in the footer (Next 16 prerender
   rule).** With `cacheComponents: true`, `new Date()` is blocked
   during static prerendering (server and client components alike).
   Fixed by rendering the year in a `CurrentYear` client component
   inside a `<Suspense fallback={2026}>` boundary — the sanctioned
   fix from the Next 16 upgrade guide.
2. **Lint error — `setState` in `useEffect`** (`react-hooks/
   set-state-in-effect`). The first fix attempt (year in state via
   effect) tripped this rule; replaced by the Suspense approach above.
   Final lint: 0 problems.
3. **Missing `<h1>` on 7 pages.** Features, How It Works, Exam
   Preparation, Pricing used `SectionHeading` (h2) as the page title;
   Login, Register, Forgot Password used `CardTitle` (h3). Fixed by
   adding a `level` prop to `SectionHeading` and an `as` prop to
   `CardTitle`; re-verified by Playwright (12/12 pages, one h1 each).
4. **`npx playwright install chromium` failed twice** (download failure
   for the Chrome-for-Testing 1255 build). Worked around with the
   already-cached `chromium-1254` binary via `executablePath`. The
   Playwright version pin (matching browser) is a known M10 item:
   either the download works on the CI runner or the version must be
   pinned to the cached build.
5. **`pkill -f "next start"` killed my own shell** (the pattern matched
   my own command line). No harm done — the server was stopped by PID
   afterwards. Recorded so it is not repeated.

## 5. What is NOT done / carried to M3+

- **Authentication (M3):** login/register/forgot-password are validated
  forms only. No Supabase client is installed, no session exists, no
  email is sent. The M3 brief must wire real Supabase Auth.
- **Dashboard, documents, engine integration (M4):** no API calls exist
  yet; `lib/api` and the TanStack query hooks land with the first real
  data in M4. The dual job-store finding (M1) is still unresolved —
  assigned to M3 with its own ADR.
- **CORS** in the engine (deferred to M3 — see §2.3).
- **Tests:** no Vitest/Playwright test suite in the repo yet (M10
  owns E2E; unit tests land with the first logic in M3/M4). The mobile
  check script is scratch in `/tmp`, not a committed test.
- **Deploy:** nothing deployed anywhere; Vercel account not created.
- **iPhone Safari / real-device check:** UNVERIFIED — Playwright
  Chromium at 360 px only. Real-device spot check is the owner's, per
  M1 doc 04 §3.3.
- **Lighthouse/accessibility audit:** not run in M2 (M9/M10).

## 6. Files changed (local only, branch `officerpath-phase2-web`)

- New: `web/` (54 files excluding `node_modules/`/`.next/`) — Next.js
  app, design system, 11 public pages + forgot-password, SEO files,
  `.env.example`, README, design-tokens doc.
- Modified: `.github/workflows/ci.yml` (branch + web job),
  `.gitignore` (Node artefacts, `web/.env.local`),
  `docs/phase2/06-deployment-plan.md` (M2 Vercel note §7).
- Unmodified: all Phase 1 Python code, APIs, models, migrations.
- `web/node_modules/` and `web/.next/` are gitignored; `package-lock.json`
  is committed (CI `npm ci` needs it).
