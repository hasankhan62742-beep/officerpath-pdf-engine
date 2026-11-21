# Benchmark M4 — MCQ extraction on golden dataset v2

- **Date:** 2026-11-21
- **Dataset:** golden v2 (`app/tests/fixtures/golden/dataset.json`, 38 entries)
- **Hardware (VERIFIED):** dev VM, 4 vCPU, 8 GB RAM (shared cell, 1.5 CPU
  quota), Python 3.12. **All timings and memory numbers are VM numbers.
  They are NOT Render numbers** (Render free is 0.1 CPU / 512 MB).
- **Extractor:** `app/pipeline/extract` (Dart parser port, M4) — models,
  numbers, markers, signals, keys, blocks, qa, tables, scoring,
  validate, service. No PaddleOCR in this benchmark (ADR-005
  deployment gate + OOM risk). No Gemini API calls; Gemini reference
  texts used for question counts only.
- **Method:** `scripts/benchmark_m4.py` → `docs/benchmarks/m4-benchmark-2026-11-21.json`.
  Matching: normalised text similarity ≥ 0.85 (difflib) AND numbers
  agree when both have numbers; options per-letter ≥ 0.85; answers by
  letter (answer text for qa_pair). Pending questions count as detected
  for question recall. Total run 2517.9 s, peak RSS 551.8 MB (VM).
- **Re-score note (VERIFIED):** the TestPoint section was re-scored
  after a real extractor defect was found by the benchmark (see
  "The consumption defect" below). Run-5 TestPoint question P/R/F1 was
  0.5403/1.0/0.7015; after the fix it is 0.8472/1.0/0.9173. The fix and
  re-score are recorded in the JSON (`rescored` note on the fixture,
  top-level notes). All other sections are run-5 numbers; the overall
  aggregates were recomputed from the re-scored section.

## Headline results (VERIFIED)

| Fixture | Question P/R/F1 | Option P/R/F1 | Answer P/R/F1 | Detected / GT |
|---|---|---|---|---|
| TestPoint 1000 (digital table) | 0.8472 / 1.0 / 0.9173 | 1.0 / 0.9987 / 0.9994 | 1.0 / 1.0 / 1.0 | 1623 / 1375 |
| Computer Q&A (qa_pair) | 0.8846 / 0.6948 / 0.7783 | n/a | 0.991 / 0.991 / 0.991 | 754 / 960 |
| CA40 (digital) | 1.0 / 1.0 / 1.0 | 1.0 / 0.9938 / 0.9969 | 1.0 / 1.0 / 1.0 | 40 / 40 |
| Urdu NOA (digital, lowercase markers) | 1.0 / 0.7926 / 0.8843 | 1.0 / 0.986 / 0.9929 | 1.0 / 1.0 / 1.0 | 107 / 135 |
| CA monthly Mar/Apr/Jun/Jul/Aug (digital) | 0 / 0.032 / 0.029 / 0.037 / 0 | 1.0 on the 1 matched pair each | n/a (answers unknown) | 29/31/34/27/21 vs 25/27/30/25/18 |
| Pak Study (numbers only) | P 0.9989 / R 0.8944 / F1 0.9438 | — | — | 924 / 1032 numbers |

**Overall (digital MCQ fixtures): Q 0.7976 / 0.9104 / 0.8503 ·
Options 1.0 / 0.9977 / 0.9989 · Answers 1.0 / 1.0 / 1.0**
(tp 1525/6086/1519). Synthetic clean p1/p2: 0 questions + 4 pending
each (answerless → pending, correct per spec §6.18). Nastaliq on
ground-truth lines: 4 pending, 4/4 options complete.

## The consumption defect — found by the benchmark, fixed, re-measured (VERIFIED)

Run 5 measured TestPoint question precision at 0.5403 with FP 1170.
The cause was a real extractor defect, not OCR: the D8 pdfplumber
fallback rows were appended to the candidates but contributed nothing
to the consumed-line set, so the grid pass re-parsed 580 of the same
rows as numberless phantoms and the block pass re-parsed 364 more
(580 + 364 + 226 pending = 1170 exactly).

Fixing it exposed four further layers, each found by measurement:

1. **Bare Sr# lines cannot anchor the match.** Bare numbers are
   noise-filtered (§3.12) before the table pass, so they are never in
   the line stream. The matcher anchors on the question-stem line
   instead.
2. **pdfplumber option cells carry the marker** ("A. from") while the
   line stream's option rest does not ("from"). The matcher strips the
   leading marker when comparing (`_option_value`); without this, no
   option line ever matched.
