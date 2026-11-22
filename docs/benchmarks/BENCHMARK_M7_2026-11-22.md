# Benchmark M7 — 2026-11-22

M7: background jobs, security, observability, performance, plus the
M6 carry-overs (multi-pass union merge, section identity, server
image endpoint, TestPoint residual FPs). All numbers measured in
this run, on THIS VM (1.5 shared CPUs, 6 GB RAM) — **VM numbers,
NOT Render numbers**. Machine-readable: `m7-benchmark-2026-11-22.json`
(run 2; the job-pipeline stage durations were re-measured with the
identical proof function after fixing an extraction bug — see the
note in the JSON).

Two full benchmark runs were made (run 1 crashed at the end on a
benchmark-side assertion about metric names — the code was right,
the benchmark's expected names were wrong; run 2 is the reported
run). Run-1 values are quoted as a cross-check where they differ.

## 1. Accuracy re-run — M6 numbers reproduced exactly

| Fixture | Q P/R/F1 | Answers P/R/F1 | M6 | Change |
|---|---|---|---|---|
| TestPoint (1,375 GT) | 0.98 / 1.0 / 0.9899 (1,375 TP, 28 FP, 0 FN) | 1.0 / 1.0 / 1.0 | same | none |
| Computer Q&A (960 GT) | 0.8846 / 0.6948 / 0.7783 (667 TP, 87 FP, 293 FN) | 0.991 / 0.991 / 0.991 | same | none |
| CA40 (40 GT) | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | same | none |
| Urdu NOA (135 GT) | 1.0 / 0.7778 / 0.875 (105 TP, 0 FP, 30 FN) | 1.0 / 1.0 / 1.0 | same | none |
| PPSC-66 live | 41 questions, 41 answered, 40/100 distinct numbers, 40/40 correct vs key | — | same | none |
| Paper 60 live | Q 0.25 / 0.05 / 0.0833 (1 TP, 3 FP, 19 FN); answers 1.0 on the 1 matched | — | same | none |
| Key region (live key) | whole-blob 0.9756 / 0.80 / 0.8791 (80 TP, 2 FP) → region 1.0 / 0.84 / 0.913 (84 TP, 0 FP) | — | same | none |
| Calibration (1,559 pairs) | ECE 0.0003 before AND after (identity mapping) | — | same | none |
| PPSC-66 promotion | 14 → 41 answered, 54 → 27 pending (27 promoted) | — | same | none |

Section identity (M7 fix) holds: TestPoint end-to-end answers stay
1.0, and the new two-section regression test proves a key evidence
from one section can no longer attach to the same number in another
section (`app/tests/test_answers_section.py`, 5 tests).

## 2. Latency + peak RSS — before vs after

Before numbers: `scripts/m7_profile.py`, same VM, same day,
unprofiled runs. After numbers: this benchmark (run 2; run 1 in
parentheses where it differs).

| Fixture | Before (s) | After (s) | Before tree peak | After tree peak |
|---|---|---|---|---|
| PPSC-66 single-path | 129.6 | 127.9 (run 1: 132.6) | 459 MB max (range 398–459 over 3 runs) | 400 MB (run 1: 431) |
| TestPoint digital | 21.3 | 20.9 | — | — |
| CA40 digital | 0.1 | 0.1 | — | — |
| Computer table photo (image endpoint) | — | 14.3 (run 1: 14.0) | — | 298 MB |
| Paper 60 photo (image endpoint) | — | 31.1 (run 1: 33.3) | — | 370 MB |

Tree peak = sampled concurrent RSS (Python parent + live
tesseract children, 100 ms sampling) in a FRESH process
(`scripts/m7_parse_once.py`). The single-path numbers are
unchanged within run-to-run noise (±5%): the only latency
optimisation in M7 (render-once) affects multi-pass only.

### What the profile found (scripts/m7_profile.py, cProfile)

- PPSC-66 single-path: Tesseract `image_to_data` ~120 s of
  129.6 s (**93%**), one invocation per page (~17 s/page,
  eng+urd). Render ~8.5 s total. Layout `analyze` ~0.00 s/call
  (42 blocks). Nothing in Python code can move the 93% except
  fewer pixels or fewer pages.
- TestPoint digital (21.3 s): inside pdfplumber/pdfminer
  (`page_get_textpage`, `process_object`, `nextobject`) — library
  internals, no cheap safe fix; the extraction path is not touched.
