# Benchmark M8 — 2026-11-22 (final Phase 1 benchmark)

M8: the full M6/M7 accuracy set re-run one final time on the
same fixtures and the same code, latency + peak RSS
re-measured in fresh processes, and the M7 job-pipeline and
security proofs re-run (not copied). Machine-readable:
`m8-benchmark-2026-11-22.json`. All numbers measured in this
run, on THIS VM (1.5 shared CPUs, 6 GB RAM) — **VM numbers,
NOT Render numbers**.

## 0. Latency caveat — read this first

**Every latency in this run is ~2.3–2.4× the M7 value, and
the cause is VM contention, not the code.** No pipeline code
changed in M8 (only tests, coverage config, and docs). During
this run other agents were working heavily on the same VM
(the website audit/fix work), and the M8 suite run just
before it took 555 s vs M7's 90 s for the same tests. The
factor is consistent across independent paths (TestPoint
digital 49.7 s vs 20.9 s; PPSC-66 single 297.3 s vs 127.9 s;
multi-pass 859.6 s vs 358.5 s; photos ~2×), which is the
signature of a throttled CPU, not a regression. **The M7
latencies remain the clean baseline; the M8 latencies are
the contended re-measurement.** Accuracy and memory — the
things contention cannot fake — reproduced exactly, which is
what this benchmark is for.

## 1. Accuracy re-run — M7 reproduced exactly

| Fixture | Q P/R/F1 | Answers P/R/F1 | M7 | Change |
|---|---|---|---|---|
| TestPoint (1,375 GT) | 0.98 / 1.0 / 0.9899 (1,375 TP, 28 FP, 0 FN) | 1.0 / 1.0 / 1.0 | same | none |
| Computer Q&A (960 GT) | 0.8846 / 0.6948 / 0.7783 (667 TP, 87 FP, 293 FN) | 0.991 / 0.991 / 0.991 | same | none |
| CA40 (40 GT) | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | same | none |
| Urdu NOA (135 GT) | 1.0 / 0.7778 / 0.875 (105 TP, 0 FP, 30 FN) | 1.0 / 1.0 / 1.0 | same | none |
| PPSC-66 live single | 41 questions, 41 answered, 40/100 distinct numbers, 40/40 correct vs key | — | same | none |
| PPSC-66 live multi | 62 questions, 62 answered, 53/100, 61/62 correct | — | same | none |
| Paper 60 live | Q 0.25 / 0.05 / 0.0833 (1 TP, 3 FP, 19 FN); answers 1.0 on the 1 matched | — | same | none |
| Key region (live key) | whole-blob 0.9756 / 0.80 / 0.8791 (80 TP, 2 FP) → region 1.0 / 0.84 / 0.913 (84 TP, 0 FP) | — | same | none |
| Calibration (1,559 pairs) | ECE 0.0003 before AND after (identity mapping) | — | same | none |
| PPSC-66 promotion | 14 → 41 answered, 54 → 27 pending (27 promoted) | — | same | none |
| TestPoint FP | 28 | — | same | none |

## 2. Latency + peak RSS — M7 vs M8

| Fixture | M7 (s) | M8 (s) | M7 tree peak | M8 tree peak |
|---|---|---|---|---|
| PPSC-66 single-path | 127.9 | 297.3 | 400 MB | 441 MB |
| PPSC-66 multi-pass | 358.5 | 859.6 | 461 MB | 465 MB |
| TestPoint digital | 20.9 | 49.7 | — | — |
| CA40 digital | 0.1 | 0.1 | — | — |
| Computer table photo | 14.3 | 29.6 | 298 MB | 294 MB |
| Paper 60 photo | 31.1 | 63.1 | 370 MB | 363 MB |

Tree peak = sampled concurrent RSS (Python parent + live
tesseract children) in a FRESH process
(`scripts/m7_parse_once.py`). Memory is in the same band as
M7 on every arm (worst 465 MB vs 461 MB) — contention slows
the CPU, it does not grow memory.

### Render-free fit (512 MB) — verdict: fits, marginally — CONFIRMED

Fresh-process worst tree peak **465 MB** (multi-pass; single
441 MB) vs M7's 461 MB — headroom **47 MB**. The M7 verdict
stands unchanged: a single PPSC-66 parse fits 512 MB with
~50 MB headroom. One parse at a time on Render free. The
long-lived worker RSS accumulation (M7: 73 MB baseline →
369 MB after one parse) was not re-measured in M8 — no
restart policy was wired in M8 either; it remains VPS-stage
work.

## 3. Union merge (multi-pass) — gain confirmed again

Optional mode only, never the default. Fresh-process driver:

| Arm | Seconds | Questions | Answered | Distinct numbers 1–100 | Correct vs key |
|---|---|---|---|---|---|
| Single-path | 297.3 | 41 | 41 | 40 | 40/40 |
| Multi-pass | 859.6 | 62 | 62 | 53 | 61/62 |

Same gain as M7 (+13 numbers, +21 questions, 61/62
correct) at the same memory band; the seconds are the
contended values (§0), not a cost change.

## 4. Job pipeline proof (re-run, real HTTP + worker)

CA40 through `POST /api/v1/async-jobs/parse` + `run_once`:
happy path **completed in 0.54 s**, 40/40 answered, stages
queued → uploaded → validated → extracted → answers_detected
→ matched → scored → completed. Forced failure (`Failed to
open stream`) → retry completes the same job (40 questions).
Cancel queued → `cancelled` (second cancel 409, worker claims
nothing); cancel processing → `cancelled`. Identical to M7.

## 5. Security proof (re-run, real HTTP path)

Per-user isolation: another user's GET and cancel → **404 /
404**. Oversize body: **422 `file_too_large`**. Bad input:
non-PDF → **422**; unauthenticated → **401**. Rate limit:
**[422 × 10, 429]**. Secrets grep: **0 offenders** in 101
shipped `.py` files. Identical to M7.

## 6. Observability samples (re-run, real run)

`/health` → `degraded` (truthful: `database:
not_configured`, tesseract + paddleocr available). Note the
one difference from M7's sample: M7's health showed
`supabase: ok` because that benchmark set dummy Supabase env
vars before importing the app; the M8 benchmark imports
`benchmark_m6` first (which imports the app before
`benchmark_m7`'s `setdefault` runs), so the M8 sample ran
with no Supabase env and `supabase` honestly reads
`not_configured`. The check is correct in both cases — it
reports the actual configuration. `/metrics` returns the real
counters (`documents_parsed_total{engine="digital"} 1`, etc.).

## 7. What M8 did not re-measure

- The M7 profile split (Tesseract ~93%) and the DPI verdict
  (150 DPI rejected) are M7 measurements; M8 changed no code
  that could move them, so they are carried, not re-run.
- Worker RSS accumulation across parses (M7) is carried, not
  re-measured.
- No live Supabase, no Render deploy, no Gemini key, no push.
  Phone verification (STOP CONDITION) still unmet — M8 is
  local only, same as M1–M7.
