# OfficerPath AI — Phase 2, Milestone 7 Report: Examination Interface

**Status: COMPLETE — E2E + browser proof landed (see §3). Awaiting parent verification.**
**Branch:** `officerpath-phase2-web` (local only, no push, no deploy, no paid services)
**Date:** 2026-11-22 (PKT)
**Parent verification:** PENDING

## 1. What was built

### Engine — exam API (GAP-6 DONE)
- Models (`app/db/models.py`): `StudentResponse`, `TestResult`.
- Alembic **0007** (`alembic/versions/0007_m7_exam.py`): creates `student_responses` + `test_results` exactly per doc 03 §2.5, plus ONE recorded addition — `test_results.unknown_count` (see §1.1). Downgrade refuses while either table holds rows.
- Schemas (`app/schemas/exam.py`) + service (`app/services/exam.py`) + routes (added to `app/api/v1/tests.py`, same router):
  - `POST /api/v1/tests/{id}/start` (200)
  - `GET /api/v1/tests/{id}/session` (snapshots + saved responses + server remaining time)
  - `POST /api/v1/tests/{id}/answers` (upsert, one or batched)
  - `POST /api/v1/tests/{id}/submit` (server-side marking, idempotent)
  - `GET /api/v1/tests/{id}/result` (stored row only)
  - OpenAPI: **31 → 36 paths** (measured).
- Scoring reuses M6's `score_answers` (Decimal, 2dp); the frontend never computes a score.

### Frontend — exam UI
- `web/app/dashboard/tests/[id]/take/page.tsx` + `web/components/dashboard/exam-client.tsx` — exam page: question palette (answered / unanswered / marked-for-review / unknown indicators), prev/next, 4-option layout, mark-for-review toggle, clear-response button, progress (answered X of N), server timer display, submit confirmation dialog, server-returned marks summary after submit.
- `web/components/dashboard/test-detail-client.tsx` — the Start button now WORKS (M6 left it disabled "coming in M7"): `created` → "Start test" (calls start, routes to the exam page); `in_progress` → "Resume test"; `submitted` → honestly disabled "Already submitted"; `expired`/`abandoned` → disabled "This test has ended".
- `web/lib/api.ts` — exam client functions (`startTest`, `getExamSession`, `saveAnswers`, `submitTest`, `getTestResult`) + `ExamSession` / `ExamResult` types.

