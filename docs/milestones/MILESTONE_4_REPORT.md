# Milestone 4 Report — MCQ Extraction (Phase 1, M4)

- **Date:** 2026-11-21
- **Branch:** `officerpath-phase1-engine` (local only — NO push; GitHub App
  install still pending, owner step)
- **Gate verdict: MET** — the extractor package is built, the golden
  dataset is v2 (38 entries), deployment-aware routing is in, the
  Nastaliq fixture is measured, and precision/recall/F1 is measured on
  every golden entry that has ground truth, including the PPSC-66
  end-to-end run from server Tesseract. The one real defect the
  benchmark caught (pdfplumber rows not consuming lines) was fixed
  and re-measured in this milestone. The PPSC-66 scanned recovery rate
  (41/100 numbers) is the known limitation carried into M5 — it is an
  OCR limitation (M3 CER 0.32–0.54 on key pages), not an extraction
  failure, and it is stated plainly below, not hidden behind the gate.
- **Quality gates (VERIFIED, re-run by the coordinator):**
  pytest **316 passed / 0 failed** (75.86 s) = 222 pre-existing + 88
  new extractor tests + 6 new consumption-fix tests; **ruff check all
  passed**, **ruff format clean** (24 files); **mypy "Success: no
  issues found in 13 source files"** (extract + digital.py).
- **No Alembic migration** — extraction results are not persisted in
  M4 (schema unchanged). No push, no live Supabase, no deploys, no
  paid services, no GCP, no Gemini key, no Gemini API calls (mock
  provider only). Flutter app untouched.

## Objective

Implement the M4 scope from audit §10: golden dataset v2; MCQ
extraction porting the Dart parser rules (question numbers, A–D and
a–d markers, sequence validation, paper-identity gate, candidate
scoring, duplicates flagged never deleted, five format paths
including the qa_pair type); deployment-aware OCR routing; a Nastaliq
fixture with an honest Tesseract measurement; and precision/recall/F1
on the golden set plus the PPSC-66 end-to-end run.

## A. Golden dataset v2 (DONE)

`app/tests/fixtures/golden/dataset.json` is now **golden-v2, 38
entries** (19 v1 + 18 v2 + 1 Nastaliq), reproducible via
`scripts/build_golden_dataset.py`, md5-stable. The `paper60-photo`
entry is fixed (source `ppsc66/paper60-photo.jpg`, reference_kind
`gemini_reference`, reference_file
`ppsc66/paper60_gemini_ocr.txt`) — the photo was viewed: "PAPER 60
— DATA ENTRY OPERATOR (Police)", Q1–Q21, answers star-marked. All 18
new fixtures copied md5-verified into `app/tests/fixtures/golden/ppsc66/`.

Ground truth was extracted programmatically (counts verified = list
lengths; never hand-typed, never cross-applied) via
`scripts/extract_golden_v2_ground_truth.py`:

- **TestPoint:** `ground_truth_testpoint_1000.json`, **1,375 rows** —
  "1000" is NOT the count; Sr# restarts per topic section (12
  restarts; Sr# 1–479; 44 values occur 8×); rows keyed by (page, sr).
- **Computer Q&A:** `ground_truth_computer_qa.json`, **960 pairs**;
  gaps 670/860 absent from the text layer; 643/644 each carry TWO
  different questions in the source; 4 pairs (8, 61, 396, 869) have no
  separable answer — left empty, never invented.
- **CA40:** `ground_truth_ca40.json`, **40/40**; answers from bold
  "Correct Answer: X) …" lines; 0 mismatches.
- **Urdu NOA:** `ground_truth_urdu_noa.json`, **135 questions**,
  lowercase answers; 129 with "(Correct)" answers, 5 without (39, 55,
  107, 110, 120), Q54 double-marked, 16 missing an option letter;
  text layer jumbled (blocks out of reading order).
- **Monthly CA ×5:** `extracted_ca_monthly_{march,april,june,july,pakistan_august}_2025.json`,
  **125 questions total** (Mar 25, Apr 27, Jun 30, Jul 25, Aug 18),
  **answers UNKNOWN**. Mechanism DETERMINED by a span-by-span check
  of all 5 files (500 option spans): question stem bold, **every
  option span non-bold (flags=0) and black** — 0 bold/coloured option
  spans; no "Correct Answer" line; the explanation matches exactly
  one option in only 64/125 (none in 55, >1 in 6), with contradictions
  (June Swat floods: explanation "at least eight dead" matches no
  option 5/9/12/15; April IT exports: explanation "$317 million"
  matches none of $3B/$4B/$5.2B/$6B). `answer: null` for all; the 2
  images per content page were NOT OCR'd — whether they carry answers
  is UNKNOWN.