3. **Options wrap across lines** ("A. She will / be praised / very
   much / by you."). A rest that is a strict prefix of an expected
   option also matches, and its continuation lines are consumed while
   the accumulated text stays a prefix of that option.
4. **The table header block is unconsumed.** ("Sr# / Question / A /
   B / C / D / <type label> / Ans / Key") — the grid/block passes
   assembled its fragments into numberless phantoms ("C D Prepositions
   Ans", "Ans Key"). The matcher now consumes the header run starting
   at each "Sr#" line, including exactly one non-token line when the
   line after it is "Ans"/"Key" (the section's type label).

Fix: `match_pdfplumber_rows_to_lines` in `app/pipeline/extract/tables.py`,
wired into `extract_document` in `app/pipeline/extract/service.py`.
6 new tests (5 table unit tests + 1 full-file regression test asserting
every ground-truth (page, Sr#) pair appears exactly once with matching
text). Re-measured TestPoint: FP 1170 → 248, question precision
0.5403 → 0.8472, F1 0.7015 → 0.9173, overall question F1 0.6764 →
0.8503. All 1375 ground-truth rows are recovered exactly once.

**Residual (VERIFIED, not fixed):** 248 FP = 218 numberless phantoms
+ 30 pending. The mechanism is documented, not hand-waved: in
long-option sections (e.g. Active and Passive Voice, p8) the
line-stream order does not follow the table's row order — option lines
for a question interleave with other rows' lines, so the
adjacency-based matcher leaves them free and the grid/block passes
assemble them into numberless phantoms (e.g. stem "cheerfully by them
every morning" with options "She will / be praised / very much / by
you."). The per-page promo line ("TestPoint.pk…") is also assembled
as a stem with the next free option lines. Fixing this needs
non-adjacent / positional matching — M5 follow-up, NOT claimed as
done. The scorer artifact from run 5 (option recall 0.4356, because
pdfplumber rows store options as "A. of" vs GT bare "of") was fixed
in the scorer by leading-marker stripping and TestPoint was re-scored
(option recall 0.4356 → 0.9987).

## Per-fixture detail (VERIFIED)

### TestPoint 1000 — Sr# table, digital (re-scored after the fix)

16.7 s (run 5; rescore wall 40.2 s incl. scoring). Questions 1593,
pending 30, qa_pairs 0, skipped 0, excluded 379, number_gaps 3,
number_duplicates 285 — the duplicates are the Sr# restarts across
the book's 12 topic sections (Sr# 1–479, 44 values occur 8×), i.e.
expected, not a defect. Options complete 4/4 on all 1593 questions.
Answers 1.0: the Ans column is recovered exactly on all 1375 rows.

### Computer Past Papers — Q&A pairs, no options (digital)

1.35 s. 754 qa_pairs detected of 960 ground truth (recall 0.6948);
208 skipped, 1 excluded. 293 pairs missed — mostly the two-question
rows (643/644 each carry two different questions in the source) and
the 4 pairs with no separable answer (8, 61, 396, 869), which are
left empty, never invented. Answer correctness 0.991 (tp 661, fp 6,
fn 6). Zero questions detected as MCQs and zero fabricated options —
the qa_pair contract holds.

### CA40 — standard blocks, bold answer lines (digital)

0.18 s. 40/40 questions, 40/40 answers, options 159/160 (1 fn).
Cleanest fixture in the set.

### Urdu NOA — lowercase option markers (digital)

0.38 s. 107/135 questions (recall 0.7926); 105 answered, 2 pending,
29 excluded, 17 number gaps. Answers 1.0 on the 104 matched with
answers. The 28 missed questions are the jumbled-text rows (blocks
out of reading order in the text layer) and the rows missing an
option letter (16 in ground truth) — geometry-based reordering was
not attempted (M5/M6). Q25/Q33 correctly excluded (D6: 3-option and
1-option questions are excluded, never normalised).

### CA monthly ×5 — question + options + explanation (digital)

1.1–2.2 s each. Detected counts track ground truth (29/31/34/27/21
vs 25/27/30/25/18) but per-question P/R/F1 is ~0 — this is a
ground-truth/matching limitation, not extractor failure: the ground
truth "questions" are sentence fragments (e.g. "announcement, what
percentage tariff was specifically imposed…") while detected stems
are full sentences, so the ≥0.85 similarity fails. Per-question
P/R/F1 is not meaningful for these five files; use the counts.
Answers are UNKNOWN for all 125 (no marking mechanism exists in
the text layer — see M4 report §A).

### Pak Study 1000 — numbers only (digital)

66.65 s. 924 unique numbers detected of 1032 (P 0.9989 / R 0.8944 /
F1 0.9438; tp 923, fp 1, fn 109). Full question/option/answer scoring
was not done — the ground truth is question numbers only (no answer
marking exists anywhere in the file). Parse counts: 929 questions,
74 qa_pairs, 77 pending, 12 skipped, 168 excluded, 105 number gaps.

## PPSC-66 end-to-end, live Tesseract (VERIFIED)

Engine Tesseract 5.3.4 eng+urd PSM 3, 200 DPI. Total 2063.9 s OCR +
0.11 s extract (VM, under shared-CPU contention: per-page OCR
31–750 s). Digital text layer 0 chars on all 7 pages (CamScanner
scan confirmed).

- **Questions 14, pending 54, 41/100 numbers recovered**, all 14
  questions 4/4 options. Key sections 1, **key entries applied 13,
  unmatched 7** (entries 21, 22, 23, 24, 29, 30, 31).
- Suspected mechanism (D11): **numbering gap** — Q10–Q24 entirely
  missing from OCR text, Q68–Q96 missing (29); those questions were
  never detected, so their key entries have nothing to join.
- p7 key parsed live: 27 entries, including OCR-noise numbers
  1088/1258/1335/2021 and Paper-67 numbers 86–99 mixed in (Paper 67
  starts mid-p7). Duplicates: Q4×2 (p7), Q28×2 (p1, p2). Skipped 76,
  excluded 51.
- Stored-Tesseract whole-document run (same Tesseract text, no live
  OCR): 17 questions + 77 pending, key applied 16, unmatched 39
  (labelled "Paper 6" — the paper label was not recovered from the
  stored text).
- Table photos (stored Tesseract, counts only): computer Q67–81 →
  4 pending of 15 rows; interjection Q230–257 → 5 pending of 28
  rows. Paper 60 (Gemini reference text, not OCR): 17/21 questions,
  all 4/4 options.

Per-page live OCR: p1 206 s / 42 blocks / 108 lines (Gemini baseline
8 question starts); p2 485 s / 43 / 127 (21); p3 750 s / 42 / 118
(19); p4 219 s / 63 / 131 (20); p5 31 s / 11 / 60 (19); p6 210 s /
20 / 166 (85); p7 163 s / 35 / 116 (34).

## Nastaliq — clean re-measurement (VERIFIED)

**CER 0.5933** (18.39 s, 16 blocks, ref 328 chars, hyp 205 chars) —
**identical to the contended M4 run**, so contention was NOT the
cause; the earlier number stands. Tesseract 5.3.4 eng+urd PSM 3
cannot carry Nastaliq. No Nastaliq claim for Tesseract. Extractor
on the ground-truth Nastaliq lines: 4 pending, 4/4 options complete.

## D9 / D16 (VERIFIED)

- **D9:** 3 of 960 Computer answers exceed flashcard caps (via the
  100-char/line rule; none exceeds 160 total chars; longest 141
  chars, Q669).
- **D16:** 38 lines with ≥3 inline option markers exist (TestPoint
  25, Pak Study 7, CA40 3, June 2, July 1) — but correct splitting
  of those specific lines is **UNVERIFIED** (not scored separately).

## Run history (honest record)

- Run 2 crashed on a key-join `TypeError: unhashable type: 'dict'`
  (stale `entries` variable in the coverage computation) on the
  whole-document stored-Tesseract run — fixed + regression test
  `test_trailing_key_section_joins_whole_document` (full suite green
  after).
- Run 3 crashed at the final `_aggregate` (Computer QA's `None`
  options — fixed).
- Run 4 was killed by a runtime restart mid live-PPSC-66; its JSON
  was lost (the incremental-write fix had silently failed to apply
  via a no-op string replace; applied properly afterwards with
  verified edits, plus a summary-printer `None` guard).
- Run 5 completed (42 min, mostly Tesseract under heavy shared-CPU
  contention). TestPoint re-scored after the consumption fix (40.2 s).

## UNVERIFIED / not scored

- Scanned fixtures with no ground truth (Science/Math/S&GAD/Capsule/
  History notes, Pak Affairs notes): not scored, nothing fabricated.
  Capsule of GK (195pp) was never OCR'd.
- 3/4-column inline-option splitting correctness; D8 line-based Sr#
  path has **zero benchmark coverage** (only unit tests) — TestPoint
  never triggers it.
- No PaddleOCR in this benchmark (ADR-005). No Gemini API calls.
