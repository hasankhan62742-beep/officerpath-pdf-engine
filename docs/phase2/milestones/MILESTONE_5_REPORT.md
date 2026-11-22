# Milestone 5 Report — Extraction Results + Question Bank

**Branch:** `officerpath-phase2-web` · **Status:** built, E2E-proven, gates green — awaiting parent verification
**Date:** 2026-11-22 (work 16:32 → ~19:10 PKT; the build itself was done before a runtime restart forced a full E2E rebuild — see §7)
**Commit:** not yet committed (this report is written before the local commit; see §9)
**Scope:** Phase 2 execution plan §M5 — per-document extraction results, manual corrections with audit trail, and the question bank. No test builder (M6), no exam interface (M7), no results/analytics (M8), no payments (Phase 3).

## 1. What was built

### Engine (new question-bank + results API)
- `app/api/v1/questions.py` (new) — 7 operations across 6 new OpenAPI paths (the corrections GET shares the existing POST corrections path, so paths go 21 → 27):
  - `GET /api/v1/questions` — bank list, owner-only, paginated; filters `q` (text search), `document_id`, `status` (answered / unknown / pending / inferred / corrected / conflict-resolved), `subject_id`, `confidence_min/max`.
  - `GET /api/v1/questions/{id}` — detail + evidence trail + correction history.
  - `GET /api/v1/documents/{id}/questions` — per-document results + counts + `qa_pairs` count.
  - `GET /api/v1/documents/{id}/questions/{question_id}/corrections` — audit listing (the minimal gap-fill the brief allowed).
  - `GET /api/v1/subjects` — the 13 seeded subjects.
  - `POST /api/v1/questions/{id}/subjects` — idempotent manual subject assign.
  - `DELETE /api/v1/questions/{id}/subjects/{subject_id}` — unassign.
- `app/schemas/questions.py`, `app/services/questions.py` (new) — batched reads; questions ordered by **printed number, not `created_at`** (SQLite second-precision ties scramble order — the M4 FIFO trap); status filters; confidence band via EXISTS; `confidence` is null when no answer row exists.
- `app/db/models.py` — `Subject` / `Topic` / `QuestionSubject` models.
- `alembic/versions/0005_m5_subjects.py` (new) — creates the three tables, seeds the 13 subjects from prompt §12 (idempotent guard); downgrade refuses while `question_subjects` holds rows.
- `app/main.py` — router registered. `app/tests/conftest.py` — patched for the new router's `get_session`.
- `app/tests/test_questions.py` (new) — 7 tests: document questions counts/order/unknown, evidence trail, bank filters + search + confidence bands + pagination, per-user isolation, correction round-trip + audit, subject assign/unassign, migration 0005 seeds 13 subjects + downgrade refusal (+ the §5 regression).

### Frontend
- `web/lib/api.ts` — question types, `answerSourceLabel`, list/get/listDocumentQuestions/getDocumentReport/listCorrections/submitCorrection/listSubjects/assignSubject/unassignSubject.
- `web/components/dashboard/question-result.tsx` (new) — the shared truth-rule component (`QuestionBadges`, `QuestionOptions`, `AnswerLine`, `QuestionResultCard`): `correct_index = -1` renders **"Answer: unknown."** and never highlights any option; inferred answers carry a visible `inferred` flag; Q&A pairs (no options) render as Q&A, never forced into 4 options; Urdu script preserved exactly as returned.
- `web/components/dashboard/document-results.tsx` (new) — per-document results: counts, QA-pairs count note, needs-review alert, extraction report card (counts + confidence distribution + pending list, honestly), pagination 10/page.
- Document detail (`web/components/dashboard/document-detail-client.tsx`) — wired to show results when the job is `done`; the M4 "arrives in Milestone 5" note is removed.
- Question bank (`web/app/dashboard/questions/page.tsx`, new) — search, document/status/subject/confidence-band filters, pagination 20/page, honest empty states.
- Question detail (`web/app/dashboard/questions/[id]/page.tsx` + `web/components/dashboard/question-detail-client.tsx`, new) — server wrapper + Suspense + `instant=false` (same Next 16 pattern as the document detail): full options, correct answer or unknown state, evidence trail, source document, correction form (answer / question-text / option-text + reason), correction history, manual subject assign/unassign.
- Dashboard nav gained a "Questions" link.

### Docs
- `docs/API.md` — new question-bank / results / subjects section.
- `docs/phase2/02-api-integration-map.md` — **GAP-3 (question-bank reads) DONE, GAP-4 (review/corrections listing) DONE** in M5. **GAP-12 (signed question-asset serving) NOT built** — no code anywhere creates `question_assets` rows (grep: only the model exists), so there is nothing to serve; recorded for M9/M10.
- Subjects/topics: the engine does **not** classify subjects — no subject label is ever invented. The document is the grouping; subjects are manual-only (assign/unassign in the UI) until a classifier exists (M6+).

