# TEST REPORT — officerpath-pdf-engine (Phase 1 + Phase 2)

**Date:** 2026-11-23 (PKT) · **Branch:** `officerpath-phase2-web` ·
**Runner:** pytest (local `.venv/`), ruff, mypy, `tsc`, `npm run build`,
`npm run lint`, Playwright (Chromium) + Lighthouse 13.6.0 — all local,
no deploy, no paid services.

This report was stale since M0 (22 tests) and is refreshed here through
Phase 2 M10. Milestone-by-milestone numbers come from the parent-verified
milestone reports in `docs/milestones/` (Phase 1) and
`docs/phase2/milestones/` (Phase 2); the M10 numbers below were measured
in this milestone's own runs.

## Final gate table (M10, 2026-11-23)

| Gate | Result | How |
|---|---|---|
| pytest (full suite) | **613 passed, 0 failed** (299.88 s) | `.venv/bin/python -m pytest -q`, re-run after the M10 code changes; 610 M9 baseline + 3 new async-dedup regression tests |
| ruff check | clean | `ruff check .` — 0 errors (one UP017 fixed in the new test file before the final run) |
| ruff format | clean | `ruff format --check .` — 229 files |
| mypy (CI gate) | SUCCESS | `mypy app/db app/pipeline app/storage` — 68 files, 0 issues |
| `tsc` | exit 0 | `npx tsc --noEmit` in `web/` |
| `npm run build` | PASS | Next.js 16.4.6, 34 pages / 37 user routes (unchanged from M9) |
| `npm run lint` | 0 problems | ESLint 9.39.5 |
| OpenAPI paths | 49 | `app.openapi()` — unchanged from M9 (the M10 dedup fix adds no route; it changes one endpoint's behaviour) |
| API regression sweep (M4–M9 + M10) | **17/17 steps PASS** | `~/workspace/m10-e2e/api_e2e.py` → `api-proof.json` |
| Browser E2E (acceptance files + walkthroughs) | **37/37 steps PASS** | `~/workspace/m10-e2e/browser_e2e.mjs` → `browser-proof.json` |
| Lighthouse (localhost harness) | Home 81 → 75, Features 80 → 79 (see §Lighthouse) | Lighthouse 13.6.0, same harness before/after the Providers split |

## Test-count growth (parent-verified per milestone)

| Milestone | pytest passed | Notes |
|---|---|---|
| Phase 1 M0 (audit) | 22 | skeleton only |
| Phase 1 M1 | 69 | schema + ingestion |
| Phase 1 M2 | 113 | PyMuPDF + classification |
| Phase 1 M3 | 203 | OCR + layout |
| Phase 1 M4 | 316 | extraction |
| Phase 1 M5 | 377 | answers |
| Phase 1 M6 | 448 | matching |
| Phase 1 M7 | 489 | async jobs + security |
| Phase 1 M8 (complete) | 492 | acceptance tests |
| Phase 2 M3 | 510 | auth + profiles (Alembic 0003) |
| Phase 2 M4 | 529 | dashboard + upload (Alembic 0004) |
| Phase 2 M5 | 536 | question bank (Alembic 0005) |
| Phase 2 M6 | 555 | test builder (Alembic 0006) |
| Phase 2 M7 | 575 | exam interface (Alembic 0007) |
| Phase 2 M8 | 593 | results/analytics (Alembic 0008) |
| Phase 2 M9 | 610 | admin + notifications + SEO (Alembic 0009) |
| Phase 2 M10 | **613** | async-dedup regression tests (3 new) |

## API regression sweep — M4–M9 proofs re-run in M10 (17/17)

Harness `~/workspace/m10-e2e/` (M9 bank copied, 91 live questions;
stub GoTrue :54399 + local engine :8001 + local web :3000).
`api-proof.json` holds the full step log.

| Area | Check | Result |
|---|---|---|
| M4 | Dashboard summary = real numbers (documents_total 4; jobs done 2 / failed 2, live-doc jobs only) | PASS |
| M5 | Bank total 91 = live bank; search `q=capital` → 1; 27 unknown in first 100 | PASS |
| M6 | Availability 64 available / 27 excluded unknown / 0 excluded no-options; test created (5q, 3600 s) | PASS |
| M7 | Answers before start → 409; session has `server_started_at` + `remaining_seconds` (3599) and NO answer key in any snapshot; submit 5.0/5.0 = 100.0%; double submit same result_id | PASS |
| M8 | Result == stored `test_results` row exactly (5.0/5.0/100.0, 5/0/0/0); retry keeps snapshots (same question_text + correct_index); history newest-first (total 13→14 across runs) | PASS |
| M9 | Student → 404 `not_found` on all 6 admin routes; admin overview real (users 1, documents 8, jobs 8, questions 91, tests 30, results 14, errors 2, notifications 16 — counts grow as the sweep itself creates rows); notifications total 14, unread 11; security headers exact; CORS disallowed origin → no ACAO | PASS |
| M10 | Async-jobs re-submit of identical CA40 bytes → **200, `idempotent_replay: true`**, same job_id `30b3992a-…`, status `done`, exactly 1 live document for (user, hash) | PASS |
| Health | `/health` → **503 by design** in this harness (GoTrue-only stub, no PostgREST → Supabase probe unreachable); body honest: status `degraded`, database `ok`, `ocr_tesseract: available`, disk `ok` | PASS (body asserted, not the code) |

## Browser E2E — acceptance files through the WEB UI (37/37)

Harness `~/workspace/m10-e2e/browser_e2e.mjs` (Playwright Chromium).
Each file was chosen in the real file picker, uploaded with the real
button, tracked live by the JobTracker, and the counts shown on the
document detail page were compared with the engine's stored rows.
`browser-proof.json` holds the full step log.

| File | UI counts (questions / answered / pending) | Stored rows | Verdict |
|---|---|---|---|
| `ppsc_paper_66.pdf` (fresh parse after soft-deleting the bank copy) | **41 / 41 / 27** | 68 `extracted_questions` rows for the new document — exactly M5's 68 (M6's run had only recovered 51 after a page-3 Tesseract timeout) | PASS — UI == stored |
| `table-computer-q67-81-resent-20261121.jpg` | **0 / 0 / 2** | — | PASS — matches Phase 1 acceptance (0q / 2 pending) |
| `paper60-photo.jpg` | **4 / 4 / 9** | — | PASS — matches Phase 1 acceptance (4q / 4ans / 9 pending) |

