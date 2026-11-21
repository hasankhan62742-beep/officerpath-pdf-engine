# Milestone 5 Report — Answer Detection (Phase 1, M5)

- **Date:** 2026-11-21
- **Branch:** `officerpath-phase1-engine` (local only — NO push; GitHub App
  install still pending, owner step)
- **Gate verdict: MET** — the answers package is built (five detectors +
  precedence resolver + document service), every detector is measured
  with precision/recall/F1 on the golden set, the TestPoint residual
  248 FPs are cut to 28, and the PPSC-66 recovery was investigated with
  bounded cost-free variations and measured honestly. The PPSC-66
  single-path ceiling stays 41/100 — it is an OCR limitation, not a
  detector failure, and it is stated plainly below, not hidden behind
  the gate. Two real defects the benchmark caught (a harness bug
  masking a live-key 0/100, and a default-label identity bug that
  would have withheld every key on scanned papers) were fixed and
  re-measured in this milestone.
- **Quality gates (VERIFIED):** pytest **377 passed / 0 failed**
  (336.46 s) = 316 pre-existing + 61 new M5 tests; **ruff check all
  passed**, **ruff format clean** (141 files); **mypy CI gate
  `mypy app/db app/pipeline app/storage` SUCCESS, no issues in 58
  source files**. (Broad `mypy app/` still shows ~382 errors in tests
  + pre-existing skeleton main.py — out of scope per pyproject.toml,
  unchanged by M5.)
- **No Alembic migration** — answers are resolved in memory and not
  persisted in M5 (schema unchanged). No new ADR — no genuinely new
  decision was taken (the per-page PSM finding is a measurement, not
  a routing change; the default-label fix is a bug fix inside the
  existing §5.5 gate). No push, no live Supabase, no deploys, no paid
  services, no GCP, no Gemini key, no Gemini API calls (mock provider
  only). Flutter app untouched.

## Objective

Implement the M5 scope: answer detectors (trailing-key, inline,
style bold/star, visual marks, handwriting — limited, honest),
answer precedence enforced in code, the M4 TestPoint residual-248-FP
follow-up, the PPSC-66 recovery investigation with bounded
cost-free variations, and per-detector precision/recall/F1 on the
golden set via `scripts/benchmark_m5.py`.

## A. Answer detectors — `app/pipeline/answers/` (DONE)

One module per mechanism, each with its own tests and a per-detector
measurement (tables in §E). All evidences carry detector, question
number, confidence, and evidence text/coordinates; all are
JSON-serialisable.

1. **Trailing-key** (`key_detector.py`): parses a trailing answer key
   (number → letter) from the same paper and joins it to the detected
   questions. Reuses the M4 primitives (`parse_key_entries`,
   `resolve_answer_token`, `decide_key_match`) and adds the filtering,
   the evidence, and the measurement. Filters with reasons recorded:
   numbers outside the paper's question range (1088/1258/1335/2021),
   unknown key tokens (spec §6.8), tokens resolving to no option
   (Paper-67 stems 97/99), and a key whose paper identity does not
   match (withheld entirely). NEVER applies a key from one paper to
   another — verified by unit test with a real "Paper 67" label.
2. **Inline** (`inline_detector.py`): Ans-column / answer-line tokens
   via `resolve_answer_token`; Q&A text answers; and
   `check_monthly_ca_answers`, which re-implements M4's span method
   (bold = flags & 16, coloured, "Correct Answer" lines,
   explanation-vs-option match histogram) and OCRs up to 4 embedded
   images per file looking for answer-like text. Returns UNKNOWN with
   the reason when no marking mechanism exists — never guesses from
   an explanation.
3. **Style** (`style_detector.py`): bold option via the U+E000 marker
   (from the digital extractor's `style["bold_lines"]` through
   `service._apply_bold_markers`); star-marked options (`*` after the
   correct option). Exactly one marked option fires; zero = no
   evidence; more than one = ambiguous rejection with reason.
   Confidence 0.9 printed; OCR tick/bold → unverified 0.54 via
   `apply_ocr_provenance`.
