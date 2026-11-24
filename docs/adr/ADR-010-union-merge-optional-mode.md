# ADR-010: Multi-pass union merge — optional mode, kept; 200 DPI kept; Render-free fit is marginal

- **Status:** ACCEPTED (M7, 2026-11-22)
- **Context:** M5 measured a union of three OCR variants
  (PSM 3 + layout, PSM 3 raw, PSM 4 raw) at 59/100 distinct
  numbers on PPSC-66 at 2–3× OCR cost, and left the mode
  unimplemented. M7 was asked to implement it as an optional
  mode, measure the real gain and cost, and keep it only if the
  gain is real. Two adjacent questions had to be settled with the
  same measurements: the render DPI (a 150 DPI candidate) and
  whether a single PPSC-66 parse fits Render free's 512 MB.
- **Decision:**
  - Multi-pass union merge is KEPT as an explicitly-enabled
    optional mode (`multi_pass=true` on `parse_document_bytes`,
    `?multi_pass=true` on `POST /documents/parse`), never the
    default. Default stays single-path PSM 3 (ADR-008).
  - Render-once: each page is rendered once and the same PNG
    bytes are OCR'd by all three variants (identical OCR input
    per variant, ~17 s saved per multi-pass run by the measured
    8.5 s/pass render cost).
  - 200 DPI stays the production render default; 150 DPI is
    rejected.
  - A single PPSC-66 parse fits Render free 512 MB, marginally
    (~50 MB headroom on the worst sampled run).
- **Evidence (measured, M7 benchmark, VM numbers):**
  - Union gain, end-to-end (fresh-process driver runs, 3 runs):
    single-path 41 questions / 41 answered / 40 distinct
    numbers / 40 correct vs key; multi-pass 62 / 62 / 53 /
    61 correct. Gain: **+13 distinct answered numbers,
    +21 answered questions, 61/62 correct** — the extra answers
    are correct, not guesses.
  - Cost: **2.8–3.1× time** (358–403 s vs 128–133 s), tree peak
    461–466 MB vs 400–431 MB (same band — pages run
    sequentially and renders are reused, so only time grows).
  - M5 comparison resolved, not fudged: M5's 59/100 counted
    extraction-level distinct numbers (questions ∪ pending).
    M7's matched-only count is 53; the M5-basis count on the M7
    multi-pass dump is **59/100, exactly reproducing M5**. The 6
    numbers in the gap exist only as pending and do not survive
    to matched questions.
  - DPI (`scripts/m7_dpi_experiment.py`): 150 DPI is 33% faster
    (96.5 s vs 144.5 s) but loses recovery (35/100 vs 40/100,
    34 vs 41 answered), all recovered answers still correct —
    a recall loss, not a correctness loss. Recovery is the scarce
    resource on PPSC-66, so the speedup is not worth it.
  - Render fit (`scripts/m7_tree_rss.py`,
    `scripts/m7_parse_once.py`): sampled concurrent tree RSS
    398–461 MB across runs (parent 346–418 MB, live tesseract
    children ~90 MB sustained, largest single child high-water
    155–283 MB briefly at model load). Worst observed 461 MB
    vs the 512 MB limit.
- **Rationale:** the gain is real and the answers it adds are
  correct, so the mode earns its place — but at ~3× time it
  must never be the default on a 0.1-CPU instance; it is for
  the cases where recovery matters more than minutes. Keeping
  200 DPI is the same logic in reverse: a 33% speedup that
  costs 5 recovered questions is a bad trade on a paper where
  recovery is the bottleneck.
- **Consequences:**
  - The parse API and the worker both accept multi-pass, but
    nothing enables it by default; the Flutter toggle does not
    expose it.
  - **M14 (2026-11-24): the web upload page now exposes it** —
    "Better recognition (multi-pass)", default OFF, wired as
    `?multi_pass=true` on `POST /documents/upload` and
    `/documents/upload/batch`; the flag rides the job's
    `result_summary` (no schema change) and the worker passes
    it to `parse_document_bytes` / `parse_image_bytes`
    (multi-pass was added to the image path too — the PDF path
    already had it). The worker's per-stage timeout is 3x the
    configured 600 s for multi-pass jobs (1800 s); the global
    setting is unchanged. Live caveat, measured from the M7
    numbers: a full 7-page multi-pass parse is ~20 min
    single-path at Render free's 0.1 CPU, ~60 min multi-pass,
    so it can still exceed the 1800 s stage timeout on the
    free tier — multi-pass is most usable there for short
    scans and single photos; the full effect needs the VPS
    stage. A re-upload of the same file replays the original
    job (dedup), so multi-pass only applies to fresh uploads.
  - Render-free deployment must treat a scanned-book parse as
    a ~50 MB-headroom operation: one parse at a time, and
    `worker_stage_timeout_seconds` (600 s) must be raised (a
    7-page OCR stage is ~120 s on this VM, ~20 min at 0.1 CPU).
  - A long-lived worker accumulates RSS across parses
    (measured: 73 MB baseline → 369 MB after one PPSC-66 parse,
    289 MB after gc + malloc_trim). No restart policy or
    per-job subprocess isolation is wired in M7 — VPS-stage work.
  - Page-parallel OCR was considered and rejected for the same
    reason: it helps this VM and hurts the 0.1-CPU target.
- **Alternatives considered:**
  - Remove the mode (gain not worth 3× cost): rejected — the
    gain is +13 answered numbers with 61/62 correct, and the
    cost is time, not accuracy or memory.
  - Make multi-pass the default: rejected — 3× time on every
    scanned document on Render free is not affordable.
  - 150 DPI as the default: rejected — measured recall loss
    (40 → 35 recovered).
  - Confidence-gated PSM-4 retry (ADR-008's candidate) instead
    of full multi-pass: not implemented — the union already
    captures the PSM-4 wins (p5's numbers) and the retry's
    cost/benefit was not measured; it stays a future option.