Walkthroughs (all 0 px horizontal overflow, every control real or
labelled unavailable): desktop — all 9 dashboard pages
(`/dashboard`, `/upload`, `/documents`, `/questions`, `/tests`,
`/results`, `/mistakes`, `/notifications`, `/profile`) + all 6 admin
pages (`/admin`, `/users`, `/documents`, `/jobs`, `/errors`,
`/questions`); student `/admin` redirects to `/dashboard` in the UI.
Mobile 360 px — 7 dashboard + `/admin`, `/admin/users`,
`/dashboard/notifications`, 0 px overflow.

## Lighthouse (localhost harness — NOT production numbers)

Lighthouse 13.6.0, same harness, same pages, before/after the M10
Providers split (TanStack Query chunk out of the root layout into the
dashboard + admin layouts only). The split removes the 16 KB raw
TanStack chunk from public pages — verified directly: the home HTML
references the chunk 0 times after the change.

| Page | Run | Perf | A11y | BP | SEO | TBT | LCP | CLS | JS bootup |
|---|---|---|---|---|---|---|---|---|---|
| Home | M9 (VM-contended) | 73 | 96 | 100 | 100 | 1,790 ms | — | — | — |
| Home | M10 before | 81 | 96 | 100 | 100 | 499 ms | 3.1 s | 0 | 1,246 ms |
| Home | M10 after (run 1) | 68 | 95 | 96* | 100 | 373 ms | 0.8 s | 0.688 | 925 ms |
| Home | M10 after (run 2) | 75 | 96 | 100 | 100 | 778 ms | 3.1 s | 0 | 1,350 ms |
| Features | M9 (VM-contended) | 60 | 94 | 100 | 100 | — | — | — | — |
| Features | M10 before | 80 | 94 | 100 | 100 | 440 ms | 3.5 s | 0 | 769 ms |
| Features | M10 after (run 1) | 75 | 94 | 100 | 100 | 143 ms | 0.8 s | 0.688 | 554 ms |
| Features | M10 after (run 2) | 79 | 94 | 100 | 100 | 475 ms | 3.6 s | 0 | 1,018 ms |

\* Home after-1 BP 96 was the stale-server artifact (see below) —
that run is discarded for Best Practices, not for the other metrics.

**Honest reading:** the measured Performance effect is inside this
harness's noise floor. Identical builds swing ±300 ms TBT and ±2.3 s
LCP between back-to-back runs (TBT 373 → 778 ms on the same build;
LCP 0.8 → 3.1 s), and the same M9 code measured 73 in M9 vs 81 here.
The CLS 0.688 in both after-1 runs is a flake: it reproduced as 0 on
both repeat runs, with no attributed source nodes, and the change
touches no visual element. Median after vs before — Home 81 → 75,
Features 80 → 79 — is no reliable gain and no regression; the chunk
removal is real but its effect is below what this throttled VM can
measure. Production numbers can only come from the deployed site.