4. **Visual** (`visual_detector.py`): OpenCV marks near option
   letters on page renders — star/tick via DejaVu Sans template
   matching at 3 scales, circle via HoughCircles with a single-stroke
   ring check, underline via horizontal morphological opening with a
   thin-line check. Option boxes are FULL option-line boxes (marks
   sit next to the option value, not the letter). Every detection
   carries confidence + evidence coordinates/region. Tuned by
   measurement on the Paper 60 photo (see §E).
5. **Handwriting** (`handwriting.py`, limited scope): finds ink
   Tesseract did not box as words (Otsu + connected components,
   minus dilated word boxes) and classifies it — answer-mark (small,
   near an option), marginalia (wide / many components / bottom
   margin away from options), else unknown — never forced. The Paper
   60 handwritten note classifies as marginalia, never as an answer
   (§E). The answer-mark class is UNVERIFIED: no fixture has a
   verified handwritten answer mark.

## B. Answer precedence, enforced in code (DONE)

`precedence.py`: manual > explicit key > inline answer > digital
style > visual > inferred. `resolve_answer()` sorts by (rank,
detector); ANY disagreement with the winner — same rank or lower
rank — is a logged conflict, and a conflict blocks verification
even for a key answer (fixed during M5: the resolver originally
logged conflicts only within the same top rank). Inferred answers
get the lowest confidence (cap 0.5) and an explicit `inferred`
flag. When NO detector fires, the answer is UNKNOWN — never
fabricated. `service.py` (`resolve_document_answers` /
`apply_resolution`) joins M4's own answer as evidence at its M5
rank; an M5 detector can only overturn it at a HIGHER precedence
rank; UNKNOWN never clears an existing answer; a pure source rename
(M4 "key" vs M5 "trailing-key") for the SAME answer is not counted
as a change (fixed during M5: it originally was).

## C. TestPoint residual 248 FPs — fixed, re-measured (DONE)

M4 baseline re-run exactly: Q P/R/F1 0.8472/1.0/0.9173, 248 FPs,
1,623 detected, 30 pending. Mechanism (measured): p8 is
COLUMN-ordered in the line stream (all stems, then the type label,
then ALL A-options, then ALL B-options, then C, then D), so
adjacency matching leaves option lines free; pdfplumber rows for
the long-option questions are themselves corrupted (merged /
truncated cells); 93 promo lines ("TestPoint.pk" + Urdu footer)
were ALL unconsumed.

Fix: `consume_leftover_option_lines` (`app/pipeline/extract/tables.py`,
wired into `service.py` after `match_pdfplumber_rows_to_lines`).
Furniture first (promo + Ans/Key footer lines — the promo regex has
NO trailing `\b` because Urdu letters are `\w` in Python re, so
"testpoint.pkاپٹس" has no boundary after "pk"); only rows whose stem
was consumed in pass 1 ("anchored") contribute option values; free
lines scanned into runs that must fuzzy-match an anchored row's
option value on the same page (exact / prefix / substring /
longest-common-substring ≥15 chars / difflib ≥0.6, space-removed
for mid-word splits), stopping early so a following stem is never
swallowed.

**After: FPs 248 → 28, Q precision 0.8472 → 0.98, F1 0.9173 →
0.9899, recall still 1.0; detected 1,623 → 1,403, pending 30 → 0.**
`app/tests/test_extract_service.py::test_testpoint_pdfplumber_rows_consumed_once`
updated to the new counts (1403 / 0) with an M5 comment; the
per-row assertions (every GT row present exactly once, text
similarity ≥0.85) are the real regression guards and still hold.
Residual 28 FPs are heterogeneous (1–2/page) — dialogue fragments,
vocabulary sections with multiple markers on one line, analogy
fragments, a p1 header fragment, a p69 degenerate 'D', a p72 mixed
fragment. Diminishing returns; reported as residual with classes.

