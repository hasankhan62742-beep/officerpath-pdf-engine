# Phase 2 M1 — Milestone Execution Plan (M2–M10)

**Date:** 2026-11-22
**Basis:** Phase 2 prompt §27 (M1–M10) + the findings in docs 01–06.
**Rhythm (as in Phase 1):** one milestone per delegated build →
parent-verified (tests + gates re-run personally before anything is
called done) → report in Roman Urdu → owner go-ahead for the next
milestone. Local only, no push, no deploy, no paid services without
owner approval.

## M2 — Frontend Foundation and Design System

- **Scope:** `web/` scaffold (Next.js App Router + React + TS +
  Tailwind, strict TS, ESLint/Prettier), design tokens (palette
  orange/green/blue/purple, typography, spacing), reusable `ui/`
  primitives, responsive layouts + navigation, all 11 public pages
  with real copy (no invented testimonials/numbers/partnerships),
  SEO basics (titles, meta, sitemap, robots.txt), CI `web` job,
  `.github/workflows/ci.yml` branch list gains
  `officerpath-phase2-web`, CORS middleware on the backend (first
  browser client), frontend hosting choice confirmed with the owner
  (Vercel free recommended — doc 06 §3).
- **Depends on:** M1 (this doc set).
- **Acceptance:** `npm run build` passes; `tsc --noEmit` clean;
  public pages render on mobile + desktop viewports (Playwright
  screenshots reviewed, not claimed); no non-functional controls;
  CI runs on the Phase 2 branch.
- **Explicitly NOT in M2:** auth, dashboard, uploads, any API
  integration beyond a `/health` ping. No payment page content that
  implies payments exist.

## M3 — Authentication and Student Profiles

- **Scope:** Supabase Auth integration (register, email verification
  — real flow, login, logout, password reset, session persistence,
  protected routes, profile/settings), `student_profiles` table
  (Alembic 0003), `GET/PATCH /api/v1/me` (GAP-1), **the dual-store
  unification decision** (doc 03 §5 — Option A recommended, decided
  here with an ADR), live Supabase state re-verified (tables, RLS,
  bucket, auth settings — the M1 UNVERIFIED item).
- **Depends on:** M2 (layouts, guards, API client).
- **Acceptance:** register → verify → login → dashboard → logout
  works end-to-end against the real Supabase project (test account,
  not a mock); cross-user profile access → 404; unverified users
  cannot reach the app shell; tests for registration, verification,
  login, logout, protected routes, authorisation.
- **Explicitly NOT in M3:** payments, premium, admin roles, document
  upload.

## M4 — Dashboard and Document Upload

- **Scope:** student dashboard (real DB values only, empty states),
  My Documents + document listing (GAP-2), drag-and-drop upload
  (PDF/JPG/PNG, single + batch ≤ 20), engine integration via
  `upload` / `parse` / `parse-image` / `async-jobs` (GAP-11
  implemented), job polling UI (5 s → 15 s backoff), cancel/retry,
  processing status + errors, document detail page.
- **Depends on:** M3 (auth, unified jobs). **Blocks:** M5.
- **Acceptance:** upload a real PDF and a real photo through the web
  UI against the local backend; job completes; counts shown are the
  engine's counts; oversize/encrypted/bad files show the engine's
  422 reason; batch partial failure handled; mobile upload usable.
- **Explicitly NOT in M4:** question bank UI, test builder, exam.

## M5 — Extraction Results and Question Bank

- **Scope:** processing progress + results interface, question list
  with search/filter (GAP-3), question detail with evidence trail and
  answer-status labels (Verified / Detected / Needs Review / Unknown /
  Conflicting), review queue + corrections (existing endpoints),
  subjects/topics (GAP-4, Alembic 0004, seed 13 subjects),
  `question_subjects` assignment, question-asset serving (GAP-12,
  signed owner-checked URLs), shared-question policy decision
  (recorded).
- **Depends on:** M4 (documents + jobs).
- **Acceptance:** PPSC-66 parse results render with evidence trails;
  UNKNOWN answers render as unknown (never green, never correct);
  a correction is audited and never overwrites the original; filters
  work on real data; uncategorised questions stay uncategorised.
- **Explicitly NOT in M5:** test builder, exam, results analytics.

## M6 — Test Builder

- **Scope:** `test_templates`, `marking_configs` (PPSC default
  +1/−0.25/0 seeded), `test_sessions`, `test_question_snapshots`
  (Alembic 0005), test creation UI (25/50/100/150/200, sources:
  all/documents/subjects/topics/bookmarks/unattempted/incorrect/
  mixed), availability check (fewer questions → clear explanation,
  never a short test), no duplicates unless repetition mode is
  explicitly chosen, random selection with a saved record,
  snapshot-freeze rule enforced.
