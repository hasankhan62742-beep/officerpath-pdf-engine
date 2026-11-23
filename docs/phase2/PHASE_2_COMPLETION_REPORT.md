# Phase 2 Completion Report — OfficerPath AI Web Application

**Date:** 2026-11-23 (PKT) · **Branch:** `officerpath-phase2-web` ·
**Status:** Phase 2 is COMPLETE as a local build — all ten milestones
parent-verified, all gates green. **Nothing is deployed, nothing is
pushed, no paid service was used.** The remaining work is owner steps
(§8) — above all the live phone verification (the STOP CONDITION).

## 1. What Phase 2 set out to do

Build a Next.js web application on top of the Phase 1 Python/FastAPI
engine (never rebuilding the engine, never migrating the backend to
Node.js), per the user's master prompt of 2026-11-22 §27:

- 11 public pages (Home, About, Features, How It Works, Exam
  Preparation, Pricing, Contact, Login, Register, Privacy Policy,
  Terms) — real content, no invented testimonials, student numbers,
  success rates, or partnerships; no prices invented (free during
  Phase 2, paid plans are Phase 3).
- Real Supabase Auth (email verification real, no fake OTP), real
  profiles, real dashboard numbers from real database records.
- Upload → engine extraction → question bank → test builder → exam
  interface (server-clock timer) → results/analytics → mistakes
  practice → admin foundation + notifications + SEO.
- Marking rules configurable and stored with the test session
  (default PPSC-style: correct +1, incorrect −0.25, unattempted 0),
  calculated on the backend only; past tests preserve their
  question/options/answer-key snapshot and marking config even if
  the bank is later edited.
- Truth rules from Phase 1 carried through the UI: `correct_index =
  -1` renders "Answer: unknown." with zero options highlighted;
  inferred answers carry a visible "Inferred" flag; Q&A pairs are
  shown as Q&A, never forced into 4 options; no duplicates in a test
  unless the user explicitly chooses repetition; answers never
  cross-apply between papers.
- No payments/subscriptions in Phase 2 (Phase 3). Every visible
  action performs a real function or is clearly labelled unavailable.

## 2. What each milestone delivered (all parent-verified)

| M | Scope | Commit | pytest | OpenAPI | Headline proof |
|---|---|---|---|---|---|
| M1 | Audit + architecture (docs only) | `dee2f06` | — (no code) | 17 | Dual job stores + `done` vs `completed` found; 12 API GAPs assigned; 7 docs (§32) |
| M2 | Frontend foundation + design system | `0add038` | — | 17 | Next.js 16.4.6, 15 static routes, 14/14 HTTP 200, 17 components, 0 overflow at 360 px |
| M3 | Auth + profiles | `4fae711` | 510/0 | 17 | Real Supabase Auth; **correction: migration 015 tables ARE live, only the bucket is missing**; ADR-011 (engine DB single store); confirm→login→profile loop NOT live-proven (owner step) |
| M4 | Dashboard + upload | `12568ba` | 529/0 | 21 | GAP-2 (documents API + bucket download); CA40 40/40 in ~3 s; real dashboard numbers |
| M5 | Extraction results + question bank | `61a121c` | 536/0 | 27 | GAP-3 + GAP-4; bank 108 rows (81 answered / 27 unknown); correction UI round-trips; `.env.local` restored by parent |
| M6 | Test builder | `1f23888` | 555/0 | 31 | GAP-5; snapshots byte-identical after a bank correction (sha256); scoring 9.5/15.0 hand-checked; **real bug: delete→re-upload 500 → partial unique index (migration 017 written, NOT applied)** |
| M7 | Exam interface | `2342c4a` | 575/0 | 36 | GAP-6; server-clock timer proven (browser clock +1 h → timer decayed exactly 10 s); submit 4.5/9.0 = 50.0% hand-checked; double submit idempotent |
| M8 | Results + analytics | `094b6b6` | 593/0 | 41 | GAP-7 + GAP-8; result == stored row exactly (3.25/9.0 = 36.11%); retry snapshots identical; mistakes = only incorrect questions |
| M9 | Admin + security + SEO | `7abb28f` | 610/0 | 49 | GAP-9 + GAP-10; student → 404 on all 6 admin routes; notifications 8 rows; **real bugs: exam session leaked the answer key (fixed), admin counted soft-deleted docs (fixed)**; Lighthouse Home 73 / Features 60 (VM-contended) |
| M10 | Complete QA + deployment readiness | `c4715fc` | **613/0** | 49 | Async-dedup 500 fixed (200 + `idempotent_replay`); Providers split; acceptance files via the WEB UI; runbooks + checklists; docs refreshed |