## D. PPSC-66 recovery — investigated, measured, still OCR-bound (DONE)

M4 live Tesseract recovered 41/100 numbers (14 questions + 54
pending); Q10–Q24 and Q68–Q96 entirely missing. Investigation
(stored Tesseract text vs Gemini reference, page renders, quality
metrics):

- **Q1–9: physically clipped at the left page edge.** Q1–Q2 have no
  visible number at all; Q3–Q9 are half-clipped. Even Gemini's p1
  reference starts at Q10. OCR ceiling for numbers is at most 91/100.
- **Q39–45: text present, numbers misread as punctuation** ("39." →
  ".", "41." → "|.", "42." → ".").
- **Q68–96 (p5): Urdu-script questions mixed in, columns merge**
  under PSM 3. Quality does NOT explain it: p3 vs p5 blur 2480.9 vs
  2002.8, contrast 65.1 vs 60.6, ink 0.099 vs 0.087 — nearly
  identical; content does.

Bounded variations (per-page PSM experiment, p3 + p5, 200 DPI):
PSM 3 best on p3 (16/19, CER 0.0623), PSM 4 best on p5 (9/19, CER
0.1397) — per-page PSM matters, a single fixed PSM is suboptimal;
300 DPI is WORSE than 200 DPI; preprocessing does not help; PSM 6/11
are catastrophic on two-column pages (0–1/19).

