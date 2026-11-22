# Milestone 8 — Results + Student Analytics (Phase 2)

**Branch:** `officerpath-phase2-web` · **Status:** built locally, gates run, NOT pushed, NOT deployed · **Date:** 2026-11-22
**M7 head:** `2342c4a`

## 1. What was built

### Engine (GAP-7 + GAP-8, Alembic 0008)

- **`student_question_collections`** (doc 03 §2.3, Alembic `0008_m8_collections`):
  id UUID PK, `user_id`, `question_id` FK → `extracted_questions` ON DELETE CASCADE,
  `collection_type` CHECK IN (`bookmark` / `mistake` / `custom`), `note` NULL,
  UNIQUE(user_id, question_id, collection_type). Downgrade refuses while rows exist.
- **Subject/topic breakdowns** (`app/services/results.py`, new): computed at submit
  from SAVED attempts only — the test's snapshots + the student's responses + the
  bank questions' `QuestionSubject` links. Per subject/topic:
  `{scored, correct, incorrect, unattempted, marks, max_marks, accuracy}` (Decimal 2dp).
  Only subjects actually assigned; unassigned questions go under an honest
  "Uncategorised" bucket — never a forced or invented subject. First-assignment-wins
  (earliest `QuestionSubject` row by `created_at`). Weak/strong = lowest/highest
  accuracy among NAMED subjects with ≥3 scored questions (Uncategorised excluded);
  both empty when no subject qualifies.
- **Backfill:** M7 results stored with NULL breakdowns are recomputed on read
  (`ensure_breakdowns`) and persisted — proven on the real M7-submitted row (§4e).