- The worker's per-stage timing attribution is CORRECT (the
  delta is credited to the stage whose hook just fired = the phase
  that just ended). An early profile script credited intervals to
  the previous stage and mislabelled OCR time as "render" — the
  code was never wrong; the script was.

### Optimisations made, and ones rejected

- **Render-once for multi-pass (DONE):** the old code rendered
  each page 3× (once per variant, ~8.5 s/pass). Each page is now
  rendered once and the same PNG bytes are OCR'd by all three
  variants — identical OCR input, ~17 s saved per multi-pass run
  (by the measured 8.5 s/pass render cost).
- **150 DPI (REJECTED, measured):** `scripts/m7_dpi_experiment.py` —
  150 DPI is 33% faster (96.5 s vs 144.5 s) but LOSES recovery
  (35/100 vs 40/100, 34 vs 41 answered), all recovered answers
  still correct — a recall loss, not a correctness loss. 200 DPI
  stays the production default. (An early run of this experiment
  hit a Tesseract per-page timeout under CPU contention with a
  parallel test run; the clean sequential re-run completed both
  arms — the timeout was a contention artifact, not a DPI effect.)
- **Page-parallel OCR (NOT DONE):** would halve wall time on this
  VM but Render free is 0.1 CPU — parallel workers would thrash
  there and add thread complexity. Recorded, not implemented.
- **TestPoint pdfplumber path (NOT DONE):** library-internal cost,
  changing the extraction path risks the 1.0 answer accuracy.

### Render-free fit (512 MB) — verdict: fits, marginally

Fresh-process single PPSC-66 parse, sampled concurrent tree RSS:
**398–461 MB across runs (worst observed 461 MB multi-pass,
400–431 MB single-path)** — fits 512 MB with ~50 MB headroom.
Detail (`scripts/m7_tree_rss.py`, `m7_tesseract_child_rss.py`):
baseline process 73 MB; parent peak 346–418 MB; live tesseract
children ~90 MB sustained (largest single child high-water
155–283 MB per page, briefly, at model load); `gc.collect()` +
`malloc_trim` returns ~79 MB after a parse (369 → 289 MB), but
the process never returns to its 73 MB baseline. A long-lived
worker therefore accumulates RSS across parses — no restart
policy or per-job subprocess isolation is wired in M7 (VPS-stage
work). Deployment notes: one parse at a time on Render free;
`worker_stage_timeout_seconds` (600 s default) is too short for a
7-page OCR stage at 0.1 CPU (~20 min by the VM's 120 s at
1.5 CPUs) and must be raised for Render free.

## 3. Union merge (multi-pass) — gain is real, mode kept

Optional mode only (`multi_pass=true` / `?multi_pass=true`),
never the default. Fresh-process driver runs:

| Arm | Seconds | Questions | Answered | Distinct numbers 1–100 | Correct vs key |
|---|---|---|---|---|---|
| Single-path (run 2) | 127.9 | 41 | 41 | 40 | 40/40 |
| Multi-pass (run 2) | 358.5 | 62 | 62 | 53 | 61/62 |
| Multi-pass (run 1) | 388.1 | 62 | 62 | 53 | 61/62 |
| Multi-pass (dump re-run) | 402.8 | 62 | 62 | 53 | 61/62 |

Gain (end-to-end): **+13 distinct answered numbers (40 → 53),
+21 answered questions (41 → 62), 61/62 correct** — the extra
answers are correct, not guesses. Cost: **2.8–3.1× time**
(358–403 s vs 128–133 s), tree peak 461–466 MB vs 400–431 MB
(same band — renders are reused and pages run sequentially, so
only time grows, not memory).

M5 comparison resolved: M5 reported 59/100, but that counted
**extraction-level** distinct numbers (questions ∪ pending).
M7's matched-only count is 53 — and the M5-basis count on the
M7 multi-pass dump is **59/100, exactly reproducing M5**. The 6
numbers in the gap exist only as pending (incomplete extraction)
and do not survive to matched questions. Verdict: KEEP the mode
(ADR-010).

## 4. Job pipeline proof (real HTTP + worker, temp SQLite)

CA40 through `POST /api/v1/async-jobs/parse` + `run_once`:

- Happy path: **completed in 0.51 s** (repeat run; benchmark run
  0.27 s), 40 questions, 40 answered. Stages (seconds):
  queued —, uploaded 0.0, validated 0.23, extracted 0.14,
  answers_detected 0.03, matched 0.01, scored 0.0,
  completed 0.5 (total). The digital path fires no
  render/ocr/layout hooks, so no preprocessing/ocr_done/
  layout_done rows — correct behaviour.