Full-run variants (live Tesseract, all 7 pages): psm3-raw 34/100,
psm3-layout 41/100 (M4's path — identical), psm4-raw 15/100.
Union across variants: raw+layout 56/100, all three 59/100 — but at
2–3× OCR cost, not justifiable on the Render-free target; recorded
as M6/M7 work (multi-pass merge), not done in M5. 41 numbers are in
NO variant, dominated by the p5 block (68–96).

**Conclusion: recovery stays OCR-bound at 41/100 on the best single
path. Gemini-advisory stays DISABLED (no key). The bar was not
lowered by testing on stored/ideal text.**

## E. Measurement — per-detector precision / recall / F1 (DONE)

Full tables in `docs/benchmarks/BENCHMARK_M5_2026-11-21.md`
(`docs/benchmarks/m5-benchmark-2026-11-21.json`). All numbers below
were actually measured in this run; timings / peak memory are VM
numbers (peak RSS 656.1 MB for the full benchmark run).

| Detector | Input | P / R / F1 | TP / FP / FN |
|---|---|---|---|
| Trailing key | ideal key text (100 GT entries) | 1.0 / 1.0 / 1.0 | 100 / 0 / 0 |
| Trailing key | live PPSC-66 OCR | 0.9744 / 0.38 / 0.5468 | 38 / 1 / 62 |
| Inline | TestPoint Ans column (1,375 rows) | 1.0 / 1.0 / 1.0 | 1375 / 0 / 0 |
| Inline | Computer Q&A (956 answerable pairs) | 1.0 / 1.0 / 1.0 | 956 / 0 / 0 |
| Inline | monthly CA ×5 | UNKNOWN (all 5) | — |
| Style star | ideal Gemini text, Paper 60 | 1.0 / 1.0 / 1.0 | 20 / 0 / 0 |
| Style star | live Tesseract photo | 0.8333 / 0.25 / 0.3846 | 5 / 1 / 15 |
| Style bold | synthetic bold PDF | 1.0 / 1.0 / 1.0 | 2 / 0 / 0 |
| Visual | synthetic marks (4 kinds) | 1.0 / 1.0 / 1.0 | 4 / 0 / 0 |
| Visual | Paper 60 photo (negative control) | — | 1 FP on 43 boxes |
| Handwriting | Paper 60 photo (79 regions) | — | note: 0 answer-mark |

Notes on the table:

- **Live key 1 FP (entry 1):** the explanation's "1. (A) Possessed"
  hijacks entry 1 because `parse_key_entries` keeps the FIRST
  occurrence and the explanation precedes the real key. Key-region
  location is M6 work (see §F).
- **Live key 62 FNs** are questions OCR never recovered — the key
  has nothing to join to.
- **Computer Q&A:** 4 GT pairs (8, 61, 396, 869) have an EMPTY
  answer in the ground truth — excluded, not counted as failures.
- **Monthly CA UNKNOWN stands:** 0 bold / 0 coloured / 0 "Correct
  Answer" lines in all 5 files; 4 embedded images OCR'd per file,
  0 carry answer text (news photos); explanations match exactly one
  option in only 8–21 questions per file — too noisy to be an
  answer source.
- **Star live:** Tesseract preserves 7/20 stars and merges the
  columns (0 usable questions parsed); measured as star attribution
  — 5 correct, 1 wrong (Q6 Macros instead of Mail merge),
  1 unattributed, 15 absent. OCR-bound, not detector-bound.
- **Paper 60 ground truth corrected:** 20 stars for Q1–Q20 (the
  earlier "21 stars" count was wrong); Q21's options are empty.
- **Pending questions are not promoted:** the M5 service resolves
  all 68 recovered numbers (42 verdicts answered, 26 unknown, 0
  conflicts) — the key evidences answer 25 pending questions in the
  resolution — but `apply_resolution` writes back only onto
  `result.questions`, so `answered_questions_after` stays 14 and
  `changed_by_resolution` is 0. Promotion needs a decision on
  whether a key letter alone suffices when options are incomplete
  (M6 work).

## Implemented (files changed)

- **New package `app/pipeline/answers/`** (8 files, ~2,600 lines incl.
  tests): `__init__.py`, `models.py`, `precedence.py`,
  `key_detector.py`, `inline_detector.py`, `style_detector.py`,
  `visual_detector.py`, `handwriting.py`, `service.py`.
- **Extractor changes (M5 only):** `app/pipeline/extract/tables.py`
  (+228 lines: `consume_leftover_option_lines` + helpers),
  `app/pipeline/extract/service.py` (positional pass wiring),
  `app/pipeline/extract/__init__.py` (export).
  `app/tests/test_extract_service.py` updated (TestPoint counts
  1593→1403, 30→0). M4's extractor API is otherwise unchanged.
- **Tests:** 61 new (precedence 10, key 10, inline 8, style 9,
  service 8, visual 6, handwriting 4, tables-positional 6).
- **Benchmark:** `scripts/benchmark_m5.py`,
  `docs/benchmarks/m5-benchmark-2026-11-21.json`,
  `docs/benchmarks/BENCHMARK_M5_2026-11-21.md`.
- **Experiments (not deliverables, kept in /tmp):**
  `scripts/m5_psm_experiment.py`, `scripts/m5_full_run_experiment.py`
  — saved outputs `/tmp/m5-psm-experiment.json`,
  `/tmp/m5-full-experiment.json`.

## Honest limitations / what is NOT done

- **PPSC-66 single-path recovery stays 41/100** (OCR-bound; see §D).
  Multi-pass merge (union 56–59) is M6/M7 work.
- **Key-region location not implemented** — the entry-1 FP
  mechanism (explanation items hijacking low entry numbers). M6.
- **Pending-question promotion not implemented** — key evidences
  answer 25 pending questions in the resolution, but they stay
  pending in the ParseResult. M6 decision needed.
- **Handwriting answer-mark class is UNVERIFIED** — no fixture has
  a verified handwritten answer mark.
- **Per-page PSM is measured, not routed** — PSM 3 wins on p3, PSM 4
  on p5, but no per-page PSM selection was wired into the pipeline.
  M6/M7 work.
- **TestPoint residual 28 FPs remain** (heterogeneous, 1–2/page).
- **Gemini-advisory stays DISABLED** (no key provisioned). Nothing
  keyed was run or scored.
- **Owner steps still outstanding (blockers, not code failures):**
  GitHub App install + push, migration 015 live apply, Render
  deploy, Gemini server key (deferred by the user).
