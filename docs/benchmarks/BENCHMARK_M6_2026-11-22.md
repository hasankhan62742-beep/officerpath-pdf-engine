# Benchmark M6 — 2026-11-22

Matching, validation, confidence calibration, reports + review APIs,
pending promotion, key-region location, per-page PSM routing.
Machine-readable companion: `m6-benchmark-2026-11-22.json`,
`m6-calibration.json`, `m6-psm-experiment.json`.
**All timings and peak memory are VM numbers (4 vCPU / 8 GB class VM),
NOT Render numbers.** Render free is 0.1 CPU / 512 MB and will be
several-times slower; the PaddleOCR-free path measured here is the
only one that fits it.

## How this run was produced

`scripts/benchmark_m6.py`, run 4 (final). Runs 1–3 are superseded and
their numbers are NOT reported here except where a bug they exposed
is documented below:

- Run 1 crashed at the Paper 60 section (`KeyError: 'text'` — the M5
  GT helper returns `{number, options, starred}`, no stem) and wrote
  no JSON. Fixed with `_paper60_stem` (stem extracted from the Gemini
  reference text).
- Run 2 completed but its calibration was wrong (see "Bugs found by
  measuring") and its TestPoint answer accuracy was 0.5084 (a real
  pipeline bug — the number-only verdict join, see below).
- Run 3 completed but its calibration consumed run 2's stale fit
  (points came out at mean confidence 0.392 — the fit chasing its own
  tail). Fixed: points use raw confidence, and the benchmark deletes
  any stale `m6-calibration.json` before parsing.
- Run 4 (this file) has all fixes. PPSC-66 live reproduced runs 2–3
  exactly (41 questions, 41 answered, 27 pending); the digital
  fixtures reproduced every earlier run exactly.

Tesseract 5.3.4 (eng+urd+osd) was reinstalled on the VM after a VM
replacement wiped it; the PSM experiment was re-run in full and
reproduced the first run's per-page numbers exactly.

## End-to-end resolved-MCQ accuracy (digital fixtures)

"Fully correct" = stem + 4 options + answer all match ground truth
(`_score_mcq`: number + stem similarity ≥ 0.85 pairing).

| Fixture | Q P / R / F1 | Options P / R / F1 | Answers P / R / F1 | Questions | Answered | Pending | Time |
|---|---|---|---|---|---|---|---|
| TestPoint (1,375 GT) | 0.98 / 1.0 / 0.9899 (1375/28/0) | 1.0 / 0.9987 / 0.9994 (5493/0/7) | **1.0 / 1.0 / 1.0** (1375/0/0) | 1403 | 1403 | 0 | 21.3 s |
| Computer Q&A (960 GT) | 0.8846 / 0.6948 / 0.7783 (667/87/293) | — (qa_pair, no options) | 0.991 (661/6/6) | 754 detected | — | — | 1.0 s |
| CA40 (40 GT) | 1.0 / 1.0 / 1.0 | 1.0 / 0.9938 / 0.9969 (159/0/1) | **1.0 / 1.0 / 1.0** | 40 | 40 | 0 | 0.1 s |
| Urdu NOA (135 GT) | 1.0 / 0.7778 / 0.875 (105/0/30) | 1.0 / 0.9857 / 0.9928 (414/0/6) | **1.0 / 1.0 / 1.0** (104/0/0) | 105 | 105 | 2 | 0.3 s |

Notes:

- TestPoint answers are 1.0 end-to-end in run 4. In run 2 they were
  0.5084 — the M5/M6 verdict joins keyed by question number only,
  and TestPoint Sr# restarts per section (1,375 rows, 476 unique
  numbers), so every Q5 got the first section's answer. Fixed in M6
  by occurrence pairing (k-th question with number N takes the k-th
  verdict for N; promotion uses positional alignment with a
  number-lookup fallback for partial resolutions). Regression tests:
  `test_duplicate_numbers_keep_their_own_answers`,
  `test_match_document_pairs_duplicate_numbers_by_occurrence`,
  `test_duplicate_numbers_take_their_own_verdicts`.
