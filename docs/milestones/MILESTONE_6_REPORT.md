# Milestone 6 Report — Matching, Validation, Calibration, Review APIs

**Date:** 2026-11-22 (work 02:46–~04:30 PKT)
**Branch:** `officerpath-phase1-engine` (local only, no push)
**Gate verdict: MET** — all M6 scope items built, measured, and passing.
All numbers below are measured in this run (VM numbers, NOT Render
numbers); anything unmeasured is labelled UNVERIFIED.

## Gate evidence (actually run, this session)

| Gate | Result |
|---|---|
| pytest (full suite) | **448 passed / 0 failed** (77.6 s) — 377 M5 baseline + 71 new M6 tests |
| ruff check | clean |
| ruff format --check | clean (164 files) |
| mypy CI gate (`mypy app/db app/pipeline app/storage`) | **SUCCESS, no issues in 68 source files** |
| Benchmark | `scripts/benchmark_m6.py` run 4 (final) → `docs/benchmarks/m6-benchmark-2026-11-22.json` + `m6-calibration.json` + `BENCHMARK_M6_2026-11-22.md` |

The broad `mypy app/` errors (~382 in tests + pre-existing skeleton
main.py) remain out of scope per pyproject.toml, as in M1–M5.

## What was built

### A. `app/pipeline/matching/` (new, 9 files + tests)

- **`models.py`** — `ResolvedMCQ` (stem + 4 options + answer +
  evidence trail: detector, confidence, precedence rank, source
  span/page) and `MatchedDocument` (counts, validation issues,
  promotion report, evidence trail per answered question). No answer
  without evidence.
- **`key_region.py`** — key-region location. Heading method +
  dense-run fallback + "none" (never guesses). Two layout-order
  rules measured on live PPSC-66 lines (see "Key-region" below):
  back-scan from the heading to the run's first entry, and
  sequence-continuation past a paper heading.
- **`promotion.py`** — pending-question promotion under ADR-007
  (new ADR): promote only on a verdict with rank in
  {manual, key, inline, style}, confidence ≥ 0.9, no conflicts,
  exactly 4 options, number not already answered. Never on `inferred`
  alone. Skipped pendings keep a recorded reason.
- **`validate.py`** — per-question validation with reason codes
  (incomplete-options, too-many-options, empty-option,
  duplicate-option, answer-out-of-range, duplicate-number,
  number-gap, missing-answer, unresolved-conflict,
  promoted-with-incomplete-options). Duplicates flagged, never
  deleted.
- **`calibration.py`** — empirical bucket calibration (buckets
  0.0–0.5, 0.5–0.7, 0.7–0.9, 0.9–1.0, 1.0; min 5 samples per
  bucket), ECE before/after.
- **`report.py`** — per-document structured report (JSON +
  markdown): counts, per-detector contribution, confidence
  distribution, pending/unknown lists with reasons, evidence trail.
- **`service.py`** — `parse_document_bytes` (the synchronous
  end-to-end entry: digital text layer, else per-page render +
  quality + `select_psm` + Tesseract + layout + extraction +
  key-region-located key detection + resolution + promotion +
  matching + validation) and `load_calibration()` (reads
  `docs/benchmarks/m6-calibration.json` when present).
- **`store.py`** — persistence + review operations on the M1
  schema (no migration needed — see below).

### B. Review APIs (`app/api/v1/review.py` + `app/schemas/review.py`)

- `POST /api/v1/documents/parse` — synchronous PDF parse; persists
  Document + Job + matched result when a database is configured,
  returns the result regardless (a bookkeeping failure never fails
  a good parse); rejects non-PDF with 422.
- `GET /api/v1/jobs/{job_id}/review` — pending/unknown items for a
  job (503 when no database, 404 for unknown/other-user jobs).
