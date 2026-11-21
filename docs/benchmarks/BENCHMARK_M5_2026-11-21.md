# Benchmark M5 — answer detection on golden dataset v2

- **Date:** 2026-11-21
- **Dataset:** golden v2 (`app/tests/fixtures/golden/dataset.json`, 38 entries)
- **Hardware (VERIFIED):** dev VM, 4 vCPU, 8 GB RAM (shared cell, 1.5 CPU
  quota), Python 3.12, Tesseract 5.3.4 (eng+urd). **All timings and memory
  numbers are VM numbers. They are NOT Render numbers** (Render free is
  0.1 CPU / 512 MB).
- **Detectors:** `app/pipeline/answers/` (M5) — trailing-key, inline,
  style (bold/star), visual (OpenCV marks), handwriting (ink regions),
  precedence resolver, document service. No PaddleOCR in this benchmark
  (ADR-005 deployment gate + OOM risk). No Gemini API calls; Gemini
  reference texts used for question counts / ground truth only.
- **Method:** `scripts/benchmark_m5.py` →
  `docs/benchmarks/m5-benchmark-2026-11-21.json`. Matching: normalised
  text similarity ≥ 0.85 (difflib) AND numbers agree when both have
  numbers; answers by letter (answer text for qa_pair). Total run
  ~5 min, peak RSS 656.1 MB (VM).
- **Harness bugs found and fixed during this run (VERIFIED):** three
  measurements in the first run were harness bugs, not detector
  results, and were fixed before the final run:
  1. Key ideal scored 0/100 because the reconstructed key text
     interpolated the full GT value `"(B) Broke out"` into `"(v)"`,
     producing `"1. ((B) Broke out)"`. Fixed to letter-only `"1. (B)"`.
  2. Star ideal scored 0/20 because the benchmark's Paper 60 parser
     stripped `*` from option text before handing it to the detector.
     Fixed to keep the star, split inline multi-option lines, and
     keep only questions with ≥3 non-empty options.
  3. Bold scored 0/2 because it fed the detector the stored options
     (U+E000 marker stripped by `clean_stored`). Fixed to run on the
     digital extractor's raw lines via `service._apply_bold_markers`.
  4. Key live scored 0/100 because the benchmark used a fresh uuid for
     the extraction and `"ppsc66-live"` for the key call, so the
     paper-identity gate correctly refused with "different source
     document". Fixed to one `doc_id` for both. This exposed a real
     detector fix (see "The default-label gate fix" below).

## Headline results (VERIFIED)

| Detector | Input | P / R / F1 | TP / FP / FN |
|---|---|---|---|---|
| Trailing key | ideal key text (100 GT entries) | 1.0 / 1.0 / 1.0 | 100 / 0 / 0 |
| Trailing key | live PPSC-66 OCR (psm3-layout) | 0.9744 / 0.38 / 0.5468 | 38 / 1 / 62 |
| Inline | TestPoint Ans column (1,375 rows) | 1.0 / 1.0 / 1.0 | 1375 / 0 / 0 |
| Inline | Computer Q&A answer text (956 answerable pairs) | 1.0 / 1.0 / 1.0 | 956 / 0 / 0 |
| Inline | monthly CA ×5 | UNKNOWN (all 5) | — |
| Style star | ideal Gemini text, Paper 60 (20 starred) | 1.0 / 1.0 / 1.0 | 20 / 0 / 0 |
| Style star | live Tesseract photo (star attribution) | 0.8333 / 0.25 / 0.3846 | 5 / 1 / 15 |
| Style bold | synthetic bold PDF (2 bold, 1 ambiguous) | 1.0 / 1.0 / 1.0 | 2 / 0 / 0 |
| Visual | synthetic marks (star/tick/circle/underline) | 1.0 / 1.0 / 1.0 | 4 / 0 / 0 |
| Visual | Paper 60 photo (negative control, 43 option boxes) | — | 1 detection (FP) |
| Handwriting | Paper 60 photo (79 ink regions) | — | bottom note: 4 marginalia + 2 unknown, 0 answer-mark |

**Overall answer correctness before/after M5 (VERIFIED):** the M4
extractor already answered TestPoint (1.0/1.0/1.0), CA40 (1.0/1.0/1.0)
and Urdu NOA (1.0/1.0/1.0) on digital text; M5 adds the *detectors*
that explain those answers, the precedence resolver, and the live-key
path. On PPSC-66 live, M5's key detector applies 39 entries (38
correct, 1 FP) where M4's key join applied 13 — but the resolution
does not promote pending questions to answered, so the answered
question count stays 14 (see "Pending questions are not promoted").