## 3. Final measured results (M10, local harness — NOT production)

### Gates (M10, exact numbers)

| Gate | Result |
|---|---|
| pytest (full suite) | **613 passed, 0 failed** (299.88 s) |
| ruff check / format | clean / clean (229 files) |
| mypy (CI gate) | SUCCESS (68 files) |
| `tsc` | exit 0 |
| `npm run build` | PASS — 34 pages / 37 user routes |
| `npm run lint` | 0 problems |
| OpenAPI paths | 49 |
| API regression sweep (M4–M9 + M10) | 17/17 steps PASS |
| Browser E2E (acceptance + walkthroughs) | 37/37 steps PASS |

### The three acceptance files — through the WEB UI (M10)

| File | UI counts (questions / answered / pending) | Stored |
|---|---|---|
| `ppsc_paper_66.pdf` (fresh parse) | **41 / 41 / 27** | 68 `extracted_questions` rows — exactly M5's 68 |
| `table-computer-q67-81-resent-20261121.jpg` | **0 / 0 / 2** | matches Phase 1 acceptance |
| `paper60-photo.jpg` | **4 / 4 / 9** | matches Phase 1 acceptance |

Walkthroughs: desktop — all 9 dashboard + all 6 admin pages, 0 px
overflow; mobile 360 px — 7 dashboard + 3 admin/notification pages,
0 px overflow; student `/admin` → `/dashboard` in the UI.

### Regression sweep (M10, per area — all PASS)

Dashboard summary real numbers · question bank (91 live, search
`capital` → 1) · test availability 64/27/0 · exam session
server-clock + no answer key · submit 5.0/5.0 = 100.0%, double
submit idempotent · result == stored row exactly · retry keeps
snapshots · history newest-first · admin 404s · notifications ·
security headers + CORS · async-dedup replay 200 +
`idempotent_replay: true` · `/health` 503-by-design in the
GoTrue-only-stub harness (body honest: `degraded`, database `ok`).

### Lighthouse (localhost harness — NOT production numbers)

| Page | M9 (contended) | M10 before | M10 after (median of 2 runs) |
|---|---|---|---|
| Home | 73/96/100/100, TBT 1,790 ms | 81/96/100/100, TBT 499 ms | 75/96/100/100, TBT 373–778 ms |
| Features | 60/94/100/100 | 80/94/100/100, TBT 440 ms | 79/94/100/100, TBT 143–475 ms |

The Providers split removes the 16 KB raw TanStack chunk from public
pages (verified: 0 references in the home HTML), but the measured
Performance effect is inside this harness's noise floor (identical
builds swing ±300 ms TBT and ±2.3 s LCP run to run). No reliable gain
demonstrated, no regression. Production numbers can only come from
the deployed site.

### Accuracy (inherited from Phase 1, reproduced in Phase 2)

- PPSC-66: 41/100 numbers recovered by single-path OCR (OCR
  limitation, not extraction failure; Q1–9 clipped at the page edge
  → ceiling ≤91/100; union of 3 PSM paths = 59 at 2–3× cost,
  optional mode only, ADR-010).
- Trailing-key answers: 1.0 on the ideal path; live PPSC-66 OCR
  0.9744/0.38/0.5468.