- **Submit wiring (M7's `app/services/exam.py`):** in the SAME submit transaction,
  after `score_answers`, the result row gets its breakdowns AND a `mistake` row is
  created for every incorrectly-answered scored question. Correct, unattempted and
  unknown questions create none; a re-submit (idempotent, same result) creates no
  duplicates.
- **Results API (OpenAPI 36 → 41 paths, +5):**
  - `GET /api/v1/tests/{id}/result` — now returns the stored row + breakdowns +
    weak/strong + `review` (per-question: snapshot text/options, `selected_index`,
    `correct_index`, evidence source, status correct/incorrect/unattempted/unknown).
    Review shows ONLY what the engine stored — no fabricated explanations.
    Unknown snapshots (`correct_index = -1`) show as unknown, never correct/incorrect.
  - `GET /api/v1/results` — paginated, owner-only, newest first.
  - `POST /api/v1/tests/{id}/retry` → 201 — new template (named `{name} (retry)`),
    new session, snapshots byte-identical to the original. Submitted-only, else
    409 `test_not_submitted`.
  - `POST /api/v1/tests/from-mistakes` → 201 — practice test from the ORIGINAL
    snapshots of the incorrectly-answered questions, never the live bank; 422
    `no_mistakes` when the notebook is empty; cap 200 most recent; unusable
    questions reported in `skipped_question_ids`.
- **Collections API:**
  `GET /api/v1/collections` (filter `?collection_type=`, enriched with the bank
  question), `POST /api/v1/collections` (bookmark/custom),
  `PATCH /api/v1/collections/{id}` (note), `DELETE /api/v1/collections/{id}`.
  **Bookmark-once rule (decided + documented): idempotent-200** — 201 first time,
  200 with `already_exists: true` after (same convention as M5 assign-subject).
  `POST` with `collection_type="mistake"` → 422 — only the submit flow writes
  mistake rows. Owner-only everywhere (foreign question/test → 404, never a leak).

### Frontend

- **Result page** `/dashboard/tests/[id]/result` (+ `result-client.tsx`): score,
  %, correct/incorrect/unattempted/unknown counts, time taken, subject + topic
  breakdown tables, weak/strong areas, per-question review with bookmark buttons.
  The exam submit summary now links here ("View full result").
- **History page** `/dashboard/results`: results newest first with retry actions;
  compare-over-time shown ONLY when ≥2 attempts exist, as a plain chronological
  marks/% list from stored results — with one attempt the page says there is no
  trend yet. No fitted trend, no prediction.
- **Mistake notebook** `/dashboard/mistakes`: mistake questions with notes
  (editable), bookmark toggle, "Practice mistakes" button (creates a new session
  from them). A bookmarks count card is shown; bookmarks are managed from review.
- **Nav:** "Results" + "Mistakes" added to the dashboard nav. Test detail page:
  submitted tests now show "View result" + "Retry this test" (replacing the
  disabled "Already submitted" button).
- **Deliberately NOT built:** no `/analytics/summary` endpoint — the history
  compare is a plain list from `GET /results` (see §6).

## 2. Gate table (exact numbers)

| Gate | Result |
|---|---|
| pytest (full) | **593 passed, 0 failed** (575 M7 baseline + 18 new M8 tests), 286.05s, 34 warnings (pre-existing deprecation warnings) |
| ruff check | clean (6 errors found in the first run — all in the new test file — fixed: unused import, 2 long lines, unused variable, 2 import sorts) |
| ruff format --check | clean (221 files; 5 files reformatted once) |
| mypy gate (`app/db app/pipeline app/storage`) | SUCCESS, 68 files, no issues |
| `npm run build` (real `web/.env.local`) | PASS — 27 page routes (+ `/icon.svg`), 3 new: `/dashboard/results`, `/dashboard/mistakes`, `/dashboard/tests/[id]/result` |
| `npm run lint` | 0 problems |
| `npx tsc --noEmit` | exit 0 |
| OpenAPI paths | 36 → **41** (+5) |
| Secrets scan (web/) | **0 offenders** — the only `eyJ` hit is a `package-lock.json` integrity hash; service-role mentions are doc comments saying never to use it |
| `web/.env.local` | untouched, real values, 0600 (checked before every build) |

## 3. Unit tests (18 new, `app/tests/test_results.py`)

Seed: 7-question matched document (6 answered + 1 unknown) with hand-assigned
subjects (Q1–Q3 → General Knowledge, Q1 also topic "Capitals"; Q4–Q5 → Current
Affairs; Q6 → none; Q7 unknown, no subject). Standard attempt: Q1/Q2/Q4 correct,
Q3/Q5 incorrect, Q6 unattempted, Q7 marked-for-review only. Hand-checked:
overall correct 3, incorrect 2, unattempted 1, unknown 1, total 2.5, max 6.0,
41.67%; GK scored 3 correct 2 incorrect 1 marks 1.75 max 3.0 accuracy 66.67;
CA scored 2 correct 1 incorrect 1 marks 0.75 max 2.0 accuracy 50.0;
Uncategorised scored 1 (Q6 unattempted) marks 0.0 max 1.0 accuracy 0.0;
topic Capitals scored 1 correct 1 marks 1.0 max 1.0 accuracy 100.0;
topic Uncategorised scored 5 correct 2 incorrect 2 unattempted 1 marks 1.5
max 5.0 accuracy 40.0; mistakes = Q3 + Q5 only. Coverage: submit breakdowns,
weak/strong distinct (reassign Q6→CA → weakest CA 33.33, strongest GK 66.67),
first-assignment-wins, backfill of NULL breakdowns, result-before-submit 404,
review items (positions, statuses, unknown `correct_index -1`), review bookmark
flag, mistake rows once + no duplicates on re-submit, history newest-first
(41.67 then 100.0), retry byte-identical snapshots + retry-requires-submitted
409, from-mistakes from original snapshots (bank correction of Q3 C→A leaves
the practice snapshot at correct_index 2) + subset + empty notebook 422,
bookmark idempotent/note/delete, mistake-create 422, owner isolation (USER_B),
Alembic 0008 fresh-DB + downgrade-refuses-with-rows.

## 4. E2E proof (`~/workspace/m8-e2e/`, M7 bank copy — 91 rows)

Harness: GoTrue stub :54399, engine :8001, web :3000; the M7 `engine.db` was
COPIED (the M7 original was never modified) and `alembic upgrade head` added
0008. Full proof in `api-proof.json` + `browser-proof.json`.

### (e) Backfill — the M7 row

M7 test `0824e256-09b8-4833-9dca-5e1ab993111b`, result `4baea094-…`:
stored 5 correct / 2 incorrect / 2 unattempted / 1 unknown, **4.5 / 9.0 = 50.0%**.
Breakdowns were JSON `null` in the copied DB before the read. After
`GET /api/v1/tests/{id}/result`: a single Uncategorised bucket, hand-checked —
scored 9, correct 5, incorrect 2, unattempted 2, marks 5.0 − 2×0.25 = **4.5**,
max 9.0, accuracy 5/9 = **55.56** — for BOTH subject and topic breakdowns.
The stored row now carries the breakdowns (recompute-on-read persisted).

### New test + hand-checked submit

Test `d95644a4-0488-4242-94fc-f4713b3860d2` ("M8 E2E exam test"), 10 questions
(9 scored + 1 unknown, picks disjoint from M7's), PPSC default, 3600s.
Subjects assigned via the real API: 3 → General Knowledge (first also topic
"Capitals"), 3 → Current Affairs, 3 → none. Answers: 4 correct, 3 incorrect,
2 unattempted, 1 unknown (marked-for-review only).

**Hand-check:** correct 4 → +4.0; incorrect 3 → −0.75; unattempted 2 → 0;
**total = 3.25; max = 9.0; percentage = 36.11%**. Server returned exactly that.

### (b) Breakdowns vs hand-computed arithmetic

| Bucket | Scored | Correct | Incorrect | Unattempted | Marks | Max | Accuracy |
|---|---|---|---|---|---|---|---|
| General Knowledge | 3 | 2 | 1 | 0 | 1.75 | 3.0 | 66.67 |
| Current Affairs | 3 | 1 | 1 | 1 | 0.75 | 3.0 | 33.33 |
| Uncategorised (subject) | 3 | 1 | 1 | 1 | 0.75 | 3.0 | 33.33 |
| Capitals (topic) | 1 | 1 | 0 | 0 | 1.0 | 1.0 | 100.0 |
| Uncategorised (topic) | 8 | 3 | 3 | 2 | 2.25 | 8.0 | 37.5 |

Weakest: Current Affairs 33.33. Strongest: General Knowledge 66.67.
Review statuses (positions 1–10): correct, correct, incorrect, correct,
incorrect, unattempted, correct, incorrect, unattempted, unknown.
The unknown item carries `correct_index -1` and no selection.

### (a) Stored row == API result, exactly

Stored `test_results` row for result `9eb2d8a7-2926-47b9-85e6-e5a23dc49396`:
`{total_marks: 3.25, max_marks: 9, percentage: 36.11, correct_count: 4,
incorrect_count: 3, unattempted_count: 2, unknown_count: 1}` — identical to
the API result, including the stored `subject_breakdown` JSON.

### Mistakes + bookmark-once

- Mistake rows: exactly **3** (the incorrectly-answered questions only);
  double-submit returned the same result id and still 3 rows.
- **(f) Bookmark-once:** first bookmark → **201**; second → **200**
  `already_exists: true`, same row id; exactly 1 bookmark row total.

### (c) Retry keeps snapshots byte-identical

Retry `10100099-edbb-4bec-a311-3900ca8a6593` ("M8 E2E exam test (retry)"):
10 snapshots, canonical JSON (minus `snapshot_id`) sha256-identical to the
original (sample hash `0fd5f3624e6229a4`).

### (d) From-mistakes — new session, only the incorrect ones

Practice test `e237574f-7bb8-492c-be9d-e1b258870314`, `source_type: "mistakes"`:
exactly the 3 incorrectly-answered questions. A bank correction applied
AFTER creation (the question's live answer changed C→A) left the practice
test's snapshots unchanged (still the original C).

### History

`GET /api/v1/results`: total **10** results, newest first (the M8 test first,
the M7 test present).

## 5. Browser proof (Playwright, stub GoTrue + local engine)

13 steps, all passed (`browser-proof.json`):

1. Login via the real UI form.
2. Result page shows the server marks: the page's N/M pairs were
   `[11/22 (the submitted date), 3.25 / 9, 0.75 / 3, 1.75 / 3, 0.75 / 3,
   1 / 1, 2.25 / 8]` — `3.25 / 9` present and equal to the server result;
   breakdown text present (General Knowledge 66.67%, Current Affairs 33.33%,
   Capitals 100%, Uncategorised, Weakest, Strongest, "Unknown answer",
   "Incorrect", "Question review").
3. Bookmark toggle on a review item: button flips to "Remove bookmark".
4. Retry from the result page → new test `ba7d0fa1-ecff-4529-a4d1-4aa041454d90`.
5. History lists results newest first with "Progress over time" (Attempt 2,
   M7's 4.5 / 9, 50% also shown).
6. Retry from history → new test `acabf27a-af37-4633-840f-98744f5f64ed`.
7. Mistakes page: **3** Mistake badges + "Practice mistakes" button →
   new session `8ac5a5e2-0c50-46a9-96d4-49948c3c04f6` ("Mistake practice").
8. Mobile 360px: **0px overflow** on result, history, and mistakes pages.

## 6. What was found by measuring (bugs + fixes)

1. **Test-seed arithmetic error (mine, not the code):** the unit seed's Q5
   ("2+2", correct B=1) was answered with index 1 and expected incorrect —
   the test expectation was wrong; fixed the seed (incorrect answer is C=2).
2. **First-assignment-wins tie:** SQLite `CURRENT_TIMESTAMP` has second
   precision, so two subject assignments created in the same second have no
   defined order. The rule still counts the question exactly once in one of
   its real subjects; the tie is now documented in the code and the unit test
   pins distinct timestamps.
3. **JSON `null` vs SQL NULL:** the JSON column stores Python `None` as the
   JSON literal `'null'` (TEXT), not SQL NULL — the E2E backfill pre-check had
   to compare the decoded JSON value, not `IS NULL`. The service logic was
   already correct (SQLAlchemy JSON deserialises `'null'` → `None`).
4. **Assign-subject route:** the E2E script called `/assign-subject`; the real
   route is `POST /api/v1/questions/{id}/subjects`.
5. **Frontend API mismatches (mine):** `Card` has no `CardContent` export;
   `ExamResult` uses `title`/`correct`/`total_questions` (not `test_name`/
   `correct_count`/`question_count`); `TestSummary` uses `test_id` (not `id`);
   `MarkingConfig` uses `incorrect_marks`; `Pagination` takes `totalPages`;
   `Textarea` requires a `label` prop. All fixed to the real APIs.
6. **Browser-proof script:** the submitted date renders as `11/22/2026`, so
   the first N/M regex match on the result page was the date — the script now
   collects all N/M pairs and requires the server marks among them; and
   `100.0%` renders as `100%` in JS, so the needle was corrected.

## 7. Honest limitations

- iPhone Safari / Lighthouse unverified (M9/M10).
- Urdu preservation not E2E-proven (no Urdu fixture this run).
- Inferred-answer flag + Q&A-pair card rendering remain unit-test-only
  (0 inferred questions in the bank; the E2E unknown question is an MCQ).
- Weak/strong with only one qualifying named subject is E2E-unproven
  (unit-tested: empty when none qualify, distinct when two qualify).
- Live Supabase unchanged: migrations 016 (bucket) + 017 (partial index)
  still unapplied, M3 auth-loop blocker + unconfirmed test user still owner
  steps.
- No `/analytics/summary` endpoint: compare-over-time is a plain
  chronological list from stored results, shown only with ≥2 attempts.
- The M8 E2E bank copy now holds the backfilled M7 breakdowns, the topic
  "Capitals", subject assignments, and the M8 test/results — the M7 original
  `~/workspace/m7-e2e/engine.db` was never modified (copy-then-upgrade).

## 8. What is NOT done (not M8)

Admin, SEO polish, deployment (M9); payments/subscriptions (Phase 3).
No push, no deploy, no paid services, no live Supabase changes.

## 9. Files changed

Engine: `alembic/versions/0008_m8_collections.py` (new), `app/db/models.py`,
`app/services/results.py` (new), `app/services/exam.py`, `app/schemas/results.py`
(new), `app/schemas/tests.py`, `app/api/v1/results.py` (new),
`app/api/v1/collections.py` (new), `app/api/v1/tests.py`, `app/main.py`,
`app/tests/conftest.py` (fixture comment), `app/tests/test_results.py` (new,
18 tests). Docs: `docs/API.md`, `docs/phase2/02-api-integration-map.md`
(GAP-7 + GAP-8 DONE). Frontend: `web/lib/api.ts`, `web/components/dashboard/
result-client.tsx` (new), `web/components/dashboard/dashboard-nav.tsx`,
`web/components/dashboard/exam-client.tsx`,
`web/components/dashboard/test-detail-client.tsx`,
`web/app/dashboard/results/page.tsx` (new),
`web/app/dashboard/mistakes/page.tsx` (new),
`web/app/dashboard/tests/[id]/result/page.tsx` (new).
Harness (outside the repo, never committed): `~/workspace/m8-e2e/`
(`setup.sh`, `gotrue_stub.py`, `api_e2e.py`, `browser_e2e.mjs`,
`api-proof.json`, `browser-proof.json`, `engine.db`).