## 2. Gate results (all measured in this run)

| Gate | Result |
|---|---|
| pytest (full) | **536 passed / 0 failed**, 641.24s (10:41) under VM contention (E2E servers running). M4 baseline 529 + 7 new M5 tests. `test_questions.py` re-run post-format: 7 passed. |
| ruff check | **All checks passed** |
| ruff format | **206 files already formatted** (one file reformatted during the run: `test_questions.py`) |
| mypy CI gate (`app/db app/pipeline app/storage`) | **Success: no issues found in 68 source files** |
| `npm run build` | **PASS, 23 routes** in the app tree (§2.1 lists them; the 2 new question routes. M4 reported 22 by a different count — the tree itself is what was measured here) |
| `npm run lint` | **exit 0, 0 problems** (the earlier unused-`EmptyState` warning is gone) |
| `npx tsc --noEmit` | **exit 0** |
| OpenAPI paths | **27** (21 at M4 + 6 new paths; the corrections GET shares the POST path) |
| Secrets scan | **0 offenders** — no JWT values and no service-role references in `web/` source or the changed engine files; `.env.example` holds placeholders only |

### 2.1 Routes in the build (23)
`/`, `/_not-found`, `/about`, `/auth/callback`, `/auth/reset-password`, `/contact`, `/dashboard`, `/dashboard/documents`, `/dashboard/documents/[id]`, `/dashboard/profile`, `/dashboard/questions`, `/dashboard/questions/[id]`, `/dashboard/upload`, `/exam-preparation`, `/features`, `/forgot-password`, `/how-it-works`, `/icon.svg`, `/login`, `/pricing`, `/privacy`, `/register`, `/terms` — plus `robots.txt` / `sitemap.xml`.

No new packages were installed (no `package.json` / requirements change).

## 3. End-to-end proof (local, real fixtures, never modified)

Harness (test-only, `~/workspace/m5-e2e/`, outside the repo): GoTrue stub on :54399 (fixed user `11111111-1111-1111-1111-111111111111`), engine on :8001 (fresh SQLite, Alembic to head incl. 0005, worker on), web on :3000. Fixtures: `ppsc-current-affairs-40-mcqs.pdf` (CA40) and `ppsc_paper_66.pdf` (PPSC-66) from `~/workspace/officerpath-ai/test-fixtures/ppsc66/`.

### 3.1 API proof (final clean run, fresh DB)

| | CA40 | PPSC-66 |
|---|---|---|
| Upload → job `done` | 4.0s | 481.3s (VM contention — see §7; the first run took 146.8s with identical counts) |
| Questions (rows) | 40 | 68 |
| Answered | 40 | **41** (pre-correction) |
| Unknown (`correct_index = -1`) | 0 | **27** |
| Pending | 0 | **27** |
| Inferred | 0 | 0 |
| Corrected | 0 | 0 (pre-correction) |
| Q&A pairs (count only) | 0 | **17** |
| Report: extracted / uncertain / requires_review | 40 / 0 / false | 41 / 0 / **true** |