- **Depends on:** M5 (question bank + subjects).
- **Acceptance:** build a 25-question test from real bank questions;
  the saved test's snapshots do not change when the bank is edited
  (test proves it); requesting 100 with 40 available explains the
  limit; duplicate prevention tested.
- **Explicitly NOT in M6:** exam interface, marking, results.

## M7 — Examination Interface

- **Scope:** exam page (palette, prev/next, 4-option layout, mark
  for review, clear response, answered/unanswered indicators,
  progress), server-aware timer (`server_started_at`), periodic
  answer persistence (`student_responses`, upsert), submit
  confirmation, duplicate-submission prevention, network-interruption
  handling, backend marking (GAP-6, `test_results` written at
  submit), mobile-first exam layout.
- **Depends on:** M6 (sessions + snapshots).
- **Acceptance:** complete a timed test in a mobile viewport;
  refresh mid-test loses nothing; submit computes marks server-side
  (+1/−0.25/0) and matches a hand-checked calculation; double-submit
  creates one result; timer survives a browser-clock change.
- **Explicitly NOT in M7:** analytics, history, mistake notebook.

## M8 — Results and Student Analytics

- **Scope:** results page (score, %, correct/incorrect/unattempted,
  time, subject/topic breakdown, weak/strong areas, history),
  question review (correct/incorrect/unattempted + evidence, no
  fabricated explanations), test history (retry, new-from-mistakes,
  compare over time), mistake notebook + bookmarks (GAP-8,
  `student_question_collections`, Alembic 0004 follow-up if not in
  M5), notifications table (GAP-9, written in M9 — M8 only consumes
  the mistake/bookmark flow).
- **Depends on:** M7 (results exist to display).
- **Acceptance:** results match the stored `test_results` row exactly;
  subject breakdowns come from saved attempts; a retried test keeps
  its original snapshot; mistake practice creates a new session.
- **Explicitly NOT in M8:** admin, SEO polish, deployment.

## M9 — Admin Foundation, Security and SEO

- **Scope:** admin role mechanism decided + enforced backend-side
  (doc 05 §4), admin dashboard + user/document/job listings + error
  monitoring + question review access (GAP-10), security hardening
  pass (headers, CORS final, dependency audit, cross-user tests),
  public-page SEO completion (canonical, Open Graph, structured data,
  noindex on private routes), PWA readiness evaluation (manifest +
  icons; public shell only — not a blocker), notifications in-app
  (GAP-9, `notifications` table, Alembic 0006).
- **Depends on:** M8 (everything exists to administer).
- **Acceptance:** non-admin → 404 on every admin route (URL + API);
  admin sees real users/documents/jobs; private routes carry noindex;
  security tests (cross-user, invalid tokens, unauthorised calls)
  pass; Lighthouse/SEO spot-check on public pages.
- **Explicitly NOT in M9:** payment/subscription management (Phase 3),
  email notifications (provider-gated, future).

## M10 — Complete QA and Deployment Readiness

- **Scope:** full test suite (unit + integration + Playwright E2E
  across auth/documents/questions/tests/security per prompt §26),
  defect fixing, production builds verified (frontend + backend),
  deployment documentation finalised (doc 06 executed as checklists,
  not as an actual deploy), `render.yaml` branch updated,
  migration runbook, rollback runbook, Phase 2 completion report.
- **Depends on:** M2–M9 (everything).
- **Acceptance:** the full gate (pytest + ruff + mypy + `tsc` +
  `npm run build` + Playwright) passes; the three acceptance files
  parse end-to-end through the web UI against the local backend;
  mobile + desktop walkthroughs pass; the completion report lists
  every remaining owner step honestly. **No deploy happens in M10
  without the owner's explicit approval.**
- **Explicitly NOT in M10:** the deploy itself, any paid service,
  Phase 3 (payments/subscriptions).

## Cross-cutting rules (all milestones)

- **Never break an existing API contract.** New endpoints are additive
  (`/api/v1/*` under the same auth/error conventions). If a contract
  must change, it gets an ADR and a version note first.
- **Never fabricate.** No fake data in production paths, no invented
  testimonials/numbers, no guessed answers, no fake OTP, no email
  claimed sent without provider confirmation.
- **Every milestone ships tests** for what it built (unit + integration;
  E2E where the prompt §26 requires it). A milestone with no tests for
  its new surface is not done.
- **Mobile is verified every milestone**, not only at M10.
- **Docs are updated in the milestone that changes them** (API.md for
  new endpoints, deploy guide for new env vars, this plan if scope
  moves).
- **Owner steps stay owner steps:** GitHub App install + push,
  migration 015 live apply, Render deploy, Gemini key, `flutter
  analyze`. No milestone assumes them done.
