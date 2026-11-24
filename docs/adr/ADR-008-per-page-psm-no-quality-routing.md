# ADR-008: Per-page PSM — no quality-driven routing

- **Status:** ACCEPTED (M6, 2026-11-22)
- **Context:** M5 measured per-page PSM on PPSC-66 p3 vs p5 (the
  two pages where the PSMs disagree): p3 PSM 3 recovers 16/19
  (CER 0.0623), PSM 4 only 7/19 (CER 0.7006); p5 PSM 3 recovers
  4/19 (CER 0.7149), PSM 4 9/19 (CER 0.1397). Per-page PSM matters
  — a single fixed PSM is suboptimal. M6 was asked to route PSM
  per page, driven by measured page quality (the M2 metrics).
- **Decision:** NO quality threshold is fitted. `select_psm()`
  (`app/pipeline/ocr/psm.py`) returns the measured-best
  single-path PSM (3) for every page. The function is the per-page
  routing hook — it takes the measured `PageQuality` and returns
  the selected PSM — so a future rule changes in one place.
- **Evidence (measured, M5 + M6 re-measurement):** the M2 quality
  metrics do NOT separate p5 (wants PSM 4) from the other pages
  (want PSM 3). M6 re-ran the per-page experiment on all 7 pages
  with tesseract 5.3.4 re-installed (`/tmp/m6-psm-experiment.json`;
  p3/p5 reproduce M5 exactly):
  | page | blur | contrast | ink | PSM 3 rec/CER | PSM 4 rec/CER | best |
  | p1 | 1656.8 | 62.1 | 0.091 | 0/8, 0.074 | 0/8, 0.659 | 3 |
  | p2 | 2274.7 | 62.5 | 0.092 | 9/21, 0.127 | 11/21, 0.717 | 3 |
  | p3 | 2480.9 | 65.1 | 0.099 | 16/19, 0.062 | 7/19, 0.701 | 3 |
  | p4 | 1951.6 | 57.4 | 0.082 | 9/20, 0.102 | 9/20, 0.718 | 3 |
  | p5 | 2002.8 | 60.6 | 0.087 | 4/19, 0.715 | 9/19, 0.140 | **4** |
  | p6 | 2167.3 | 66.1 | 0.105 | 76/82, 0.067 | 45/82, 0.333 | 3 |
  | p7 | 2203.9 | 65.0 | 0.097 | 21/33, 0.403 | 5/33, 0.731 | 3 |
  p5 is not an outlier on any metric (blur, contrast and ink are
  all mid-range; p4 is LOWER than p5 on all three yet wants PSM 3
  by CER 0.102 vs 0.718). Any threshold that catches p5 also
  misroutes p1/p4. Noise is 0.0, skew 0/None, brightness 228–234
  on every page — no signal there either. The M5 benchmark states
  it directly: "Page quality (M2 metrics) does NOT explain the
  p3/p5 difference... content (Urdu + column merge) does."
- **Rationale:** fitting a threshold to two nearly-identical
  points is overfitting to noise — any threshold between them
  "works" on the two anchor pages and has no reason to work on a
  third. A routing rule that does not track reality is a defect,
  not a feature (same principle as confidence calibration). The
  honest outcome is: routed and unrouted PPSC-66 recovery are the
  same number in M6, and the benchmark says so.
- **Consequences:**
  - M6 PPSC-66 recovery is unchanged by routing (measured in the
    M6 benchmark: before/after identical).
  - The multi-pass union merge (59/100 at 2–3× OCR cost, M5) stays
    M7 work — NOT implemented in M6.
  - The M7 candidate for real routing is a CONFIDENCE-gated retry
    (OCR once with PSM 3; retry low-confidence pages with PSM 4
    and keep the better result), which uses a signal the quality
    metrics cannot provide. Its cost/benefit must be measured
    before it is adopted — a retry doubles OCR cost on retried
    pages, which matters on Render free (0.1 CPU).
- **Alternatives considered:**
  - Threshold on blur/contrast/ink midpoints between p3 and p5:
    rejected — the midpoints are arbitrary (the gaps are within
    measurement noise) and the M5 text explicitly rules the signal
    out.
  - Always PSM 4: rejected — PSM 4 is decisively worse overall
    (M5 full run: PSM 4 raw 15/100 vs PSM 3 layout 41/100).
  - Route on page classification (scanned vs digital): rejected —
    all 7 PPSC-66 pages are scanned, so the signal does not vary
    where the PSMs disagree.

## Addendum — M15: confidence-gated PSM-4 retry (IMPLEMENTED, 2026-11-24)

- **Status:** IMPLEMENTED in the single path only
  (`app/pipeline/ocr/psm.py` rule + `_ocr_page_single` in
  `app/pipeline/matching/service.py`); `select_psm()` still
  returns 3 for every page — the retry happens AFTER the PSM-3
  pass, it does not replace the default.
- **Rule (measured, Child A):** after a page's PSM-3 OCR,
  compute the mean Tesseract word confidence (every non-empty
  word with conf >= 0; conf -1 dropped — the exact TSV rule from
  `bench_a.py`); if it is below **85**, retry the page with
  PSM 4 and keep the retry only if its mean confidence is
  **strictly higher** (keep margin 0).
- **Measured (PPSC-66):** 41 -> **42 questions**, 40 -> **41
  correct vs key, 0 wrong**; pending 27 -> 33. Only p5 retried
  (PSM-3 mean 81.8 -> PSM-4 86.4, kept). Table photo (0/2) and
  Paper 60 (4/4/9) unchanged. The pre-registered keep margin +5
  scored 41 (PSM-4 was +4.6, just under), so the margin-0 rule
  was chosen post-hoc — it was validated on a second paper
  before adoption: NOA Urdu MCQs (9 pp, 135-question extracted
  key) showed NO change (75 questions / 7 pending / 39 correct
  / 29 wrong, baseline and retry identical — only p9 retried,
  PSM-4 conf equal at 84.1, not kept), so no loss and no new
  wrong answers. The acceptance test now pins 42 / 42 / 33.
- **Scope:** single path only (PDF pages AND the image path).
  Multi-pass (M14/ADR-010) is untouched — it calls `_ocr_page`
  directly with its three fixed variants.
- **OMP_THREAD_LIMIT=1** (`Dockerfile`, production image): Child
  A measured that default 4-thread OpenMP left one PPSC-66 page
  unfinished after 25 min on the oversubscribed dev VM (load
  8–19), while `OMP_THREAD_LIMIT=1` finished the same page in
  11 s with the same OCR text. The production image (web +
  in-process worker) carries the ENV; CI does not set it — the
  suite runs green on GitHub runners without it.