- `POST /api/v1/documents/{id}/questions/{qid}/corrections` —
  manual correction (question text / option text / answer) with an
  audit trail (`ManualCorrection` + `ReviewHistory` rows; originals
  never silently overwritten); re-runs validation after the
  correction. Manual corrections are top of precedence.
- `GET /api/v1/documents/{id}/report` — the stored document report.
- 10 API tests (in-memory SQLite + TestClient, existing auth
  fixtures).

### Schema decision (explicit, as required)

**No Alembic migration was needed.** The M1 schema already has
`extracted_questions` / `question_options` / `extracted_answers` /
`evidence` / `sources` / `extraction_reports` /
`manual_corrections` / `review_history` — verified against
`app/db/models.py` before building. Resolved MCQs, corrections and
reports persist into those tables.

### C. Per-page PSM routing (ADR-008, new)

`app/pipeline/ocr/psm.py`: `select_psm(quality)` always returns PSM
3. The 7-page experiment (re-run in full in M6, reproduced the
first run exactly) shows only p5 wants PSM 4, and p5 is not an
outlier on any M2 quality metric — no threshold separates it
without misrouting p1/p4. No quality-driven routing is fitted.
Multi-pass union merge (M5: 59/100 at 2–3× OCR cost) NOT
implemented — recorded as M7 work with the measured cost/benefit.

### D. Flutter "Server parse" toggle — PREPARED ONLY, NOT shipped

Separate repo `~/workspace/officerpath-ai/` (no `.git` locally, so
**no branch could be created** — the changes are uncommitted files
only; the intended branch name is `officerpath-server-parse-toggle`):

- `lib/services/server_parse_service.dart` (new, 275 lines):
  multipart POST to `/api/v1/documents/parse` (default base URL
  `https://officerpath-pdf-engine.onrender.com` — **not deployed
  yet**), toggle persisted in SharedPreferences
  (`server_parse_enabled`, default OFF), maps server results to the
  app's parse-maps shape. Any failure throws
  `ServerParseException` — never a silent fallback to another
  parser.
- `lib/services/pdf_import_service.dart`: `importPdf` routes to
  the server when the toggle is ON (except `key-attach` imports,
  which must stay on-device — they need the raw text the server
  does not return); requires a Supabase sign-in token.
- `lib/screens/ai_settings_screen.dart`: SwitchListTile with a
  not-deployed-yet warning, PDF-only note, photo/key-attach stay
  on-device.
- `importImage` is NOT wired (the server endpoint accepts PDFs
  only; photos need a server image endpoint — M7/server work).
- **No APK build, no release, no version bump, no push.**
  `flutter analyze` could NOT be run on the VM (no Flutter/Dart
  SDK) — the owner must run it before review. Code checked by
  inspection only.

## Measured results (run 4, VM numbers)

Full tables in `docs/benchmarks/BENCHMARK_M6_2026-11-22.md`.

### End-to-end resolved-MCQ accuracy (digital fixtures)

| Fixture | Q P/R/F1 | Options | Answers | Answered / Pending |
|---|---|---|---|---|
| TestPoint (1,375 GT) | 0.98 / 1.0 / 0.9899 | 1.0 / 0.9987 / 0.9994 | **1.0 / 1.0 / 1.0** | 1403 / 0 |
| Computer Q&A (960 GT) | 0.8846 / 0.6948 / 0.7783 | — (qa_pair) | 0.991 | 667 matched |
| CA40 | 1.0 / 1.0 / 1.0 | 1.0 / 0.9938 / 0.9969 | **1.0 / 1.0 / 1.0** | 40 / 0 |
| Urdu NOA (135 GT) | 1.0 / 0.7778 / 0.875 | 1.0 / 0.9857 / 0.9928 | **1.0 / 1.0 / 1.0** | 105 / 2 |

### Promotion (ADR-007)