## The default-label gate fix — found by the benchmark, fixed, re-measured (VERIFIED)

The first live-key run scored 0/100 with decision "mismatch —
different source document": the benchmark passed two different
source_document_ids. Fixing that (one `doc_id`) exposed the real
issue: the live-extracted questions carry the extractor's default
paper label `"Paper 1"` (no heading was found by OCR), while the key
says Paper 66 — the gate read the placeholder as a conflicting
identity and would have withheld the key.

Fix (`app/pipeline/answers/key_detector.py`): a default `"Paper 1"`
label is the *absence* of identity, not evidence of a different
paper, so the detector drops the default number/title before the
gate. A REAL different label (e.g. "Paper 67") still mismatches —
verified by unit test (`test_real_different_paper_label_still_mismatches`).
After the fix the live decision is **verified** (paper number + title
agree) and the detector applies 39 entries.

## Trailing-key detector (VERIFIED)

- **Ideal text:** 100/100 entries parsed and applied, decision
  "verified", 0 filtered, 0 unmatched. P/R/F1 1.0/1.0/1.0.
- **Live PPSC-66 OCR (psm3-layout path, 119.0 s):** 93 entries parsed,
  39 applied, 6 filtered, 48 unmatched. Decision "verified".
  P/R/F1 0.9744/0.38/0.5468 (tp 38, fp 1, fn 62).
- **Filtered (6):** noise numbers outside the paper range
  1088/1258/1335/2021 (OCR noise — years/page furniture read as key
  entries) and Paper-67 stems 97/99 ("Select the correct sentence…",
  "Choose the correct form of the verb…") whose values resolve to no
  option. All filtered with reasons recorded.
- **The 1 FP (entry 1):** the live key text's entry 1 is
  `"(A) Possessed: The most suitable choice…"` — Q98's Explanation
  item, not the real key entry `"(B) Broke out"`. The explanation
  section (p6 lines 16–35) precedes the real key (line 36+), and
  `parse_key_entries` keeps the FIRST occurrence of each number, so
  the explanation's "1." hijacks entry 1. The detector takes the
  key_text it is given and does not re-locate the key region inside
  it. Key-region location (start after the "ANSWER KEY" heading) is
  M6 work, not a first/last-wins change: last-wins would let Paper
  67's questions (after the key on p7) hijack entries 1–10 instead.
- **Unmatched (48):** entries whose question OCR never recovered —
  mostly the p5 block (68–78) and Q10–24. These are OCR failures,
  not detector failures: the key has nothing to join to.

## Inline detector (VERIFIED)

- **TestPoint Ans column:** 1.0/1.0/1.0 (1,375/1,375 rows).
- **Computer Q&A answer text:** 1.0/1.0/1.0 over 956 answerable
  pairs. Four GT pairs (nos. 8, 61, 396, 869) have an EMPTY answer
  in the ground truth itself — excluded from the denominator, not
  counted as detector failures.
- **Monthly CA ×5: UNKNOWN, all five** (March, April, June, July,
  Pakistan August). Span check: 72–120 option spans per file, 0 bold,
  0 coloured, 0 "Correct Answer" lines. Image check: 4 embedded
  images OCR'd per file, 0 carry answer text (they are news photos,
  290x174 to 1170x530 px). Explanations match exactly one option in
  8–21 questions per file — too noisy to be an answer source, so the
  detector returns UNKNOWN with the reason recorded, never guesses.

## Style detectors (VERIFIED)

