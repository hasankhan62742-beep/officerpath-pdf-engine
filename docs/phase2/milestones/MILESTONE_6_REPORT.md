# OfficerPath AI — Phase 2, Milestone 6 Report: Test Builder

**Status: COMPLETE — E2E + browser proof landed (see §3). Awaiting parent verification.**
**Branch:** `officerpath-phase2-web` (local only, no push, no deploy, no paid services)
**Date:** 2026-11-22 (PKT)
**Parent verification:** PENDING

## 1. What was built

### Engine — test builder API (GAP-5 DONE)
- Models (`app/db/models.py`): `MarkingConfig`, `TestTemplate` (incl. `excluded_unknown` / `excluded_no_options` columns), `TestSession`, `TestQuestionSnapshot`.
- Alembic **0006** (`alembic/versions/0006_m6_tests.py`): creates the four M6 tables; **also creates `documents`/`jobs` IF NOT EXISTS** (mirroring migration 015 DDL incl. checks and unique indexes, deliberately NO FK to `auth.users`) — this is the M5 carry-over fix. Seeds the PPSC default marking config idempotently (hex UUIDs, per the M5 lesson). Downgrade refuses while `test_sessions`/`test_templates` hold rows and never drops `documents`/`jobs`.
- Schemas (`app/schemas/tests.py`) + service (`app/services/tests.py`: selection, snapshots, scoring, CRUD) + routes (`app/api/v1/tests.py`, registered in `app/main.py`):
  - `GET /api/v1/marking-configs`, `POST /api/v1/marking-configs`
  - `GET /api/v1/tests/availability` (pool counts + 5-question sample)
  - `POST /api/v1/tests` (201), `GET /api/v1/tests`, `GET /api/v1/tests/{id}`, `PATCH /api/v1/tests/{id}`, `DELETE /api/v1/tests/{id}`
  - OpenAPI: **27 → 31 paths** (measured).
- Scoring is a pure backend function (`score_answers`, Decimal arithmetic, 2dp); `correct_index < 0` in scoring input raises ValueError. The frontend never computes a score.