Digital fixtures: no change (0 pendings to promote). **PPSC-66 live:
14 → 41 answered, 54 → 27 pending, 27 promoted** (1, 3, 4, 6–9,
29–31, 41–47, 49, 51, 52, 54, 56–58, 61, 67, 97). Still pending:
25 with "question number unknown", Q28/Q4 blocked as "number
already answered", Q99 with an UNKNOWN verdict.

### Key-region location (live PPSC-66 key)

Whole blob: P/R/F1 0.9756 / 0.80 / 0.8791 (80 TP, **2 FP**).
Region-located: **1.0 / 0.84 / 0.913 (84 TP, 0 FP)** — strictly
better on all three. Region lines 31–282, heading method. The
whole-blob's 2 FPs were both Q98-explanation hijacks (entries 1
and 2). Remaining 16 FN are OCR damage (entries 17, 18, 19, 99,
100 unparseable in live Tesseract text).

### PPSC-66 live end-to-end

Routed = unrouted (all pages PSM 3): 41 questions, 41 answered, 27
pending, 17 Q&A pairs, 1 duplicate, 0 conflicts, 3 validation
issues, 40 of 100 distinct answered numbers. Total recovered items
68 — unchanged from M5 (the OCR ceiling is unchanged; the M6 gain
is promotion + key-region turning pending items into answered
questions). M5's "41/100" counted items, not answered questions,
so it is not directly comparable to M6's "40/100 answered".

### Paper 60 live

Question detection 0.25 / 0.05 / 0.0833 — **1 of 20 questions
recovered**; that 1 is answered correctly. The M5 finding stands:
live Tesseract on this two-column photo essentially fails at
segmentation. Paper 60 needs Gemini-vision OCR (or better
segmentation). M6 did not change OCR or segmentation.

### Calibration

1,559 (raw confidence, correct) pairs. The 1.0 bucket: n=1,558,
mean confidence 1.0, **accuracy 1.0**, calibrated 1.0. **ECE 0.0003
before and after** — the detectors' confidence 1.0 is already
calibrated; the fitted mapping is the identity and no
recalibration is applied. Lower buckets have no samples (the
measured detectors never emit below 0.9 here except one 0.6 point,
which was correct) — calibration below 1.0 is UNVERIFIED, not
"correct".

### Validation issues (run 4)

TestPoint 915 (duplicate-number 899, duplicate-option 14,
empty-option 1, number-gap 1); CA40 0; Urdu NOA 1 (number-gap);
PPSC-66 live 3 (duplicate-option 2, number-gap 1). TestPoint
residual FPs still 28 (unchanged from M5 — M6 did not change
extraction, per the bounded scope).

### Peak memory

881.0 MB peak RSS (VM, whole benchmark process). VM number, not a
Render number.

## Bugs found by measuring (all fixed and re-measured in run 4)

1. **Number-only verdict join (real pipeline bug, M5/M6).**
   `apply_resolution`, `match_document` and `promote_pending` took
   the first verdict for a question number. TestPoint numbers repeat
   across sections, so end-to-end answer accuracy was 0.5084 (run
   2) although the extractor's own answers are 1.0. Fixed by
   occurrence pairing (questions) and positional alignment with a
   number-lookup fallback for partial resolutions (promotion).
   Run 4: 1.0. Regression tests added for all three joins.
2. **Calibration pairing (harness bug).** `_calibration_points`
   paired by number only — same duplicate-number problem — giving
   accuracy 0.392 at confidence 1.0 (run 2). Fixed: pair by number
   + stem similarity. Run 4: accuracy 1.0 at confidence 1.0.
3. **Stale-fit feedback (harness bug).** The benchmark loaded the
   previous run's `m6-calibration.json` while measuring, so run 3's
   points came out at mean confidence 0.392. Fixed: points use raw
   confidence, and the benchmark deletes any stale calibration file
   before parsing.
4. **Live key-GT letters (harness bug).** The PPSC-66 live key GT
   carried full entry texts as "answer", so live calibration points
   were silently 0 in runs 2–3. Fixed: extract the single letter.
   Run 4: 40 live points.