- TestPoint FP 248 → 28 (Q precision 0.98, F1 0.9899, recall 1.0).
- Key-region location: 1.0/0.84/0.913 (84 TP, 0 FP).
- Calibration ECE 0.0003 (below-1.0 buckets UNVERIFIED, no samples).

### Latency + memory (VM numbers, not production)

- CA40 upload → done ≈3–6 s; PPSC-66 single-path parse 224 s in
  the M10 UI run (146–481 s across runs under VM contention; the
  900 s per-page Tesseract timeout cost page 3 once in M6).
- Render-free fit MARGINAL: single-parse tree peak 398–461 MB vs
  512 MB (47 MB headroom); long-lived worker RSS accumulates
  (73 MB baseline → 369 MB after one parse) — no restart policy
  wired; `worker_stage_timeout_seconds` 600 s must be raised for
  Render free (render.yaml sets 1800).

## 4. Architecture as built

- **Frontend:** Next.js 16.4.6 (App Router, Turbopack) + React
  19.3.0 + TypeScript 5.9.3 (strict) + Tailwind CSS 4.3.3, in
  `web/` at the repo root (no `src/`; tokens in CSS `@theme`).
  TanStack Query 5.108.2 + React Hook Form 7.92.0 + Zod 4.6.7.
  34 pages / 37 user routes. `proxy.ts` guards `/dashboard/*`
  (Next 16 deprecates `middleware`). PWA manifest + icons, NO
  service worker/offline (not claimed). SEO: canonical + OG +
  JSON-LD Organization/WebSite on home; noindex on
  `/dashboard/*`, `/admin/*`, auth pages; robots.txt disallows
  `/dashboard/` `/admin/` `/auth/` `/api/`; sitemap lists 11
  public pages.
- **Engine (unchanged, Phase 1):** Python FastAPI, SQLAlchemy +
  Alembic 0001–0009, PyMuPDF (AGPLv3 — see §7), Tesseract +
  PaddleOCR (VPS-only), in-process worker + CLI runner, JSON logs,
  `/health` (honest 200/503) + `/metrics`.
- **Auth:** Supabase Auth (`@supabase/ssr` 0.12.7) with the
  real project `officerpath-ai` (`gliebuyyjguxrwdfuakz`, Singapore,
  Free plan). Admin = `app_metadata.is_admin` from the VERIFIED
  JWT only; the engine's `require_admin` returns 404 for
  non-admins; the frontend guard is UX only.
- **Data:** engine DB (SQLAlchemy) is the single store (ADR-011);
  PostgREST repos deleted; vocabulary unified on `done`. 17 engine
  tables + `student_profiles` + `subjects`/`topics` + test
  templates/sessions/snapshots + `student_responses`/`test_results`
  + collections + notifications. Supabase migration 015 tables are
  LIVE; 016 (bucket) + 017 (partial index) are written, NOT applied.
- **Hosting (ADR-001):** Stage 1 Render free (engine) + Vercel
  free (frontend, recommended); Stage 2 Hostinger KVM 1 VPS when
  payment is possible. GCP billing PAUSED — never resumed.
- **OCR (ADR-002/005/006):** hybrid — digital text first,
  Gemini-advisory when a server key exists (disabled-by-default;
  no key provisioned; no Gemini API call has ever been made),
  Tesseract/PaddleOCR fallback. PaddleOCR cannot run on Render
  free (peak RSS 1.8–3.7 GB).

## 5. Decisions (ADR-001 … ADR-011, one line each)