### Frontend — test builder UI
- `web/app/dashboard/tests/page.tsx` — tests list (title, question count, marking summary, status, created date, view/delete).
- `web/app/dashboard/tests/new/page.tsx` — builder: name, source modes (all / documents / subjects / explicit picker), quick-pick counts 25/50/100/150/200 + custom 1–200, marking select (PPSC default pre-filled and explained in plain words) or custom, repetition/unknown toggles, optional time limit, availability preview with sample, honest M7 note.
- `web/app/dashboard/tests/[id]/page.tsx` + `web/components/dashboard/test-detail-client.tsx` — read-only snapshot preview reusing `QuestionResultCard`; Start button disabled and labelled "coming in M7". `QuestionResultCard` gained a `detailsHref` prop (null hides the link when a snapshot's source question was deleted).
- "Tests" added to `web/components/dashboard/dashboard-nav.tsx`.

### Design decisions (deviations from doc 03, recorded)
- Question count: any 1–200 accepted (service-enforced); UI offers 25/50/100/150/200 as quick picks — doc 03 §2.4's CHECK IN (25,50,100,150,200) was a constraint; the brief's E2E proof builds a 20-question test.
- `test_sessions.server_started_at` nullable in M6 (M7 sets it at start, never from the browser clock); doc 03 marks it NOT NULL.
- Marking ranges validated: correct 0.25–10, incorrect −5–0, unattempted −1–0.
- Selection: random sample with a saved `selection_seed` (reproducible); explicit mode keeps given order; unknown excluded by default with `excluded_unknown`/`excluded_no_options` counts returned and stored on the template; Q&A pairs (no options) always excluded from the pool; explicit unknown picks also require `include_unknown` (picking by id is not itself the opt-in).
- Availability: requesting more than the pool holds → 422 `insufficient_questions` naming the available count, never a short test.
- Delete/update only while status == `created`; otherwise 409 `test_already_started`.

## 2. Gate results

| Gate | Result |
|---|---|
| `npm run build` (web) | PASS — 26 routes (was 23, +3 tests routes) |
| `npm run lint` | **0 problems** (exit 0, no output) |
| `npx tsc --noEmit` | exit 0 |
| pytest (full suite) | **555 passed, 0 failed** (327.43s, run alone on a quiet VM — M5 baseline 536 + 19 new) |
| `pytest app/tests/test_tests.py` | **19 passed** (7.01s; 18 + the new partial-index regression test) |
| `pytest app/tests/test_tests.py app/tests/test_documents.py` | **28 passed** (187.41s) |
| `ruff check .` | All checks passed (211 files) |
| `ruff format --check .` | 211 files formatted |
| `mypy app/db app/pipeline app/storage` | Success: no issues found in 68 source files |
| OpenAPI paths | **31** (27 at M5 + 4: marking-configs, tests, tests/availability, tests/{test_id}) |
| Secrets scan (source files only, excl. node_modules/.next) | **0 offenders** — no JWT/key patterns, no service-role reference in web/ |

### Bugs found by measuring (fixed in M6)
1. Ruff: 13 errors at first run (12× E501 long lines + 1× F841 unused `q4` in `test_tests.py`) — fixed by `ruff check --fix`, `ruff format`, and removing the unused variable. Re-run clean.
2. TypeScript: `snapshotToQuestionItem` widened `answer_status` to `string` — fixed with an explicit `QuestionItem` return type. Build then passed.
3. **Delete → re-upload 500 (REAL BUG, M1/M4 code):** deleting a document and re-uploading the same file failed with `500 UNIQUE constraint failed: documents.user_id, documents.content_hash`. Root cause: 015's plain unique index on (user_id, content_hash) does not ignore soft-deleted rows, while the dedup lookup correctly does (M4) — the deleted row held the unique slot. The M4 test never caught it because conftest builds the DB from models (`create_all`), and the model had only a plain non-unique index. **Fix:** the index is now PARTIAL (`WHERE deleted_at IS NULL`) in three places: `app/db/models.py`, Alembic 0006's mirror, and new Supabase migration 017 (`supabase/migrations/017_documents_hash_partial_unique.sql` + down; written, NOT applied — owner step, live 015 still has the plain index until then). **Regression test:** `test_migration_0006_documents_hash_index_is_partial` (migration-built DB: deleted + live same-hash rows coexist; second live row still rejected; other user unaffected) + the existing M4 re-upload test now runs against the model-enforced partial index. **Guard-value proof (measured):** on the old plain index the re-upload insert fails with the UNIQUE error; on the partial index it succeeds and a duplicate live insert is still rejected.
4. **Per-page tesseract timeouts silently emptied PPSC-66 pages (Phase 1 pipeline behaviour, NOT an M6 bug):** see §3 environment note.

## 3. End-to-end proof (harness `~/workspace/m6-e2e/`, fresh SQLite DB, GoTrue stub :54399, engine :8001, web :3000)

**Environment note (honest):** the shared VM ran at load 1–14 during this proof (a concurrent video render + two full pytest suites at first). Two distinct timeout effects were measured, both environmental, neither an M6 code failure (M6 touches no pipeline code):
- **Worker stage timeout (1800s):** the PPSC-66 parse failed it twice (attempt 1: 1875.5s; attempt 2: 1823.8s) because the OCR stage accumulates ~300s per page on this loaded VM.
- **Per-page tesseract timeout (300s, `app/config.py` default):** pages 2–7 of PPSC-66 each hit it (six consecutive ~301–306s stage deltas = timeout + overhead). `_ocr_page` catches all exceptions and returns `[]` (per-page failure isolation, M2 design), so those pages silently contributed nothing — attempt 3 completed with only page 1's 11 rows (1 answered, 10 unknown, numbers unknown). The harness therefore restarted the engine with `WORKER_STAGE_TIMEOUT_SECONDS=3600` + `TESSERACT_TIMEOUT_SECONDS=900` (harness-only; repo defaults unchanged) and re-ran the parse from scratch; the M5 proof passed at the defaults on a quieter VM. The timeouts are deployment guards, not correctness properties.
- **Final proof run, page 3 (Q25–41) lost again:** even at the 900s per-page timeout, page 3's OCR took 903s and was dropped by the timeout (cumulative OCR deltas: p1+p2 522.34s → p3 1425.43s → p4 1798.85s → p5 1990.18s → p6 2223.19s → p7 2249.8s). The other six pages completed. The final PPSC-66 parse therefore holds **51 rows (24 answered / 27 unknown / 27 pending)**, not M5's 68/41 — the missing 17 rows are exactly Q25–41 (verified row-by-row against the M5 database). Unknown (27) and Q&A-pair (17, report-only) counts match M5 exactly. This is an environment/OCR effect, not an M6 code difference. The test-builder checks below need a bank with answered + unknown rows; the measured bank (91 rows: 64 answered, 27 unknown) provides that. No third re-parse was run — re-running a ~40-minute parse for the same at-risk page would not change any M6 conclusion.
- **Also found while re-running:** the delete → re-upload 500 (§2 bug 3), fixed in M6 (partial unique index) before the final proof run.

### 3.1 Parse results
| Fixture | Result | Time |
|---|---|---|
| CA40 (`ppsc-current-affairs-40-mcqs.pdf`) | done, 40 questions / 40 answered | 6.4s |
| PPSC-66 (`ppsc_paper_66.pdf`) | done, 51 questions / 24 answered / 27 unknown / 27 pending; 17 Q&A pairs (report count only, never stored rows) | 2395.4s |
| Bank total after both uploads | **91 rows** (64 answered, 27 unknown) | — |

### 3.2 Test creation (20-question mixed test, via the exact API calls the UI makes)
- Availability (`GET /api/v1/tests/availability?source_type=all`): available **64**, excluded_unknown **27**, excluded_no_options **0**, sample 5. Partition sums to the bank: 64 + 27 + 0 = 91. With `include_unknown=true`: available **91** (exactly 64 + 27).
- Marking configs: exactly 1 — **PPSC default** (+1 / −0.25 / 0, `is_default: true`).
- Test created: `M6 E2E mixed test`, id `ad878d61-c1bd-4351-be65-c09b31f7dc07`, **20 questions**, status `created`, source `all`, `allow_repetition: false`, `include_unknown: false`, excluded_unknown 27, excluded_no_options 0. Stored marking config = PPSC default (id `940dbedb-6d0b-439c-bb27-e7f7c091ed27`).
- **Why `excluded_no_options` is 0 (measured, not assumed):** the 17 "Q&A pairs" are a count in the extraction report summary only — `persist_matched_document` stores questions + pending rows and never stores qa_pairs as rows (`store.py`: `"qa_pairs_reported_only"`). Verified in the DB: 0 of the 51 PPSC-66 rows lack options (all carry 4); the M5 run's 68 rows were the same. The unit suite already asserts this (`test_tests.py`: `excluded_no_options == 0`, "qa_pair is a count, not a row"). The no-option exclusion path for a *stored* no-option row (e.g. the Computer Q&A fixture) is covered only by the service's explicit-pick error — that fixture was not parsed in this E2E run (see §6).

### 3.3 Snapshot immutability proof
- Target: snapshot[0] of the 20-question test, question `3c6b59ce-ba74-42e1-b885-e8eb4f0c262e`, old answer letter **C** → bank correction to **B** (`POST .../corrections`, field `answer`).
- Bank after correction: `correct_index` 1, letter B, `corrected: true` — the correction took effect in the bank.
- Test snapshot after re-read: sha256 **before** `13feaea07a050f5d921614f51ae7bad72810e1baab5daa8a3ffbe40b0844c779` = sha256 **after** `13feaea07a050f5d921614f51ae7bad72810e1baab5daa8a3ffbe40b0844c779` — **byte-identical**. Snapshot `correct_index` still 2 (old C); question text identical: true; options identical: true. Marking config unchanged after the correction.
- UI-level check (browser proof §3.7): the same corrected question's card still shows the OLD letter C, not the new B.

### 3.4 No-duplicates proof
- The 20-question test holds **20 snapshots / 20 unique question ids** (0 duplicates), 0 unknown snapshots.
- Explicit duplicate picks without the flag → **422** (`duplicate_questions`: "Duplicate questions are not allowed in a test unless allow_repetition is true: 1 duplicate id(s).").
- Same picks with `allow_repetition: true` → **201**, `allow_repetition: true` recorded on the test, both snapshots carrying the same question id (`3c6b59ce-ba74-42e1-b885-e8eb4f0c262e` twice). That test was then deleted (200, re-read 404) — delete-before-attempts works.
- Tests list after the API run: 3 tests ("M6 E2E mixed test" 20, "M6 E2E unknown opted in" 2, "M6 E2E dup allowed" 2 — the last deleted before the browser run).

### 3.5 Unknown-handling proof
- Decision (A.5): unknown questions are **excluded by default** (with counts reported), included only on explicit opt-in and flagged.
- Availability default: 27 unknown excluded; `include_unknown=true` adds exactly those 27 (64 → 91).
- Explicit unknown pick without the flag → **422** (`validation_error`: "1 picked question(s) have no known answer (correct_index -1). Set include_unknown to include them explicitly, flagged as unknown.").
- Same picks with `include_unknown: true` → **201**, test `8331fcd7-5640-486e-9c93-f61137169033`, both snapshots `correct_index: -1`, `include_unknown` recorded on the test.
- The 20-question default test contains **0 unknown snapshots**.

### 3.6 Scoring worked example (real function, `scoring-proof.json`)
- 10 correct, 2 incorrect, 3 unattempted, PPSC default (+1 / −0.25 / 0) → **total_marks 9.5**, max_marks 15.0 (measured, `score_answers`).
- Same answers, custom marking (+2 / −0.5 / 0) → **total_marks 19.0**, max_marks 30.0.
- Unknown item (`correct_index: -1`) → **ValueError** ("Cannot score a question with an unknown answer"), never a mark.

### 3.7 Browser proof (Playwright Chromium, stub GoTrue + local engine, `browser-proof.json`)
All 13 steps passed:
- Login via UI: 1621ms → `/dashboard`.
- Tests list shows the API tests: mixed test present, unknown test present, PPSC marking present.
- Builder availability preview: available **64**, excluded unknown **27** (= API 64).
- Builder marking default: "PPSC default (+1 / −0.25 / 0) — default" pre-selected, "Custom marking…" available.
- Test created via UI: **"M6 browser test", 20 questions** — verified in the API list afterwards (3 tests total at that point).
- Test view via UI: title ✓, 20 questions ✓, marking ✓.
- Start button **honestly disabled** ("coming in M7").
- Snapshot correct marks on view: **20** (one per question).
- Snapshot card after bank correction (UI): shows OLD letter **C**, not new **B** — the preview is immutable.
- Mobile 360px: **0px overflow** on builder, tests list, and test view.

## 4. Fresh-DB proof (M5 carry-over, C)
- Fresh SQLite DB, `alembic upgrade head` ONLY (no `create_all` workaround — removed from the M6 harness): tables `documents` → OK, `jobs` → OK, `test_templates` → OK, `test_sessions` → OK, `test_question_snapshots` → OK, `marking_configs` → OK, `subjects` → OK. (The harness check also listed `questions` → MISSING; that table does not exist by design — the model is `extracted_questions`.)
- Worker started without "no such table": CA40 job queued → done in 6.4s on the fresh DB; engine log scan for "no such table" → **0 hits** (measured over the full E2E run, `api-proof.json` `worker_start`).
- **Supabase migration 017** (`supabase/migrations/017_documents_hash_partial_unique.sql` + down) written, NOT applied live — it drops 015's plain unique index and recreates it as a partial unique index (`WHERE deleted_at IS NULL`). Joins 016 in the owner-apply queue (Dashboard SQL Editor). Until it is applied, live Supabase still has the plain index and delete → re-upload of the same file still 500s live; the engine-side fix (model + 0006) covers fresh engine-managed databases.

## 5. What is NOT done (explicitly out of scope)
- Exam interface (M7): taking a test, `server_started_at`, answers, submit, server-side timer.
- Results/analytics (M8): result views, analytics, mistake notebook.
- Payments/subscriptions (Phase 3).
- Live Supabase unchanged: bucket 016 unapplied, M3 auth-loop blocker unchanged, unconfirmed test user `officerpath.m3.test@gmail.com` still an owner step. No live data touched.

## 6. Limitations / open items
- Full pytest gate: **MET — 555 passed, 0 failed** on the clean re-run (327.43s, alone on a quiet VM). The earlier "FF" partial output was a contention artifact (two pytest suites + E2E OCR competing); no failure reproduced.
- iPhone Safari / real-device + Lighthouse: UNVERIFIED (M9/M10).
- Inferred-answer flag + Q&A-pair card rendering in the test preview: unit-test-only (0 inferred in the fixtures).
- Urdu preservation: not E2E-proven (no Urdu fixture this run).
- PPSC-66 parse wall time on this VM is load-dependent (see §3 environment note); the M5 numbers (146.8s / 481.3s) remain the clean baseline. The final proof's PPSC-66 parse lost page 3 (Q25–41) to the 900s per-page tesseract timeout — the bank is 91 rows, not 108.
- Stored no-option rows (a Q&A pair stored without options, e.g. the Computer Q&A fixture) were not parsed in this E2E run, so the availability `excluded_no_options > 0` path is E2E-unproven; it is covered only by the service's explicit-pick error and unit tests. The 17 PPSC-66 "Q&A pairs" are a report count, not stored rows (§3.2).
- Live Supabase still carries 015's plain unique index until the owner applies 017 (§4) — delete → re-upload still 500s live until then.

## 7. Files changed
Commit `cb3f4b6` on `officerpath-phase2-web` (local only, no push): **20 files, +4,021 / −11**.
- Engine (new): `alembic/versions/0006_m6_tests.py`, `app/api/v1/tests.py`, `app/schemas/tests.py`, `app/services/tests.py`, `app/tests/test_tests.py` (19 tests).
- Engine (modified): `app/db/models.py` (M6 models + partial documents hash index), `app/main.py` (router), `app/tests/conftest.py` (tests_api session patch).
- Supabase (new, NOT applied): `supabase/migrations/017_documents_hash_partial_unique.sql` + `_down.sql`.
- Frontend (new): `web/app/dashboard/tests/page.tsx`, `web/app/dashboard/tests/new/page.tsx`, `web/app/dashboard/tests/[id]/page.tsx`, `web/components/dashboard/test-detail-client.tsx`.
- Frontend (modified): `web/lib/api.ts` (tests section), `web/components/dashboard/dashboard-nav.tsx` (Tests link), `web/components/dashboard/question-result.tsx` (`detailsHref` prop).
- Docs: `docs/phase2/milestones/MILESTONE_6_REPORT.md` (this report), `docs/API.md` (test-builder section + 017 note), `docs/phase2/02-api-integration-map.md` (GAP-5 DONE).
- No new packages installed (engine or web).
- E2E harness (not committed, `~/workspace/m6-e2e/`): `setup.sh`, `api_e2e.py`, `api_e2e_phase2.py`, `browser_e2e.mjs`, `watch_job.py`, `restart_engine_3600.sh`, `gotrue_stub.py`, `scoring_proof.py`, `api-proof.json`, `browser-proof.json`, `scoring-proof.json`.