- **Pak Study:** `extracted_pak_study_1000_ranges.json`, **1,032
  questions, Q1–1032, no gaps**; NO answer marking anywhere (0 hits
  for "(Correct)"/"Correct Answer"/"Ans:"/"Answer:"); 5 zero-char
  pages (34, 89, 134, 181, 280); pp. 273–280 back matter.
- Scanned (Science/Math/S&GAD/Capsule/History notes) + Pak Affairs
  notes: reference_kind none, no ground truth fabricated.

## B. MCQ extraction — `app/pipeline/extract/` (DONE)

12 files: `models.py`, `numbers.py`, `markers.py`, `signals.py`,
`keys.py`, `blocks.py`, `qa.py`, `tables.py`, `scoring.py`,
`validate.py`, `service.py`, `__init__.py`. Verbatim Dart-parser
port per `docs/milestones/M4_DART_PARSER_PORT_SPEC.md` plus the
specified additions. 88 new tests in 10 files under `app/tests/test_extract_*.py`.

Ported rules (measured, not asserted): question-number regex +
OCR-misread fallback (`decodeOcrNumber`); A–D and a–d markers;
category separation (digits only in number slots, letters only in
option markers); Urdu text preserved exactly; sequence validation
(1..N contiguous, gaps/duplicates reported); paper-identity gate
(never merge across documents); candidate scoring with per-candidate
confidence; duplicates flagged, never deleted; exactly-4 rule with
5→4 normalisation; precedence answer-line > key > tick > bold >
asterisk > AI (parked); bold = U+E000 marker; asterisk = trailing
`*` only; key sections as token stream, first-wins, strict paper
rule, `decideKeyMatch` ladder, orphan-key adoption (5 conditions +
80% threshold); confidence per-question only (answer-line/key 1.0,
tick/bold/asterisk/flashcard 0.9, manual 1.0, ai 0.5, unknown 0.0;
unverified ×0.6; OCR tick/bold → unverified 0.54).

Five format paths, each with its own tests:

1. Two-column prose MCQs (PPSC-66 style, from server OCR text).
2. Table MCQs (Sr# | Question | A | B | C | D | Ans) — digital
   (pdfplumber) and OCR text (line-based).
3. Inline-answer MCQs (monthly CA: question + A–D + explanation —
   mechanism determined: NO marking exists, answers UNKNOWN).
4. Q&A without options (Computer Past Papers) — first-class
   `qa_pair` type, question + answer, NO options; the extractor
   NEVER fabricates 4 options for these (0 MCQs detected on that
   file).
5. Lowercase option markers (Urdu NOA).

**D1–D18 — all applied as assigned:** D1 Urdu-digit normalisation
(matching only) · D2 OCR line order as given · D3 clipped →
numberless interpolation · D4 OCR tick/bold → unverified 0.54 · D5
highlight/colour/italic/circle/underline/cross/OMR explicit
non-support · D6 3-option excluded (Urdu NOA Q25/Q33 correctly
excluded) · D7 no one-line splitter · D8 Sr# delimiter path
(pdfplumber + line-based; M4 addition, see defect below) · D9 caps
kept, 3/960 Computer answers over caps measured · D10 seeded
`Random(20261121)` · D11 unmatched-key reporting with mechanism ·
D12 separate `validate.py` · D13 paper-identity fields on the Python
question record (nullable, never wildcard) · D14 unknown subjects
stay "unknown" (deliberate change from the Dart wart that mapped
them to GK) · D15 separately attached key NOT in M4 (M5/M6) · D16
measured (38 lines, splitting UNVERIFIED) · D17 `bold_lines` +
U+E000, OCR bold never approximated · D18 multi-letter answers →
null → pending.

**Changed outside the package:** `app/pipeline/ocr/digital.py`
only — per-line bold `style["bold_lines"]` (D17). Nothing else
under `app/pipeline/ocr/`, no dataset/build-script/ground-truth
changes by the implementer, Flutter untouched except reading.

## C. Deployment-aware OCR routing (DONE)

`app/pipeline/ocr/deployment.py` — profiles `render-free` (512 MB) /
`vps` (4096 MB) / `local` (8192 MB); PaddleOCR gated at ≥4096 MB,
above the M3 worst measured peak 3,667 MB; unknown profile raises
ValueError. `route_page(..., deployment=)` filters gated engines
before preference; `run_ocr_stage` resolves the profile from
settings, logs exclusions once per document, records per-page
`engines_excluded_by_deployment`. Config adds `deployment_profile:
str = "local"`, `memory_budget_mb: int | None = None`;
`render.yaml` sets `DEPLOYMENT_PROFILE=render-free` +
`PADDLEOCR_ENABLED=false`; `.env.example` updated.
**ADR-006 written** (`docs/adr/ADR-006-deployment-aware-ocr-routing.md`).
17 new tests in `app/tests/test_ocr_deployment.py` — 27 passed with
router tests, ruff + mypy clean.

## D. Nastaliq fixture (DONE)

Noto Nastaliq Urdu exists on the VM (Regular + Bold); PIL has raqm +
harfbuzz. `scripts/render_nastaliq_fixture.py` renders
`app/tests/fixtures/golden/synthetic-nastaliq/nastaliq-p1.png`
(1654x2339, 4 Urdu MCQs, ground truth in `nastaliq-p1.txt`). A
defect was caught and fixed on visual check: Nastaliq has no Latin
A–Z, so `(A)` markers first rendered as `.notdef` boxes — markers
now drawn separately in DejaVu Sans; fixed image visually verified.
**Tesseract 5.3.4 eng+urd PSM 3: CER 0.5933** (clean re-measurement
18.39 s, 16 blocks, ref 328 chars, hyp 205 chars — identical to the
contended run, so contention was NOT the cause). Tesseract cannot
carry Nastaliq; no Nastaliq claim for Tesseract. Nastaliq dataset
entry added; `config.benchmark_dataset_version` updated
`golden-v1` → `golden-v2`.

## E. Measurement — precision / recall / F1 (DONE)

Full tables in `docs/benchmarks/BENCHMARK_M4_2026-11-21.md` (+ JSON).
Benchmark script: `scripts/benchmark_m4.py` (total run 2517.9 s,
peak RSS 551.8 MB, VM numbers).

| Fixture | Question P/R/F1 | Option P/R/F1 | Answer P/R/F1 |
|---|---|---|---|
| TestPoint 1000 | 0.8472 / 1.0 / 0.9173 | 1.0 / 0.9987 / 0.9994 | 1.0 / 1.0 / 1.0 |
| Computer Q&A | 0.8846 / 0.6948 / 0.7783 | n/a | 0.991 / 0.991 / 0.991 |
| CA40 | 1.0 / 1.0 / 1.0 | 1.0 / 0.9938 / 0.9969 | 1.0 / 1.0 / 1.0 |
| Urdu NOA | 1.0 / 0.7926 / 0.8843 | 1.0 / 0.986 / 0.9929 | 1.0 / 1.0 / 1.0 |
| CA monthly ×5 | ~0 (GT/matching limitation — counts track) | 1.0 on matched pairs | n/a (answers unknown) |
| Pak Study (numbers) | P 0.9989 / R 0.8944 / F1 0.9438 | — | — |

**Overall (digital MCQ fixtures): Q 0.7976 / 0.9104 / 0.8503 ·
Options 1.0 / 0.9977 / 0.9989 · Answers 1.0 / 1.0 / 1.0.**

**PPSC-66 end-to-end (live Tesseract 5.3.4 eng+urd PSM 3, 200 DPI,
2063.9 s OCR + 0.11 s extract):** digital text layer 0 chars on all
7 pages. **Questions 14, pending 54, 41/100 numbers recovered**, all
14 questions 4/4 options. Key sections 1, **key entries applied 13,
unmatched 7** (21, 22, 23, 24, 29, 30, 31). Suspected mechanism
(D11): numbering gap — Q10–Q24 entirely missing from OCR text,
Q68–Q96 missing (29); those questions were never detected, so their
key entries have nothing to join. p7 key parsed live: 27 entries,
including OCR-noise numbers 1088/1258/1335/2021 and Paper-67 numbers
86–99 mixed in. Duplicates: Q4×2, Q28×2. Skipped 76, excluded 51.
Stored-Tesseract whole-document run: 17 questions + 77 pending, key
applied 16, unmatched 39. Table photos: computer Q67–81 → 4 pending
of 15 rows; interjection Q230–257 → 5 pending of 28. Paper 60
(Gemini text): 17/21, all 4/4.

### The consumption defect (found by the benchmark, fixed, re-measured)

Run 5 measured TestPoint question precision at 0.5403 (FP 1170).
Cause: a real extractor defect — the D8 pdfplumber fallback rows
were appended but contributed nothing to the consumed-line set, so
the grid pass re-parsed 580 rows as numberless phantoms and the
block pass re-parsed 364 more (580 + 364 + 226 pending = 1170
exactly). The fix (`match_pdfplumber_rows_to_lines` in `tables.py`,
wired into `extract_document`) also had to solve four layers the
measurement exposed: bare Sr# lines are noise-filtered so they
cannot anchor (anchor on the question stem); pdfplumber option cells
carry markers ("A. from") while line rests do not; options wrap
across lines; and the table header block ("Sr# / Question / A / B /
C / D / <type label> / Ans / Key") was unconsumed and assembled
into phantoms. 6 new tests (5 unit + 1 full-file regression test:
every ground-truth (page, Sr#) pair appears exactly once).
Re-measured: FP 1170 → 248, question precision 0.5403 → 0.8472,
F1 0.7015 → 0.9173, overall question F1 0.6764 → 0.8503.

**Residual (not fixed):** 248 FP = 218 numberless phantoms + 30
pending. Mechanism documented with evidence: in long-option
sections (e.g. Active and Passive Voice, p8) the line-stream order
does not follow the table's row order — option lines interleave
across rows, so the adjacency-based matcher leaves them free and
the grid/block passes assemble them into phantoms; the per-page
promo line is also assembled as a stem. Fixing this needs
non-adjacent / positional matching — M5 follow-up.

## Implemented (files changed)

**New — extraction (`app/pipeline/extract/`):** `__init__.py`,
`models.py`, `numbers.py`, `markers.py`, `signals.py`, `keys.py`,
`blocks.py`, `qa.py`, `tables.py` (incl. the consumption fix),
`scoring.py`, `validate.py`, `service.py`.
**New — routing:** `app/pipeline/ocr/deployment.py`.
**Changed:** `app/pipeline/ocr/digital.py` (D17 bold lines),
`app/pipeline/ocr/router.py`, `app/pipeline/ocr/service.py`,
`app/config.py`, `render.yaml`, `.env.example`, `README.md`,
`CHANGELOG.md`, `app/tests/fixtures/golden/dataset.json`,
`app/tests/fixtures/golden/ppsc66/PROVENANCE.md`,
`app/tests/test_golden_dataset.py`,
`scripts/build_golden_dataset.py`.
**New — scripts:** `scripts/extract_golden_v2_ground_truth.py`,
`scripts/render_nastaliq_fixture.py`, `scripts/benchmark_m4.py`.
**New — tests:** 10 files `app/tests/test_extract_*.py` (88 tests),
`app/tests/test_ocr_deployment.py` (17 tests), plus 6
consumption-fix tests.
**New — docs:** `docs/milestones/M4_DART_PARSER_PORT_SPEC.md`,
`docs/adr/ADR-006-deployment-aware-ocr-routing.md`,
`docs/benchmarks/BENCHMARK_M4_2026-11-21.md` (+
`docs/benchmarks/m4-benchmark-2026-11-21.json`), this report.
**New — fixtures:** 18 files + ground-truth JSONs under
`app/tests/fixtures/golden/ppsc66/`, Nastaliq fixture under
`app/tests/fixtures/golden/synthetic-nastaliq/`.

## Honest limitations / what is NOT done

- **PPSC-66 scanned recovery is 41/100 numbers (14 questions).**
  The extractor is not the bottleneck — live Tesseract loses whole
  question ranges (Q10–Q24, Q68–Q96) and the p6–p7 key pages are
  CER 0.32–0.54 (M3). Any claim of "PPSC-66 solved" would be false.
  M5 (answer detection) and the Gemini-advisory path (needs the
  deferred server key) are the routes that can move this number.
- **248 TestPoint false positives remain** (218 numberless phantoms
  + 30 pending) — non-adjacent matching needed (M5).
- **CA monthly per-question P/R/F1 is ~0** — a ground-truth/matching
  limitation (fragment ground truth vs full-sentence stems), not
  extractor failure; and their **answers are UNKNOWN** (no marking
  mechanism exists in the text layer; the 2 images per content page
  were never OCR'd).
- **Computer Q&A recall 0.6948** — 293 pairs missed, mostly the
  two-question rows (643/644) and the 4 no-separable-answer pairs.
- **Urdu NOA recall 0.7926** — jumbled text-layer order; no
  geometry-based reordering attempted.
- **D8 line-based Sr# path has zero benchmark coverage** (unit tests
  only) — TestPoint never triggers it. D16 inline-option splitting
  correctness is UNVERIFIED (38 lines measured, not scored).
- **No hand-verification** of any extracted ground truth (all
  programmatic). Scanned fixtures with no ground truth were not
  scored and nothing was fabricated. Capsule of GK (195pp) was never
  OCR'd.
- **No PaddleOCR in this benchmark** (ADR-005). No Gemini API calls.
- **Run history:** run 2 crashed on a key-join `TypeError`
  (fixed + regression test); run 3 crashed at `_aggregate`
  (Computer QA `None` options — fixed); run 4 was killed by a
  runtime restart mid live-PPSC-66 (its JSON was lost); run 5
  completed (42 min). TestPoint re-scored after the consumption fix.
- **Owner steps still outstanding (blockers, not code failures):**
  GitHub App install + push; migration 015 live apply; Render
  deploy; Gemini server key (deferred by the user).