| ADR | Decision |
|---|---|
| ADR-001 | Hosting: Render free Stage 1, Hostinger KVM 1 Stage 2; GCP paused |
| ADR-002 | OCR: hybrid digital-first, Gemini-advisory (server key only, deferred) |
| ADR-003 | Persistence: SQLAlchemy + Alembic for engine tables; supabase-py for Auth + documents/jobs |
| ADR-004 | PyMuPDF is AGPLv3 — accepted while the repo is public; replace/license before closed-source distribution |
| ADR-005 | PaddleOCR cannot run on Render free (RSS 1.8–3.7 GB) — VPS-only |
| ADR-006 | Deployment-aware OCR routing (`DEPLOYMENT_PROFILE=render-free`, `PADDLEOCR_ENABLED=false`) |
| ADR-007 | Pending-promotion rule: key/inline/style, conf ≥0.9, no conflicts, never inferred |
| ADR-008 | `select_psm` always PSM 3 (no M2 quality metric separates p5) |
| ADR-009 | In-process background worker (atomic claim, per-stage timeout, cancel, retry) |
| ADR-010 | Union merge kept as optional mode only (40→53 answered numbers at 2.8–3.1× time) |
| ADR-011 | Engine DB single store; PostgREST repos deleted; vocabulary unified on `done` |

## 6. What Phase 2 built, by area (final state)

| Area | State |
|---|---|
| Public pages (11) | Real, complete; Pricing invents no prices; Contact validates locally and states submissions are not sent anywhere yet |
| Auth | Login / register / forgot / reset real; `/auth/callback` exchanges code + creates engine profile; guard 307s; header session state + logout; profile reads/writes `GET/POST/PATCH /api/v1/me` |
| Dashboard | Real summary, real document list/detail (filter, pagination, View/Retry/Cancel/Delete), real upload (drag-drop + picker, single/batch, JobTracker polling 5 s → 15 s) |
| Question bank | Search/filter/paginate, detail + evidence trail + corrections with audit history, manual subject assignment only (engine never classifies) |
| Test builder | All/documents/subjects/explicit modes, counts 1–200, PPSC default pre-filled + explained, repetition/unknown toggles, availability preview with 5-question sample; snapshots byte-identical after bank corrections |
| Exam | Server-clock timer (no local tick), palette, mark-for-review, clear response (row kept, `selected_index = NULL`), autosave + `localStorage` draft, submit dialog with honest counts, unknown snapshots options-disabled + "not scored" |
| Results | Score/%, counts, time, subject/topic breakdowns, weak/strong, review with bookmarks, history newest-first, compare-over-time (≥2 attempts), retry, from-mistakes (only incorrect questions) |
| Notifications | Per-user only, written by real flows in the same transaction; list + All/Unread filter + mark-read + live unread badge |
| Admin | 6 pages + server guard; 6 endpoints, all real rows, paginated; users list has NO email (engine DB stores none) |
| SEO / PWA | As §4; manifest + icons, no service worker |

## 7. Honest limitations — what Phase 2 does NOT do

- **Not deployed, not pushed.** No Render deploy, no Vercel
  deploy, no GitHub push (the GitHub App is not installed on
  `hasankhan62742-beep/officerpath-pdf-engine` yet).
- **Not live-verified against real Supabase.** Migrations 016 +
  017 unapplied; the M3 confirm→login→profile loop is not
  live-proven; the unconfirmed M3 test user still exists; the
  bucket download path is local-only proven.
- **STOP CONDITION unmet:** no fix is "done" until the owner's
  phone proves it on the three acceptance files against a deployed
  build. The files are proven here through the local web UI only.
- **PyMuPDF is AGPLv3** (ADR-004) — must be replaced or licensed
  before closed-source distribution.
- **Render-free fit is MARGINAL** (47 MB headroom); no worker
  restart policy; keep-alive DEFERRED; Docker never built (no
  Docker on VM); GitHub CI never run.
- **`npm audit` not run** (VM registry 403 `policy_denied`).
- **iPhone Safari / real device unverified;** Lighthouse is
  localhost-harness only; Urdu preservation not E2E-proven;
  inferred-flag + Q&A-pair rendering unit-test-only; invalid-token
  → 401 unit-test-only; no email in the admin users list.
- **Payments/subscriptions are Phase 3** — not built, not in
  Phase 2.
- **Gemini server key deferred** by the user ("baad ki bat") — the
  advisory adapter is disabled; no Gemini API call has ever been
  made.