**Invalid run discarded:** the first after-runs were measured against
the OLD server — `kill $(cat web.pid)` killed the `npx` wrapper, not
the `next-server` child, so the restart failed with EADDRINUSE and
the old build kept serving while the new `.next` had replaced its
chunks (500 + MIME-type console errors). The server was restarted
properly (real `next-server` pid) and both after-runs re-measured.
Lesson: always verify the serving pid + chunk list after a restart.

## Defects found and fixed in M10

| # | Defect | Fix | Test |
|---|---|---|---|
| 1 | Async-jobs re-submit 500 (M9 §6.5, pre-existing M7 edge): identical bytes to `POST /api/v1/async-jobs/parse` → `IntegrityError` at `async_jobs.py:123` | Idempotent replay: return the original job, 200 + `idempotent_replay: true`; soft-deleted docs never block; `IntegrityError` race guard; `idempotent_replay` field added to `AsyncJobCreatedResponse` | 3 regression tests in `app/tests/test_worker_jobs.py` (replay / replay-after-delete / other-user) — 13/13 in file, 613/0 full suite |
| 2 | `render.yaml` branch still `officerpath-phase1-engine` | One-line fix → `officerpath-phase2-web` | Verified by grep |
| 3 | Root layout loaded TanStack Query on every public page | Providers split into dashboard + admin layouts only | Lighthouse before/after (above); HTML chunk check |

## Environment incidents in M10 (not code failures)

- **Runtime restart (2nd in M10)** wiped system tesseract a 5th time
  and interrupted the harness setup mid-build. The cell's own
  os-intent replay restored tesseract 5.3.4 (eng/osd/urd/ara) after
  its `apt-get update` finished (~14 min at ~87 kB/s); the harness
  setup was re-run cleanly afterwards.
- **Disk quota (EDQUOT, errno 122):** the overlay upper filled up —
  a 1 MB write failed even though `df` showed 47 G free. Cause: the
  npm cache (`~/.npm` 2.7 G) plus stale npx installs. Fixed by
  `npm cache clean --force` + deleting one failed npx extract
  (2.7 G → 883 M); writes worked again. Lighthouse's first npx
  download and its JSON output both failed with the same -122 before
  the cleanup. The working Lighthouse 13.6.0 is M9's npx install
  (`~/.npm/_npx/0f94ee7615faf582/…/cli/index.js` — note: the entry
  is `cli/index.js`, not `cli/bin.js`, which exits silently).
- **Harness script bugs (mine, fixed):** `api_e2e.py` assumed
  `search=` (the student bank uses `q=`), assumed the availability
  endpoint takes no params (`source_type` is required), compared
  the summary's job count against all jobs instead of live-doc jobs,
  compared UUIDs dashed instead of hex, counted soft-deleted CA40
  rows as live, and expected `/health` 200 in a GoTrue-only-stub
  harness (designed 503 — see the health row above).
  `browser_e2e.mjs` read the summary from `GET /api/v1/jobs/{id}`
  (which does not return `result_summary` — it lives on the
  document detail), looked for a "Pending" label (the UI says
  "Needs review"), and set the file input before hydration (the
  change event was dropped). All fixed in the scripts; the product
  was never at fault in any of these.

## What was NOT tested live (honest gaps — unchanged from M9)

- **`npm audit`** — NOT run (VM registry returns 403
  `policy_denied`). Owner step on his machine; not clean, just not run.
- **iPhone Safari / real device** — unverified (Playwright Chromium
  360 px only).
- **Urdu preservation** — not E2E-proven (no Urdu fixture in the
  M10 bank runs; the Urdu OCR fixture work is Phase 1 M3/M4).
- **Inferred-answer flag + Q&A-pair card rendering** — unit-test
  only (0 inferred answers in the fixtures; 17 Q&A pairs is a
  report-summary count, never stored rows).
- **Live Supabase** — unchanged: migrations 016 (bucket) + 017
  (partial index) NOT applied; the M3 confirm→login→profile loop
  is still not live-proven; the unconfirmed M3 test user
  `officerpath.m3.test@gmail.com` still exists.
- **Docker image build** — no Docker on this VM; Dockerfile is
  config-only, never built.
- **GitHub CI** — never run (no push; the GitHub App is not
  installed on the repo yet).
- **Live phone verification (STOP CONDITION)** — the three
  acceptance files are proven through the local web UI here, but
  NOT on the owner's phone against a deployed build. No
  Phase-2-complete claim until that happens.
- **Production Lighthouse / performance** — localhost-harness
  numbers only (see the Lighthouse section).