### 1.1 Design decisions (recorded, not silent)
- **Template → session:** M6 already creates template + session 1:1 at build time — the session IS the test instance. M7's `start` activates that same session (created → in_progress, `server_started_at` from the server clock). No new session row is created per attempt; a retake is a new test (M8 handles retakes).
- **Unknown snapshots at submit:** excluded from correct/incorrect/unattempted AND from `max_marks`, and counted as `unknown_count` on the result row — never scored as wrong, never a 500. `unknown_count` is an M7 addition to doc 03 §2.5's `test_results` table (doc 03 lists no unknown count); the brief explicitly allows recording them separately in a count field.
- **Percentage:** total/max clamped to [0, 100] (negative marking can make total_marks negative; a negative percentage is meaningless to a student).
- **Expiry:** a session past its deadline flips to `expired` on the next server read (GET session, save, submit). A save after expiry is 409 `time_expired` and stores NOTHING. Submit is still allowed from `expired` (it grades what was saved) — this is how the exam page "submits what was saved" when time runs out. Submit from `created` is 409 `test_not_started`.
- **Timer display:** the page shows ONLY the server-provided `remaining_seconds`, refreshed by polling every 10 seconds. There is deliberately NO local tick: a countdown ticked from the browser clock would move when the browser clock moves, which is exactly what the M7 acceptance test must catch. The 10-second step granularity is the honest trade-off, documented in the component.
- **Refresh safety:** answers save immediately (debounced 400ms per question) and are mirrored to a `localStorage` draft keyed by test id; on load the page restores from the server and re-sends any draft entries the server does not have yet (a save that was in flight when the page was refreshed). The draft is cleared on submit.
- **Unknown snapshots in the UI:** their options render DISABLED with an "Answer unknown — not scored" badge (they can still be marked for review). Q&A-pair snapshots with no options render as Q&A, never forced into options (defensive branch — M6's pool excludes no-option questions, so this should not occur in practice).
- **`started_at` vs `server_started_at`:** both are set to the same server instant at start (`started_at` is the readable field; `server_started_at` is the timer anchor). `expires_at` is set at start when the test has a time limit.
- **Clear response:** the response row is KEPT with `selected_index = NULL` (unattempted), so a mark-for-review flag survives a clear.

## 2. Gate results

| Gate | Result |
|---|---|
| Full pytest | **575 passed, 0 failed** in 338.93 s (555 M6 baseline + 20 new M7 tests) |
| `ruff check .` | Clean — 215 files |
| `ruff format --check .` | Clean — 215 files |
| `mypy app/db app/pipeline app/storage` | SUCCESS — no issues in 68 files |
| `npm run build` (real `web/.env.local`) | PASS — 26 user routes (M6: 25, +1 take route) |
| `npm run lint` | 0 problems |
| `npx tsc --noEmit` | Exit 0 |
| OpenAPI paths | 31 → 36 (5 new M7 endpoints, measured via `app.openapi()`) |
| Secrets scan (`web/`, JWT / service-role) | 0 offenders |
| `web/.env.local` | Real values intact (0600, project ref `gliebuyyjguxrwdfuakz`, anon key 208 chars, `eyJ…`) — never overwritten by a harness; no restore needed |

Note on the pytest history (honest, not hidden): the first full run after the M7 code landed showed **1 failed, 573 passed**. The failure was `test_observability.py::test_request_log_line_has_duration_ms`, and a second run with tesseract missing showed 18 failures — all pre-existing OCR tests, caused by a runtime restart wiping the system `tesseract` binary (reinstalled 5.3.4 + eng/osd/urd from the local apt cache; the same wipe happened in M7/M8). The 1 failure was a REAL order-dependence my new tests exposed — see §6.1. After the fix, the suite ran **574/0**, then **575/0** with the duplicate-batch regression test.

## 3. End-to-end proof (harness `~/workspace/m7-e2e/`)

Bank: the M6 copy (`~/workspace/m6-e2e/engine.db` → `m7-e2e/engine.db`, M6 original untouched), **91 questions: 64 scored / 27 unknown** (CA40 40/40 + PPSC-66 51 rows). Setup: `alembic upgrade head` adds the 0007 tables on the copied bank; GoTrue stub :54399 + engine :8001 + web :3000 (stub env overrides; `web/.env.local` untouched). Proof files: `api-proof.json` (29 steps), `browser-proof.json` (15 steps, ok: true).

### 3.1 API E2E (`api_e2e.py`) — ALL CHECKS PASSED
- Test created (explicit picks, PPSC default marking, 3600 s limit): 10 snapshots — 9 scored + 1 unknown. Result-before-submit → **404**; answers-before-start → **409** `test_not_started`.
- Start → `in_progress`, `server_started_at` from the server clock, `remaining_seconds` 3600 (then 3599 on re-read). Second start → **409** `test_already_started`.
- Batch 1 saved: 5 correct + Q2 marked for review (6 items, 5 distinct snapshots — this batch exposed the duplicate-batch 500, §6.2). Batch 2 saved: 2 incorrect + 1 to-be-cleared. Clear → row kept with `selected_index: null`. Unknown snapshot marked for review with no selection. Out-of-range answer → **422**.
- Reload proof: re-read session → **9 response rows intact**, cleared stays null, untouched snapshot absent, unknown row marked-for-review.
- **Submit — hand-checked (the numbers, quoted):** marking PPSC default (+1 / −0.25 / 0). Answers, from CA40 (all `ppsc-current-affairs-40-mcqs.pdf`):
  - Correct ×5 — Q1 (correct B), Q10 (correct C), Q11 (correct A), Q12 (correct D), Q13 (correct B) — answered with their correct options.
  - Incorrect ×2 — Q14 (correct C, answered D), Q15 (correct B, answered C).
  - Unattempted ×2 — Q16 (answered then cleared) + Q17 (never touched).
  - Unknown ×1 — a PPSC-66 question (`correct_index: -1`), marked for review only, never answered.
  - Arithmetic: 5 × (+1) = +5.0; 2 × (−0.25) = −0.50; 2 × 0 = 0; unknown excluded. **Total = 5.0 − 0.50 = 4.5. Max = 9 scored × 1 = 9.0. Percentage = 4.5 / 9.0 = 50.0.** Server returned exactly: correct 5, incorrect 2, unattempted 2, unknown_count 1, total_marks 4.5, max_marks 9.0, percentage 50.0, total_questions 10.
- **Double submit:** second submit returned the SAME `result_id` (`4baea094-…`), same marks; exactly **1 `test_results` row** in the DB. Answers after submit → **409** `test_already_submitted`. GET result returns the same row.
- **Expiry:** second test (10 scored, 60 s limit), harness-only clock move (`server_started_at = now − 120 s`). Save after expiry → **409** `time_expired`, **0 response rows stored**. Session reads `expired`, `remaining_seconds: 0`. Submit after expiry grades what was saved: 0 / 0 / 10 / 0, **0.0 / 10.0, 0.0%**, `time_taken_seconds: 121` (server timestamps: started 120 s ago + ~1 s).
- Browser test created unstarted for §3.2.

### 3.2 Browser E2E (`browser_e2e.mjs`, Playwright, stub GoTrue + local engine) — ALL CHECKS PASSED
- Login via UI 1,173 ms → tests list shows "M7 browser exam test" → **Start test** (the M6-disabled button) routes to the exam page in 135 ms.
- Q1 answered (option B), "All answers saved." shown; Q2 marked for review, saved. **Refresh mid-test: progress still "Answered 1 of 10", mark-for-review chip still shown, Q1 option B still selected.**
- **Timer proof (browser clock +1 h):** displayed 59:57 (3,597 s) before the change; with the browser clock frozen +1 h it read 59:47 (3,587 s) — a decay of **exactly 10 s, i.e. one real server poll**, not ~3,600 s. After resuming the clock and one more poll: 59:37 (3,577 s) vs server `remaining_seconds` 3,570 (7 s gap = poll cadence, within the 25 s tolerance). The countdown follows the server; the browser clock cannot move it.
- Submit dialog: "You have answered 1 of 10 questions. 9 unanswered and 1 marked for review. 1 question has no known answer and will not be scored." Result shown in UI: **"1 / 9"** = server result (correct 1, incorrect 0, unattempted 8, unknown_count 1, total 1, max 9).
- **Mobile 360 px: 0 px horizontal overflow** on the exam page and on the submitted-result page.

## 4. Fresh-DB proof
- Fresh SQLite DB, `alembic upgrade head` ONLY, on the copied M6 bank: tables `student_responses` → OK, `test_results` → OK (harness setup.sh asserts all eight tables).
- The migration-level proof is also a pytest test (`test_migration_0007_fresh_db_has_exam_tables`: upgrade head creates both tables; downgrade to 0006 drops them and leaves the M6 tables untouched).

## 5. What is NOT done (explicitly out of scope)
- Results/analytics (M8): result views beyond the submit summary, subject/topic breakdowns (stored as NULL in M7), history, mistake notebook, bookmarks.
- Payments/subscriptions (Phase 3).
- Live Supabase unchanged: bucket 016 unapplied, migration 017 unapplied, M3 auth-loop blocker unchanged, unconfirmed test user `officerpath.m3.test@gmail.com` still an owner step. No live data touched.

## 6. Limitations / open items
### 6.1 REAL BUG FOUND + FIXED — Alembic's `fileConfig` disabled the app's loggers (order-dependent test failure)
The first full run showed 1 failure: `test_request_log_line_has_duration_ms` (M7 observability test) — "no request log line emitted". Bisected to my two migration tests: `alembic.ini` has `[loggers]` sections, and our `alembic/env.py` called `fileConfig(config.config_file_name)` with the default `disable_existing_loggers=True`, which disables every logger created before the call (`app.main` went `disabled=True`, proven by direct measurement). M6's migration tests did the same thing but escaped it only because `test_tests.py` sorts AFTER `test_observability.py`; my `test_exam.py` sorts before it and exposed the latent order-dependence. Fix (one line, `alembic/env.py`): `fileConfig(config.config_file_name, disable_existing_loggers=False)`. An `alembic.ini` key was tried first and reverted — CPython's `fileConfig` does not read `disable_existing_loggers` from the ini (only `dictConfig` does). After the fix: `test_exam + test_tests + test_observability` = 44/44, full suite 574/0.

### 6.2 REAL BUG FOUND + FIXED — duplicate snapshot in one answers batch → 500
The API E2E's first batch (6 items, 5 distinct snapshots — an answer plus a mark-for-review flip for the same question) 500'd with `UNIQUE constraint failed: student_responses.session_id, student_responses.snapshot_id`. Cause: `save_answers` created a pending row per item and queried for an existing row before the first was committed, so the second item created a second pending row. Fix (`app/services/exam.py`): track rows created in the current batch and reuse them (last item wins). Regression test added (`test_save_answers_same_snapshot_twice_in_one_batch_is_one_row`): 200, one saved row, last values win. The unit suite had not covered same-snapshot-twice-in-one-batch (only re-saves across requests).

### 6.3 Harness notes (environment, not code)
- A runtime restart mid-milestone wiped the system `tesseract` binary (and `/tmp`); reinstalled 5.3.4 + eng/osd/urd from the local apt archive cache via `dpkg -i` (the runtime's own `apt-get update` held the apt lock for 6+ minutes). Deploy must install tesseract in the image (already documented in Phase 1).
- The same restart changed the shell's `NO_PROXY` to include bracketed-IPv6 entries (`[::1]`, `[fd8b:…]`), which httpx cannot parse (`InvalidURL ':1]'`) — it broke the harness's httpx client AND the engine's Supabase client creation (`auth_unavailable` 503s) until `NO_PROXY`/`no_proxy` were unset for those processes. Test-only harness issue; the fix is documented in the harness scripts (`trust_env=False` in `api_e2e.py`).
- The harness's direct-SQL checks must compare UUIDs as CHAR(32) hex (dashes stripped) — SQLite stores `sa.Uuid` without dashes; a dashed comparison silently matches 0 rows. Two harness checks were fixed for this (the API's `test_id` IS the session id; `template_id` is a different row).
- Timer display updates only on the 10 s server poll (deliberate — no local tick). Between polls the displayed time is up to 10 s stale; the server value is always the truth.
- iPhone Safari / real device unverified (M9/M10). Lighthouse not run (M9/M10). Urdu preservation not E2E-proven in M7 (no Urdu fixture in the bank; the 17 PPSC-66 Q&A pairs are a count, as in M5/M6). Inferred-answer flag + Q&A-pair card rendering remain unit-test-only (0 inferred rows in the bank).
- Live Supabase unchanged (016 bucket + 017 unapplied, M3 auth-loop blocker + unconfirmed test user still owner steps).

## 7. Files changed
Engine (new): `app/db/models.py` — `StudentResponse` + `TestResult` models; `alembic/versions/0007_m7_exam.py` (revision `0007_m7_exam`, down_revision `0006_m6_tests`); `app/services/exam.py`; `app/schemas/exam.py`; `app/tests/test_exam.py` (20 tests). Engine (edited): `app/api/v1/tests.py` (5 endpoints); `alembic/env.py` (fileConfig `disable_existing_loggers=False`, §6.1). Frontend (new): `web/app/dashboard/tests/[id]/take/page.tsx`; `web/components/dashboard/exam-client.tsx`. Frontend (edited): `web/components/dashboard/test-detail-client.tsx` (Start button works); `web/lib/api.ts` (exam client + types). Docs: `docs/API.md` (exam section, GAP-6 endpoints); `docs/phase2/02-api-integration-map.md` (GAP-6 DONE); this report. Harness (not committed): `~/workspace/m7-e2e/` — `setup.sh`, `gotrue_stub.py`, `api_e2e.py`, `browser_e2e.mjs`, `api-proof.json`, `browser-proof.json`, `logs/`.