- **Flutter app is not the primary frontend any more** and must not
  dictate the web architecture; the v2.0.5 "Server parse" toggle is
  prepared only (3 files, uncommitted, `flutter analyze` never run
  — no SDK on VM), and the server URL it points at is not deployed
  yet.

## 8. Owner steps still outstanding (in order — nothing here is code)

1. **GitHub App install** — add `officerpath-pdf-engine` at
   https://github.com/apps/meta-muse-ai/installations/new, then
   push branch `officerpath-phase2-web` (local head: M10 commit;
   CI has never run on GitHub).
2. **Apply Supabase migrations 016 + 017** — exact steps in
   `docs/phase2/migration-runbook.md` (Dashboard SQL Editor;
   verification queries included). Until then: the `pdf-documents`
   bucket is missing and live delete → re-upload of the same file
   still 500s.
3. **Apply the Alembic chain on the deploy target** —
   `alembic upgrade head` (0001–0009) with `DATABASE_URL`, per the
   runbook (rollback in `docs/phase2/rollback-runbook.md`).
4. **Render deploy (engine)** — per `docs/deploy-render.md` and
   `docs/phase2/deployment-checklists.md` checklist A (branch is
   now `officerpath-phase2-web` in `render.yaml`).
5. **Vercel deploy (frontend)** — per checklist B; confirm the
   canonical domain (placeholder `https://officerpath.ai` is
   unconfirmed) and set the env vars (`NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`,
   `NEXT_PUBLIC_SITE_URL`).
6. **Confirm Redirect URLs allowlist** includes
   `http://localhost:3000/auth/callback` (Dashboard →
   Authentication → URL Configuration) — not conclusively proven.
7. **Delete the unconfirmed M3 test user**
   `officerpath.m3.test@gmail.com` (Dashboard → Authentication →
   Users; cannot be deleted from the VM — no service key).
8. **Live phone verification — the STOP CONDITION:** PPSC-66 PDF,
   computer table photo, Paper 60 photo on his phone against the
   deployed build. No Phase-2-complete claim until this passes.
9. **`npm audit` on the owner's machine** (VM registry 403).
10. **`flutter analyze`** on the toggle files (owner step, no SDK
    on VM).
11. **Gemini server key** — deferred by the user; do not keep
    asking for it.

## 9. Handover — where everything lives

| Item | Location |
|---|---|
| Engine + web code | `~/workspace/officerpath-pdf-engine/`, branch `officerpath-phase2-web` (local only) |
| Phase 2 docs (M1) | `docs/phase2/01-repository-findings.md` … `07-milestone-execution-plan.md`, `README.md` |
| Milestone reports | `docs/phase2/milestones/MILESTONE_2_REPORT.md` … `MILESTONE_10_REPORT.md` |
| Runbooks + checklists | `docs/phase2/migration-runbook.md`, `docs/phase2/rollback-runbook.md`, `docs/phase2/deployment-checklists.md` |
| This report | `docs/phase2/PHASE_2_COMPLETION_REPORT.md` |
| API reference | `docs/API.md` (49 paths) |
| Test report | `TEST_REPORT.md` (613/0 + E2E proofs) |
| Changelog | `CHANGELOG.md` (through [2.10.0] M10) |
| Deploy guides | `docs/deploy-render.md`, `docs/phase2/06-deployment-plan.md` |
| E2E harnesses (never committed) | `~/workspace/m5-e2e/` … `~/workspace/m10-e2e/` (M10: `api-proof.json`, `browser-proof.json`, Lighthouse JSONs, `engine.db`) |
| Fixtures (originals never modified) | `~/workspace/officerpath-ai/test-fixtures/ppsc66/` |
| Flutter toggle (prepared only) | `~/workspace/officerpath-ai/` — `lib/services/server_parse_service.dart`, `lib/services/pdf_import_service.dart`, `lib/screens/ai_settings_screen.dart` |