- TestPoint still has 28 residual FPs (unchanged from M5) and 1,184
  duplicate-number flags (the Sr# restarts — flagged, never deleted).
  Validation issues on TestPoint: 915 (see "Validation" below).
- Computer Q&A: question recall 0.6948 is an extraction limit (M4),
  unchanged by M6; the 667 matched pairs answer at 0.991.
- Urdu NOA: 30 GT questions not detected (extraction recall 0.7778,
  M4 limit); the 105 detected answer at 1.0; 2 still pending.

## Pending-question promotion (ADR-007)

| Case | Before | After | Promoted |
|---|---|---|---|
| TestPoint (digital) | 1403 answered / 0 pending | 1403 / 0 | 0 |
| CA40 (digital) | 40 / 0 | 40 / 0 | 0 |
| PPSC-66 live OCR | 14 answered / 54 pending | **41 answered / 27 pending** | **27** |

Promoted live numbers: 1, 3, 4, 6, 7, 8, 9, 29, 30, 31, 41–47, 49,
51, 52, 54, 56–58, 61, 67, 97. The 27 still pending: 25 with
"question number unknown" (OCR could not even number them), Q28 and
Q4 blocked as "number already answered by another question", Q99
with an UNKNOWN verdict (its key entry is unparseable in live OCR).
No promotion ever happened on an `inferred` verdict alone or below
confidence 0.9 (ADR-007).

## Key-region location (live PPSC-66 key, 282 OCR lines)

| Path | Entries parsed | Applied | P / R / F1 vs Gemini key | TP | FP | FN |
|---|---|---|---|---|---|---|
| Whole blob (M5 way) | 93 | 82 | 0.9756 / 0.80 / 0.8791 | 80 | **2** | 20 |
| Region-located (M6) | 93 | 84 | **1.0 / 0.84 / 0.913** | **84** | **0** | 16 |

Region: lines 31–282 (of 282), method `heading`, evidence "key
heading: 'ANSWER KEY: Model Paper 66'; key run starts 27 lines
above the heading". Two layout-order facts drove the design, both
measured on the live lines:

1. The key's first column (entries 1–20) precedes the heading in
   layout order — a heading-only start loses 15 true positives. The
   back-scan walks up from the heading over entry-like lines whose
   numbers strictly decrease going up (any decrease counts; OCR
   drops entries), allowing gaps of ≤ 4 non-entry lines; a number
   that does not decrease (an explanation item above the key) or a
   longer gap ends the scan. The explanation items "1. (A)
   Possessed" / "2. (B) Privileged" are excluded by both guards.
2. The "MODEL PAPER 67" heading sits BEFORE key entries 90–100 in
   layout order — a naive first-heading cut loses them. A paper
   heading ends the region only when the entry numbers after it do
   NOT continue the ascending sequence (a restart means the next
   paper's key); when they continue, the heading is a layout
   artifact and scanning continues.

The whole-blob's 2 FPs were both explanation hijacks (entries 1 and
2). The region's remaining 16 FN are OCR damage: entries 17, 18,
19, 99, 100 are unparseable in live Tesseract text (e.g. "i 99. (A)
Goes", "100.Choose the right option…" merged into the previous
line) plus 11 more garbled entries. The region is pinned by a live
fixture test (`ocr-live-p6p7.txt`, Tesseract PSM 3 layout-ordered).

## PPSC-66 live end-to-end (Tesseract, single path)

Routed (per-page PSM selection) and unrouted (PSM 3 everywhere) are
**identical**: 41 questions, 41 answered, 0 unknown, 27 pending, 17
Q&A pairs, 1 duplicate, 0 conflicts, 3 validation issues,
recovered 40 of 100 distinct answered numbers. Routed 130.0 s,
unrouted 126.1 s (difference is OCR timing noise).

Comparison with M5 (same 68 recovered items: 14 questions + 54
pending in M5, 41 + 27 in M6 — the OCR ceiling is unchanged; the
M6 gain is all promotion + key-region, turning pending items into
answered questions):

| | M5 | M6 |
|---|---|---|
| Answered questions (live) | 14 | **41** |
| Pending | 54 | **27** |
| Total recovered items | 68 | 68 |
| Distinct answered numbers of 100 | — (M5 counted items, not answered) | 40 |

M5's "41/100" counted distinct numbers across questions + pending;
M6's "40/100" counts distinct numbers among answered questions
only. The two are not directly comparable; the honest comparison is
answered 14 → 41 with total items unchanged at 68 — the OCR
ceiling (Q1–9 clipped at the page edge, ceiling ≤ 91/100) is
unchanged.

## Paper 60 live (photo, Tesseract)

| | P / R / F1 |
|---|---|
| Question detection (of 20 GT) | 0.25 / 0.05 / 0.0833 (1 TP, 3 FP, 19 FN) |
| Option extraction | 1.0 / 0.5 / 0.6667 (2/0/2) |
| Answer correctness (on the 1 matched) | 1.0 (1/0/0) |

4 questions detected, 4 pending, 0 promoted, 29.1 s. This
reproduces the M5 finding through the M6 pipeline: live Tesseract
on this two-column photo essentially fails at segmentation (the
columns merge), so only 1 of 20 questions is recovered — though
that 1 is now answered correctly (run 2 had it wrong: the old
number-only join gave it another question's verdict). Paper 60
needs Gemini-vision OCR (or better segmentation), not Tesseract.
That is a measurement, not a fix — M6 did not change OCR or
segmentation.

## Confidence calibration

1,559 (raw confidence, correct) pairs: 1,375 TestPoint + 40 CA40 +
104 Urdu NOA + 40 PPSC-66 live (the live points were 0 in runs 2–3
because the key-GT "answer" field held the full entry text, not the
letter — fixed in run 4).

| Bucket | n | Mean conf | Accuracy | Calibrated |
|---|---|---|---|---|
| 0.0–0.5 | 0 | — | — | — |
| 0.5–0.7 | 1 | 0.6 | 1.0 | — (below 5 samples, raw kept) |
| 0.7–0.9 | 0 | — | — | — |
| 0.9–1.0 | 0 | — | — | — |
| 1.0 | 1,558 | 1.0 | **1.0** | **1.0** |

**ECE 0.0003 before and after.** The detectors' confidence 1.0 is
already calibrated (accuracy 1.0 on 1,558 predictions); the fitted
mapping is the identity for the populated bucket and no
recalibration is applied. The single 0.6-confidence point (a live
PPSC-66 question) was correct. No confidence below 0.9 is ever
emitted by the measured detectors on these fixtures — the lower
buckets are empty, so calibration below 1.0 is UNVERIFIED (no
samples), not "correct".

## Per-page PSM experiment (ADR-008)

Measured quality (M2 metrics) + Tesseract PSM 3 vs 4 recovery per
page, vs Gemini references. Re-run in full in M6; reproduced the
first run's numbers exactly.

| Page | Blur | Contrast | Ink | PSM 3 recovered / CER | PSM 4 recovered / CER | Better |
|---|---|---|---|---|---|---|
| p1 | 1656.8 | 62.1 | 0.091 | 0/8, 0.0742 | 0/8, 0.6586 | 3 |
| p2 | 2274.7 | 62.5 | 0.092 | 9/21, 0.1268 | 11/21, 0.7170 | 3 (CER) |
| p3 | 2480.9 | 65.1 | 0.099 | 16/19, 0.0623 | 7/19, 0.7006 | 3 |
| p4 | 1951.6 | 57.4 | 0.082 | 9/20, 0.1024 | 9/20, 0.7180 | 3 (CER) |
| p5 | 2002.8 | 60.6 | 0.087 | 4/19, 0.7149 | 9/19, 0.1397 | **4** |
| p6 | 2167.3 | 66.1 | 0.105 | 76/82, 0.0669 | 45/82, 0.3329 | 3 |
| p7 | 2203.9 | 65.0 | 0.097 | 21/33, 0.4030 | 5/33, 0.7313 | 3 |

Only p5 wants PSM 4, and p5 is not an outlier on any measured
metric (p4 is lower than p5 on blur, contrast and ink yet wants
PSM 3 by CER 0.102 vs 0.718). Noise is 0.0, skew 0/None,
brightness 228–234 on every page — no signal. Any threshold
catching p5 also misroutes p1/p4. Conclusion (ADR-008):
`select_psm` always returns PSM 3 (the measured-best single path);
no quality-driven routing is fitted. The multi-pass union merge
(M5: 59/100 at 2–3× OCR cost) was NOT implemented — recorded as M7
work with the measured cost/benefit.

## Validation

Per-question validation runs on every matched document (codes:
incomplete-options, too-many-options, empty-option,
duplicate-option, answer-out-of-range, duplicate-number,
number-gap, missing-answer, unresolved-conflict,
promoted-with-incomplete-options). Counts in run 4:

| Fixture | Validation issues |
|---|---|
| TestPoint | 915 = duplicate-number 899, duplicate-option 14, empty-option 1, number-gap 1 |
| CA40 | 0 |
| Urdu NOA | 1 = number-gap 1 (missing 25, 33, 40, 42–45, 54–57, 69, 78, 80, 84, 87, 94–96, 103, …) |
| PPSC-66 live | 3 = duplicate-option 2 (one question's options B and C both duplicate A — OCR damage), number-gap 1 |

Validation failures are reported per-question with a reason code,
never silently dropped; duplicates stay flagged, never deleted.

## Bugs found by measuring (all fixed and re-measured in run 4)

1. **Number-only verdict join (real pipeline bug, M5/M6).**
   `apply_resolution`, `match_document` and `promote_pending` took
   the first verdict for a question number. TestPoint numbers repeat
   across sections, so end-to-end answer accuracy was 0.5084 (run
   2) although the extractor's own answers are 1.0. Fixed by
   occurrence pairing (questions) and positional alignment with a
   number-lookup fallback (promotion). Run 4: 1.0.
2. **Calibration pairing (harness bug).** `_calibration_points`
   paired by number only — same TestPoint duplicate-number problem —
   giving accuracy 0.392 at confidence 1.0 (run 2). Fixed: pair by
   number + stem similarity (the `_score_mcq` pairing). Run 4:
   accuracy 1.0 at confidence 1.0.
3. **Stale-fit feedback (harness bug).** The benchmark loaded the
   previous run's `m6-calibration.json` while measuring, so run 3's
   points came out at mean confidence 0.392. Fixed: points use raw
   confidence, and the benchmark deletes any stale calibration file
   before parsing.
4. **Live key-GT letters (harness bug).** The PPSC-66 live key GT
   carried full entry texts ("(B) Broke out") as "answer", so the
   live calibration points were silently 0 in runs 2–3. Fixed:
   extract the single letter. Run 4: 40 live points.
5. **Paper 60 GT stems (harness bug).** Run 1 crashed: the M5 GT
   helper returns no question text, and `_score_mcq` pairs by stem.
   Fixed with `_paper60_stem` (stem from the Gemini reference).

Residual known limitation (not fixed in M6): extra detector
evidences still join to questions by number only inside
`resolve_document_answers`, so on a multi-section paper with a
trailing key, a key evidence from another section could attach to
a question (the M4 inline answer is per-object and safe; only the
extra-evidences join is number-keyed). Full fix needs section
identity through the detectors — M7 work.

## Peak memory

Peak RSS 881.0 MB (VM, whole benchmark process including the
Tesseract subprocesses). VM number, not a Render number.