- Forced failure + retry: corrupt PDF fails with
  `Failed to open stream` recorded; retry re-queues
  (`retry_count` 1); good bytes complete the same job
  (40 questions).
- Cancel queued: `cancelled`, worker claims nothing, second
  cancel is 409.
- Cancel processing: claimed, flag set, worker records
  `cancelled` at the first stage boundary (not failed).
- Stage timeout proof is in the tests (fake slow parse, 0.1 s
  timeout names the `ocr` stage); the benchmark does not burn a
  real 600 s timeout.

## 5. Security proof (real HTTP path)

- Per-user isolation: another user's GET and cancel on user A's
  job → **404 / 404** (async-jobs; review endpoints already 404
  per M6 and are covered by tests).
- Oversize body: **422 `file_too_large`** (the M1 contract —
  the M7 middleware originally returned 413 and broke the M1
  test; fixed to 422 everywhere so one oversize shape holds
  across upload/parse/parse-image/async-jobs).
- Bad input: non-PDF to the PDF parse endpoint → **422**, never
  a 500. Unauthenticated → **401**.
- Rate limit: 10 parse attempts/user/minute by default; 11
  attempts → `[422 × 10, 429]` (`rate_limited`). In-memory
  sliding window, per-user key; resets per process (documented
  limitation for multi-replica deploys).
- Secrets grep: **0 offenders** in 101 shipped `.py` files
  (same regex as `test_security_m7.py`); `.env` not tracked.
  Gemini-advisory stays disabled-by-default (flag + key +
  nonzero budget); no Gemini API calls were made.

## 6. Observability samples (real run)

`/health` (no DATABASE_URL — truthful, not faked):

```json
{"status": "degraded", "service": "officerpath-pdf-engine",
 "version": "0.1.0", "environment": "development",
 "checks": {"config": "ok", "supabase": "ok",
  "database": "not_configured", "ocr_tesseract": "available",
  "ocr_paddleocr": "available", "disk": "ok"}}
```

`/metrics` (after one sync parse, one async job through the
worker, one bad parse — counters appear on first event, standard
Prometheus behaviour):

```
documents_parsed_total{engine="digital"} 1
errors_total{code="invalid_file"} 1
http_requests_total{status="200"} 2
http_requests_total{status="202"} 1
http_requests_total{status="422"} 1
jobs_total{status="completed"} 1
ocr_calls_total{engine="digital"} 1
officerpath_stage_seconds_total{stage="answers"} 0.025
officerpath_stage_seconds_total{stage="classify"} 0.012
officerpath_stage_seconds_total{stage="extract"} 0.040
officerpath_stage_seconds_total{stage="ingest"} 0.000
officerpath_stage_seconds_total{stage="matching"} 0.005
officerpath_jobs_current{status="completed"} 2
```

Note: `officerpath_jobs_current` comes from a live DB query and
is absent when no database is configured (never faked — the test
asserts this). Metric names are the real ones
(`documents_parsed_total`, not `officerpath_documents_parsed_total`;
stage metric is `officerpath_stage_seconds_total`).

## 7. TestPoint residual 28 FPs — assessed, left as-is

All 28 FPs are **numberless fragments** (`number=None`) from
split table rows — stems like `'Sana you'`, `'by someone'`,
`'bruises'`, `'D'`, `'night,'`, `'contentment B. happiness C.
execution D. gassing C. D D'` — pieces of real questions whose
option rows the table parser split apart. They carry 4 options
so they pass validation as questions, but they never produce a
wrong answer (no number → no inline answer joins them;
`correct_index` stays −1/UNKNOWN; answers P/R/F1 is still 1.0).
The safe-looking fix ("drop numberless questions") would risk
real numberless detections on scanned papers and needs a full
re-measurement; the fragment-joining fix lives in the pdfplumber
fallback path M4 already touched once. NOT cheap — left, recorded.

## 8. What M7 did not do

- No live Supabase, no Render deploy, no Gemini key, no push.
- No worker restart policy / per-job subprocess isolation
  (RSS accumulation across parses in a long-lived worker).
- No page-parallel OCR (wrong for 0.1 CPU Render free).
- No 150 DPI, no TestPoint FP fix (both measured and rejected).
- Flutter `flutter analyze` still needs the owner (no SDK on VM).
- Phone verification (STOP CONDITION) still unmet — M7 is local
  only, same as M1–M6.