PPSC-66 report review reasons (engine's own words): `"option B duplicates option A."`, `"option C duplicates option A."`, `"missing question numbers: [2, 5, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 48, 50, 53] ..."`. The UI shows this plainly — PPSC-66 recovered **41 of 100** numbers, an OCR limitation (M4/M8), not an extraction failure. No accuracy claim is invented anywhere.

Bank (pre-correction, both documents parsed): **total 108** (40 + 68); answered 81, unknown 27, pending 27, inferred 0, corrected 0. Search `q=capital` → **1**. Subjects seeded: **13** (computer-science, current-affairs, english, everyday-science, general-ability, general-knowledge, geography, history, islamic-studies, mathematics, pakistan-affairs, political-science, urdu).

### 3.2 UI counts vs API counts (browser, Playwright Chromium)

| Check | UI | API | Match |
|---|---|---|---|
| Bank total | 108 | 108 | ✓ |
| Bank search "capital" | 1 | 1 | ✓ |
| Bank filter `status=unknown` | 26 | 26 (live re-read — the API correction had already answered one unknown) | ✓ |
| CA40 results page | 40 questions, 40 answered (counts card read in the UI) | 40 / 40 | ✓ |
| PPSC-66 results page | 68 rows rendered ("of 68 questions."), QA-pairs note present; the counts card values were not scraped in this run — the API counts are §3.1, and the bank-level unknown filter (26) matched the live API exactly | 68 rows; 41 / 27 / 27 pre-correction, 42 / 26 / 26 after the API correction | ✓ (rows + filter; counts card itself not scraped) |

### 3.3 Unknown-state proof (truth rule)
PPSC-66 **Q28** ("TEHSILDAR / CONSOLIDATION OFFICER … English Morning", options A. Break down / B. Broke out / C. Break off / D. None of these) renders with the **"Needs review"** badge and the line **"Answer: unknown. The engine could not determine the answer for this question — no option is marked correct."** — with **0** "— correct" marks inside its card. (Pending questions show "Needs review", not an "Unknown answer" badge — the badge text follows `answer_status`; the unknown state itself is the `Answer: unknown.` line plus zero highlighted options.)

CA40 page 1 shows **10** "— correct" marks (one per answered question on the page) — correct options are highlighted only where the engine actually resolved one.

### 3.4 Correction round-trip proof
- **API:** PPSC-66 Q4 *"Halaku Khan sacked Baghdad in:"* (unknown) → `POST .../corrections` `{field: "answer", new_value: "B", reason: "M5 E2E check"}` → detail shows `correct_index: 1`, `correct_letter: "B"`, `corrected: true`, `answer_status: "verified"`, 1 correction; audit listing total **1**. The original extraction is untouched — the correction is a new version with an audit entry.
- **UI:** the same correction is visible on the question-detail page ("Corrected" badge, "Answer: B", reason "M5 E2E check" in the history). A **second** correction submitted through the UI on Q28 (answer **C**, reason "M5 browser E2E correction") round-trips: "Correction saved", "Answer: C" shown, audit entry present (API-verified afterwards).
- **Bank final state** (after both corrections): 108 total, **83 answered, 25 unknown, 25 pending, 2 corrected**.

### 3.5 Subject assignment proof
Manual assign via the UI on Q28: the assigned-subject badge appears (**1 badge, no error**) and the API confirms `subjects: [("Computer Science", "computer-science")]` on the question. (The first browser run's step-9 assertion was a false positive — it matched subject names in the picker dropdown while the assign was actually 404ing; see §5. The assertion now checks for the badge itself.)

### 3.6 Mobile
360px viewport, zero horizontal overflow: question bank **0px**, question detail **0px**.

## 4. What the engine returns vs what the UI shows
Nothing is added or smoothed: counts, evidence, confidence, and review reasons are the engine's values verbatim. Two engine behaviours worth knowing (both real, both shown as-is):
- PPSC-66 stores **two rows numbered "4"** (one answered, one pending) — the UI shows both; numbers come from the engine.
- PPSC-66 reports **17 Q&A pairs as a count only** — no `qa_pair` rows are stored, so there is no Q&A card to render from live data (see §6).

## 5. Real bugs found by measuring (fixed + regression coverage)

### 5.1 Migration 0005 seed stored dashed UUIDs — subject assign 404'd (PRODUCT BUG, fixed)
The seed inserted `str(uuid.uuid4())` (dashed) via raw SQL, while the ORM maps `Subject.id` as `sa.Uuid`, which stores **CHAR(32) hex** on SQLite. Result: `assign_subject`'s `filter(Subject.id == uuid)` never matched a listed subject → **404 "Subject not found"** for a subject the list endpoint returned. The M5 unit tests missed it because they insert via the ORM (consistent format) and never round-tripped list → assign.
- **Fix:** seed inserts `uuid.uuid4().hex` (Postgres accepts undashed hex as a uuid literal, so this is correct on both dialects).
- **Regression test:** `test_migration_0005_seeds_13_subjects` now round-trips list → ORM id-filter lookup. Proven: the test **FAILS on the old seed** and **PASSES on the fixed seed** (7/7 in `test_questions.py`).
- The browser E2E's step-9 assertion was also fixed (badge check, not page-text match) — it had passed once while the assign was failing.

### 5.2 Repo gap found, NOT fixed in M5 (recorded for M6/owner)
Alembic **0001 assumes Supabase migration 015 already created the `documents` and `jobs` tables** (its docstring: "015 owns them"). A fresh database built by `alembic upgrade head` alone has **no `documents`/`jobs` tables** — the worker fails with `no such table: jobs` and no upload can complete. Tests never catch it (conftest uses `create_all` from models); the M4/M5 harnesses work around it with `create_all` after the upgrade. The live deploy path is covered (015 is applied via Dashboard per the deploy guide), but a fresh local/CI database is not. Recommendation: a 0006 migration that creates `documents`/`jobs` when missing, or a documented `create_all` step — parent to decide in M6.

## 6. Honest limitations (measured, not assumed)
- **Inferred answers: 0 in both fixtures.** The inferred flag/badge rendering is covered by unit tests only, NOT by live E2E data. No fixture in this run produced an inferred answer.
- **Q&A-pair rendering: unit-test-only.** PPSC-66 reports 17 QA pairs as a count, but no `qa_pair` rows are stored, so the Q&A card (no-options rendering) was not exercised against live data.
- **Urdu script preservation: not E2E-proven.** No Urdu fixture was parsed in this run (the Urdu NOA fixture exists but was out of M5 scope); the engine preserves script by design and the UI renders text verbatim.
- **PPSC-66 timing varies with VM load:** 146.8s (first run) vs 481.3s (rebuilt run) for the same 7-page OCR — VM contention, not a code change. M8's latencies remain the clean baseline.
- **Live Supabase: unchanged from M4.** Bucket 016 not applied (live bucket UNVERIFIED-live); the M3 live Auth confirm→login→profile loop is still unproven; the unconfirmed test user `officerpath.m3.test@gmail.com` is still to be deleted by the owner. No live data was touched.
- **iPhone Safari / Lighthouse: not verified** (M9/M10).
- **CHANGELOG.md / TEST_REPORT.md: still stale** (M4 / M0).

## 7. Incidents during this milestone (why the E2E was rebuilt)
1. **Runtime restart wiped `/tmp` mid-milestone** (the third such wipe in this project): the entire first E2E harness (`/tmp/m5-e2e`, incl. the API proof, the GoTrue stub, both E2E scripts, and the real `web/.env.local` backup) was lost — after the first API run had already produced identical counts (CA40 5.0s, PPSC-66 146.8s, bank 108/81/27/27/0/0, search 1) and the browser run had passed 7 of 13 steps. The harness was rebuilt in `~/workspace/m5-e2e/` (persistent) and the full E2E re-run from scratch; every number in §3 is from the rebuilt run.
2. **Tesseract wiped too:** the restart removed `tesseract-ocr` + `urd` data. The rebuilt run first OCR'd PPSC-66 to **0 questions in 13s** (OCR stage ~0.2s/page, 0 blocks) because only `eng`/`osd` had been reinstalled — the engine defaults to `eng+urd` and per-page failure isolation swallows the missing-language failure silently. Fixed by installing `tesseract-ocr-urd` (langs now eng/osd/urd, 5.3.4). Lesson (again): deploy must install tesseract + data files in the image; a missing language must surface, not silently empty the OCR.
3. **Harness bugs found while rebuilding** (all harness-only, none in the product): the VM's egress-proxy vars break `httpx` client construction (`Invalid port: ':1]'` from the lowercase `no_proxy` IPv6 entries — `NO_PROXY='*'` alone is not enough; all proxy vars must be unset for the engine/E2E processes); `npm start -p 3000` passes `3000` as the project directory (use `npx next start -p 3000`); the rebuilt GoTrue stub initially lacked CORS, so the browser login was blocked at the preflight (added CORS + OPTIONS).
4. **Upload response shape:** the rebuilt `api_e2e.py` first assumed flat `document_id`/`job_id` keys; the real `UploadResponse` nests them (`document.id`, `job.id`) and returns `status: "stored"` / `"replay"` for idempotent re-uploads. Fixed in the script.

## 8. What is NOT done (explicitly out of M5)
Test builder (M6), exam interface (M7), results/analytics (M8), payments/subscriptions (Phase 3), subject auto-classification (engine does not classify; manual assign only), signed question-asset serving (GAP-12 — nothing to serve), live deploy, live Supabase changes.

## 9. Teardown + one open blocker for the parent
- E2E servers stopped (stub :54399, engine :8001, web :3000 — all confirmed down). Fixtures never modified. E2E database, storage, and logs live in `~/workspace/m5-e2e/` (kept for the parent to inspect; the harness is test-only and outside the repo).
- **BLOCKER — `web/.env.local` holds STUB values.** The real-values backup was in `/tmp` and was lost in the restart; no other copy exists on the VM (searched). The file currently points at `http://127.0.0.1:54399` / `http://127.0.0.1:8001`, and the `.next` build is baked with those values. **Before any real use, the parent must restore the real values** (`NEXT_PUBLIC_SUPABASE_URL=https://gliebuyyjguxrwdfuakz.supabase.co`, the live `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`) **and rebuild the web.** The committed code is unaffected (`.env.local` is gitignored) and the stub values must never be committed.
- Commit: to be made locally on `officerpath-phase2-web` after parent verification (no push). Files: 17 paths — 8 tracked modified (+461/−5), 9 untracked paths / 10 new files (2,194 lines).

## 10. Gate verdict
**All M5 gates pass on measured evidence** (pytest 536/0, ruff clean, mypy clean, build/lint/tsc clean, OpenAPI 27, secrets 0, API + browser E2E fully green incl. the unknown-state and correction proofs), with **one real product bug found and fixed by measuring** (§5.1) and **one open parent step** (§9, `.env.local` restore). The M5 gate is met pending the parent's own re-run of the gates.