- **Star, ideal Gemini text (Paper 60):** 1.0/1.0/1.0 — 20/20 starred
  options found (Q1–Q20). Q21 has empty options (B)(C)(D) and no
  star — unanswerable from the reference; Q22–Q30 exist with empty
  options. Ground truth corrected in M5: the earlier "21 stars"
  count was wrong; the file holds 20 stars for Q1–Q20 (Q12's and
  Q14's stars sit on wrapped continuation lines).
- **Star, live Tesseract photo:** Tesseract preserves only 7/20 stars
  and merges the columns, so the questions cannot even be segmented
  (the parser finds 0 usable questions). Measured as star
  attribution instead: 5 correctly attributed, 1 wrongly attributed
  (Q6 "(B) Macros *" — the star drifted from (A) Mail merge),
  1 unattributed ("HTTP key repeatedly*" — merged fragment), 15 GT
  stars simply absent from the text. P/R/F1 0.8333/0.25/0.3846.
  The failure is upstream (OCR + segmentation), not in the detector.
- **Bold, synthetic PDF:** 1.0/1.0/1.0 — 2 bold options detected,
  the ambiguous question (two bold options) correctly rejected with
  no answer. The detector reads raw option texts via
  `service._apply_bold_markers` (the U+E000 marker); feeding it the
  stored options scores 0/2 (harness bug #3 above).

## Visual detector (VERIFIED)

- **Synthetic page (4 marks: star, tick, circle, underline):**
  1.0/1.0/1.0 — 4/4 detected, 0 FP, 0 FN. Clean page: 0 FPs.
- **Paper 60 photo (negative control — printed stars + one
  handwritten note, NO pen tick/circle/underline):** 43 option
  boxes, 1 detection (a thin 2px "underline" below option (D) —
  viewed: a faint full-width line under "(D) Public Domain
  Software", likely a printed rule/crease, not a drawn underline).
  1 FP on 43 option boxes ≈ 2.3% FP rate on the negative control.
  The detector was tuned by measurement to get here: search pad
  1.5→3.0× letter height, circle Hough param2 15→25 with a
  single-stroke ring check (point-sampling passed 3 false circles
  from parentheses + letter curves), underline thin-line check
  (≤ max(3, letter_h//6) px — the first version fired on the next
  line's ascenders, 50 FPs), dedup by closest option box, and
  MATCH_THRESHOLD 0.6→0.7 (synthetic stars match at 0.83+; the
  only sub-0.7 hit was a 0.61 false match on the photo).

## Handwriting detector (VERIFIED, limited scope)

- **Paper 60 photo:** 79 unmatched-ink regions. The bottom note
  ("Dot Matrix printer / impact printer", y 0.88–0.91) → **4
  marginalia + 2 unknown, 0 answer-mark** — the requirement is met:
  the note is never treated as an answer. All classifications:
  marginalia 19, unknown 51, answer-mark 9.
- **The 9 answer-mark regions are UNVERIFIED as handwriting:**
  they are consistent with the printed stars (ink near options
  Tesseract did not box as words). No fixture has a verified
  handwritten answer mark, so the detector's answer-mark class is
  recorded UNVERIFIED, not claimed working.

## TestPoint positional fix — M4 follow-up (VERIFIED)

M4 baseline (re-run exactly): Q P/R/F1 0.8472/1.0/0.9173, 248 FPs,
1,623 detected, 30 pending. Mechanism (measured): p8 is
COLUMN-ordered in the line stream — all 5 stems, then the type
label, then ALL A-options, then ALL B-options, then C, then D —
so adjacency-based matching leaves option lines free; pdfplumber
rows for the long-option questions are themselves corrupted
(merged/truncated cells); 93 promo lines ("TestPoint.pk" + Urdu
footer) were ALL unconsumed.

Fix (`consume_leftover_option_lines` in
`app/pipeline/extract/tables.py`, wired into `service.py` after
`match_pdfplumber_rows_to_lines`): furniture first (promo + Ans/Key
footer lines), only anchored rows contribute option values, free
lines scanned in stream order into runs that must fuzzy-match an
anchored row's option value on the same page (exact / prefix /
substring / longest-common-substring ≥15 chars / difflib ≥0.6,
space-removed comparison for mid-word splits), runs stop early so
a following stem is never swallowed.

**After: FPs 248 → 28, Q precision 0.8472 → 0.98,
F1 0.9173 → 0.9899, recall still 1.0; detected 1,623 → 1,403,
pending 30 → 0** (17.34 s). Option P/R/F1 1.0/0.9987/0.9994,
answer P/R/F1 1.0/1.0/1.0. The residual 28 FPs are heterogeneous
(1–2/page): dialogue/quotation fragments (p10–12), vocabulary
sections with multiple option markers on ONE line (p22/26/27/31/
34/36/37/43/46/47), analogy fragments (p38/40), a p1 header
fragment, a p69 degenerate 'D', a p72 mixed fragment. Diminishing
returns — chasing them needs new mechanisms with their own FP risk;
reported as residual with classes, not fixed.

## PPSC-66 end-to-end, live Tesseract (VERIFIED)

- **Best single path (psm3-layout, M4's path): recovered 41/100,
  questions 14, pending 54, 119.0 s** — identical to M4. Recovery
  stays OCR-bound at 41/100; M5 did not raise the single-path
  ceiling, and the report does not claim otherwise.
- **Why (measured):** Q1–9 numbers are PHYSICALLY CLIPPED at the
  left page edge (Q1–Q2 have no visible number at all; Q3–Q9 are
  half-clipped) — even Gemini's p1 reference starts at Q10, so the
  OCR ceiling for numbers is at most 91/100. Q39–45 text is present
  but the numbers are misread as punctuation ("39." → ".").
  Q68–96 (p5) is the dominant missing block: Urdu-script questions
  mixed in, columns merge under PSM 3 ("…Translate into English. -
  88. Change the voice…").
- **PSM variants (full run, 200 DPI, live Tesseract):**

  | Variant | Recovered /100 | Questions | Pending | Key applied | Seconds |
  |---|---|---|---|---|---|
  | psm3-raw | 34 | 23 | 43 | 23 | 113.36 |
  | psm3-layout (M4 path) | 41 | 14 | 54 | 13 | 120.96 |
  | psm4-raw | 15 | 8 | 29 | 8 | 180.06 |

- **Per-page PSM experiment (p3 Q39–57, p5 Q78–96, 200 DPI):**

  | Variant | p3 recovered /19 | p3 CER | p5 recovered /19 | p5 CER |
  |---|---|---|---|---|
  | psm3 | **16** | 0.0623 | 4 | 0.7149 |
  | psm6 | 0 | 0.7408 | 1 | 0.6917 |
  | psm4 | 7 | 0.7006 | **9** | 0.1397 |
  | psm11 | 9 | 0.7145 | 3 | 0.7069 |
  | preprocessed-default-psm3 | 16 | 0.0853 | 3 | 0.2018 |
  | psm3-300dpi | 9 | 0.0938 | 3 | 0.7164 |
  | gutter-crop-psm6 | 7 | — | 4 | — |

  Conclusions: PSM 3 is decisively best on p3, PSM 4 best on p5 —
  per-page PSM matters, a single fixed PSM is suboptimal; 300 DPI
  is WORSE than 200 DPI; preprocessing does not help; PSM 6/11 are
  catastrophic on two-column pages. Page quality (M2 metrics) does
  NOT explain the p3/p5 difference (blur 2480.9 vs 2002.8, contrast
  65.1 vs 60.6, ink 0.099 vs 0.087 — nearly identical); content
  (Urdu + column merge) does.
- **Union across variants (recomputed from the saved full-run
  data):** raw+layout 56/100, all three 59/100. Raw-only numbers:
  [13–17, 20, 22–23, 66, 94]; layout-only:
  [29–41, 49, 51, 52, 54, 56, 67]; in ALL variants: [3, 27, 44, 99];
  in NO variant: 41 numbers [5, 10–12, 48, 50, 53, 55, 59–60,
  62–65, 68–83, 85–88, 90–93, 95–96, 98] — the p5 block (68–96)
  dominates. The union reaches 56–59 but at 2–3× OCR cost, not
  justifiable on the Render-free target — recorded as M6/M7 work
  (multi-pass merge), not done in M5.

## Pending questions are not promoted (VERIFIED)

The M5 service resolves all 68 recovered numbers (14 questions +
54 pending): 42 verdicts answered, 26 unknown, 0 conflicts. The
key evidences answer 25 pending questions in the resolution (plus
3 answered by M4 evidence alone). But `apply_resolution` writes
back only onto `result.questions` — it does not promote pending
questions to answered — so `answered_questions_after` stays 14 and
`changed_by_resolution` is 0. The verdicts exist in the resolution;
the ParseResult keeps the questions pending. Promotion is M6 work:
it needs a decision on whether a key letter alone suffices when
the options are incomplete.

## UNVERIFIED / not scored

- Handwriting answer-mark class: no fixture has a verified
  handwritten answer mark (see above).
- Multi-pass merge (union 56–59/100): measured as a union of saved
  runs, not implemented as a pipeline path.
- Key-region location (the entry-1 FP mechanism): not implemented.
- Gemini-advisory: disabled (no key provisioned); nothing keyed was
  run or scored.
- All timings / peak memory are VM numbers (peak RSS 656.1 MB for
  the full benchmark run), never Render numbers.