5. **Paper 60 GT stems (harness bug).** Run 1 crashed: the M5 GT
   helper returns no question text, and `_score_mcq` pairs by stem.
   Fixed with `_paper60_stem`.

Residual known limitation (not fixed in M6): extra detector
evidences still join to questions by number only inside
`resolve_document_answers`, so on a multi-section paper with a
trailing key, a key evidence from another section could attach to a
question. Full fix needs section identity through the detectors —
M7 work.

## Honest limitations / what is NOT done

- **PPSC-66 live recovery is still OCR-bound**: 41 of 100 questions
  answered; 27 pending (25 unnumberable by OCR); Q1–9 clipped at
  the page edge (ceiling ≤ 91/100). No OCR or segmentation change
  was made in M6.
- **Paper 60 live is still essentially unrecovered** (1/20) via
  Tesseract. Needs Gemini-vision OCR (key deferred by the user) or
  better segmentation.
- **Calibration below confidence 1.0 is UNVERIFIED** — no samples
  in the lower buckets on these fixtures.
- **TestPoint residual 28 FPs** unchanged (bounded scope — left as
  is, not chased).
- **Multi-pass union merge (59/100) NOT implemented** — M7 work
  with the measured 2–3× OCR cost.
- **Flutter toggle is prepare-only**: uncommitted files, no branch
  (no `.git` locally), no `flutter analyze` run, no APK, no release.
- **No push, no Render deploy, no live Supabase, no Gemini key** —
  the owner steps from M1 (GitHub App install, migration 015 live
  apply, Render deploy) are still outstanding and unchanged.
- **No live phone test**: all numbers are VM measurements. The
  Phase 1 STOP CONDITION (critical acceptance tests passing live,
  including the user's phone test on PPSC-66 / table photos /
  Paper 60) is still unmet — M6 is a local milestone, not a live
  verification.

## Files changed (engine, local only)

- New: `app/pipeline/matching/` (9 files), `app/pipeline/ocr/psm.py`,
  `app/api/v1/review.py`, `app/schemas/review.py`,
  `app/tests/test_matching_*.py` (6 files), `app/tests/test_ocr_psm.py`,
  `app/tests/test_review_api.py`,
  `app/tests/test_benchmark_m6_calibration.py`,
  `app/tests/fixtures/golden/ppsc66/ocr-live-p6p7.txt` (live Tesseract
  lines fixture), `docs/adr/ADR-007-pending-promotion-rule.md`,
  `docs/adr/ADR-008-per-page-psm-no-quality-routing.md`,
  `scripts/benchmark_m6.py`, `scripts/m6_psm_experiment.py`,
  `docs/benchmarks/m6-benchmark-2026-11-22.json`,
  `docs/benchmarks/m6-calibration.json`,
  `docs/benchmarks/m6-psm-experiment.json`,
  `docs/benchmarks/BENCHMARK_M6_2026-11-22.md`,
  `docs/milestones/MILESTONE_6_REPORT.md`.
- Modified: `app/main.py` (review router), `app/pipeline/answers/service.py`
  (occurrence pairing in `apply_resolution`),
  `app/tests/test_answers_service.py` (1 regression test).
- Untracked run logs (not committed, intermediate evidence only):
  `docs/benchmarks/m6-benchmark-run.log`,
  `docs/benchmarks/m6-psm-experiment-run.log`.

## Carried to M7

- Background jobs / security / observability / performance (M7
  scope); full test suite + deployment guide (M8).
- Multi-pass union merge for PPSC-66 (measured 59/100 at 2–3× OCR
  cost) — decide on cost/benefit.
- Section identity through detectors + key parsing (the residual
  number-join limitation above).
- Server image endpoint for photos (Flutter `importImage` path).
- TestPoint residual 28 FPs (only if cheap).
- Live verification on the user's phone (STOP CONDITION) + Render
  deploy (owner steps).
