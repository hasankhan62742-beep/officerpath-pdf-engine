# OfficerPath AI — Phase 1 Milestone 2 Report

- **Date:** 2026-11-21 (PKT, Asia/Karachi)
- **Milestone:** M2 — PDF analysis, page classification, rendering, adaptive preprocessing (Ultimate numbering M0–M8)
- **Gate (audit §10):** Quality metrics per page; marks preserved on fixtures.
- **Evidence labels:** **VERIFIED** (executed and observed) · **ASSUMED** (reasonable, untested) · **UNVERIFIED** (code exists, not run) · **UNKNOWN** (needs research/access).

## 1. Objective

Implement M2 on the approved baseline (ADR-001 Render free Stage 1,
ADR-002 hybrid OCR, ADR-003 persistence): replace the M1 byte-heuristic
page classification with real PyMuPDF evidence, render pages at bounded
DPI, measure per-page quality, and build adaptive OpenCV preprocessing
whose profiles are chosen from measured quality — with the hard
requirement that ticks, stars, circles, underlines, highlights and
handwriting survive. Local only, on branch `officerpath-phase1-engine`
(owner: "M2 local shuru karo, push baad mein hoga"). No OCR/extraction
logic (M3–M6), no live Supabase changes, no deploys, no paid services,
no Gemini key, no GitHub push attempted.

## 2. Implemented (files changed)

New modules (all in `~/workspace/officerpath-pdf-engine`):

- `app/pipeline/pdf/analysis.py` — PyMuPDF analysis: per-page text
  chars/spans, image count + coverage, fonts, rotation, embedded-image
  DPIs, drawing count. Encrypted files raise `ValueError` (never bypassed).
- `app/pipeline/pdf/classifier.py` — real classification from that
  evidence: digital / scanned / mixed / blank / unreadable / unknown,
  per page. `app/pipeline/ingestion/classifier.py` now passes the raw
  PDF bytes through when available; the M1 byte heuristic remains only
  as the fallback (labelled `byte-heuristic`).
- `app/pipeline/pdf/renderer.py` — one page at a time, colour PNG, DPI
  lowered automatically to fit `max_render_pixels` (default 12 MP);
  image files normalised via Pillow (`Image.Resampling.LANCZOS`).
- `app/pipeline/pdf/quality.py` — blur (Laplacian variance), contrast
  (grayscale std-dev), background-noise sigma (MAD estimate), skew
  (Hough lines + an interquartile-range agreement guard), brightness,
  ink coverage. Bleed-through is recorded as NOT measured — no reliable
  signal without a clean reference page.
- `app/pipeline/preprocess/profiles.py` — six versioned profiles
  (`m2-v1`: clean, default, low_contrast, noisy, skewed, low_quality)
  selected from measured quality with a recorded reason per page.
- `app/pipeline/preprocess/preprocessor.py` — deskew, denoise
  (fastNlMeans), CLAHE, sharpen, upscale, Otsu/adaptive threshold,
  border crop. Colour copies are returned byte-identical; every applied
  / skipped operation is recorded with its parameters.
- `app/pipeline/preprocess/marks.py` — mark-preservation checks (ink
  retention per known mark region, colour-copy identity) + HSV highlight
  detection for reporting (M5 input, not a gate).
- `app/pipeline/pdf/service.py` — `run_pdf_stage`: analysis ->
  classification -> rendering -> preprocessing, page by page, through
  the `can_transition` state machine; per-page failures become
  `processing_errors` rows and the document continues; metrics + render
  paths + profiles persist to `document_pages`. Deliberately NOT wired
  into the upload request path (it would block requests and hold renders
  in memory) — the M7 worker calls it; `scripts/run_m2_pipeline.py`
  runs it from the CLI.
- `scripts/generate_m2_fixtures.py` + `scripts/copy_ppsc66_fixtures.py`
  — synthetic fixtures generated programmatically (clean / scanned /
  mixed / skewed +5° / low-contrast / noisy σ=18 / blank) with a mark
  manifest (bboxes in points + render pixels at 200 DPI); PPSC-66
  p-1..p-7 + two table photos copied read-only with `PROVENANCE.md`.
- `scripts/benchmark_m2.py` — measured table for this report.
- `docs/adr/ADR-004-pdf-and-preprocessing.md` — library evaluation,
  PyMuPDF AGPLv3 licence flag, pdfplumber deferred to M3, Render
  memory measurements.
- Tests added (44 new): `test_pdf_analysis.py`, `test_preprocessing.py`,
  `test_pdf_pipeline.py` (incl. the gate test: marks survive every
  profile; persistence of metrics via `SqlAlchemyStageRecorder`).

Changed pre-existing files (small, reviewed): `requirements.txt`
(PyMuPDF 1.26.3, opencv-python-headless 4.11.0.86, Pillow 13.0.0,
NumPy 2.3.2), `app/config.py` (M2 render/preprocess settings),
`app/pipeline/ingestion/classifier.py` + `service.py` (bytes passed
through; `StageRecorder` protocol extended with `update_page` +
`record_error`, both recorders implement them), `README.md`,
`CHANGELOG.md`, `Dockerfile` (comment: no new apt packages for M2).

## 3. Verified (commands + results, all executed 2026-11-21)

- **Baseline first:** `pytest -q` → **69 passed** before any M2 change
  (reproduces M1).
- **Full suite after M2:** `pytest -q` → **113 passed, 0 failed**
  (69 pre-existing + 44 new), 10 warnings (pre-existing Starlette/
  gotrue deprecations + OpenCV SWIG warnings). Suite takes ~54 s
  (fastNlMeans on full pages dominates).
- **Ruff:** `ruff check .` → all checks passed (after `--fix` +
  `format`); **mypy** `mypy app/db app/pipeline app/storage` → no
  issues in 22 source files.
- **pip-audit:** Pillow 11.3.0 carried **59 known vulnerabilities**
  (fix versions 12.2.0/12.3.0/13.0.0). Upgraded to Pillow **13.0.0**;
  suite stayed green; re-audit → **No known vulnerabilities found**.
- **Classification (VERIFIED on fixtures):**

  | Fixture | Expected | Measured |
  |---|---|---|
  | clean.pdf (2 pp.) | digital, digital | digital, digital |
  | scanned.pdf | scanned | scanned (0 text chars, coverage > 0.9) |
  | mixed.pdf | digital, scanned | digital, scanned |
  | blank.pdf | blank | blank |
  | low_contrast.pdf | digital | digital |
  | noisy.pdf | scanned | scanned |
  | skewed.pdf | scanned | scanned |
  | PPSC-66 p-1..p-7 (PNGs) | scanned | scanned (all 7) |

- **Quality metrics per page (VERIFIED — benchmark script, VM numbers):**

  | Page | Profile | Skew before → after | Blur | Contrast | Noise | Ink |
  |---|---|---|---|---|---|---|
  | clean p1 | clean | 0.0 → 0.0 | 708 → 1006 | 25.5 → 26.6 | 0.0 → 0.0 | 0.012 → 0.012 |
  | scanned p1 | clean | 0.0 → 0.0 | 708 → 1008 | 25.5 → 26.6 | 0.0 → 0.0 | 0.012 → 0.012 |
  | skewed p1 | low_quality | **-4.98 → 0.0** | 389 → 1905 | 24.3 → 31.1 | 0.0 → 0.0 | 0.012 → 0.015 |
  | low-contrast p1 | low_quality | None → None | 30 → 1531 | **5.1 → 25.3** | 0.0 → 0.0 | 0.009 → 0.010 |
  | noisy p1 | low_quality | 0.0 → 0.0 | 1726 → 2013 | 25.1 → 29.8 | **4.4 → 0.0** | 0.012 → 0.014 |
  | blank p1 | clean | None → None | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
  | PPSC-66 p-1..p-7 | clean (all) | 0.0 or None | 5237–7534 → 8644–11876 | 57–66 → 64–72 | 0.0 → 0.0 | 0.085–0.108 |

  Timings (VM: 4 vCPU, ~8 GB RAM — **VM numbers, NOT Render numbers**;
  Render free is 0.1 CPU / 512 MB, expect several-times-slower):
  clean 0.60 s/page, scanned 0.93, mixed 0.61, skewed 4.17,
  low-contrast 3.61, noisy 8.62 (two profiles compared), blank 0.37,
  PPSC-66 0.75–0.86 s/page. Fresh-process peak RSS (interpreter +
  imports ~124 MB included): clean 275 MB, skewed 316 MB,
  low-contrast 285 MB, noisy 325 MB, PPSC-66 p-1 192 MB.
- **Mark preservation (VERIFIED — the gate test):** on the clean
  fixture, all four dark marks survive ALL six profiles; colour copy
  pixel-identical in every case:

  | Profile | Underline | Tick | Star | Circle |
  |---|---|---|---|---|
  | clean | 1.017 | 1.003 | 1.027 | 1.017 |
  | default | 1.018 | 1.003 | 1.027 | 1.018 |
  | low_contrast | 1.030 | 1.003 | 1.029 | 1.020 |
  | noisy | 1.003 | 1.000 | 0.997 | 1.000 |
  | skewed | 1.018 | 1.003 | 1.027 | 1.018 |
  | low_quality | 0.989 | 1.008 | 1.076 | 1.023 |

  (Numbers are ink-retention ratios; ≥ 0.5 passes. Retention > 1
  means binarisation thickened the stroke slightly — the mark got
  bolder, not weaker.)
- **Two-profile comparison (VERIFIED):** low-quality pages run a
  second profile and record the comparison (e.g. noisy: first
  `noisy` vs second `low_quality`, chosen by measured contrast +
  sharpness without ink collapse). Blank pages are excluded from the
  comparison (a calibration fix — see §4).
- **Per-page failure isolation (VERIFIED):** a simulated render
  failure on page 2 of clean.pdf yields 1 processed + 1 failed page,
  a `page_processing_failed` error row, and the document result still
  returns. A corrupt PDF yields 0 pages + a `pdf_analysis_failed`
  error row, not an exception. An out-of-order stage
  (`COMPLETED` → PREPROCESSING) raises `ValueError`.
- **Persistence (VERIFIED):** with `SqlAlchemyStageRecorder` on
  SQLite, `document_pages` rows carry classification, method,
  skew/blur/noise/contrast, render paths and the full
  `preprocessing_applied` JSON (profile, operations, quality
  before/after, highlight regions, profile comparison).
- **Highlight detection (VERIFIED, un-gated):** the drawn yellow
  highlight on the clean fixture is detected (≥ 1 region). On the
  real PPSC-66 pages it fires 1–2 small regions per page (~205 px²,
  same size on every page) — these are UNVERIFIED candidates, most
  likely a repeated small coloured element, not confirmed highlights;
  M5 must ground-truth them. Not gated in M2.
- **CLI smoke:** `scripts/run_m2_pipeline.py` runs on a PDF and on a
  PPSC-66 PNG and prints per-page JSON (exit 0).

### Calibration notes (what the numbers forced us to change)

1. **Noise metric, redefined twice.** Whole-page high-frequency
   energy scored clean print 17.9 ("noisy" — it was text edges, not
   noise). A flat-block std-dev then filtered out exactly the noisy
   blocks it was meant to measure (noisy fixture: 7.1, below the
   threshold). The shipped metric is a median-absolute-deviation
   estimate of (gray − median-filtered gray): clean 0.0, noisy
   fixture 4.4. Threshold is 3.0 — a thin margin, and real-world
   calibration is M3 benchmark work.
2. **Skew agreement guard.** After sharpening a noisy page, Hough
   lines scattered and the median angle read 45°. `estimate_skew`
   now returns None when the line angles do not cluster (IQR > 5°).
   Skew is also None on 3 of 7 PPSC-66 pages (no dominant direction
   detected at this resolution) — recorded, not faked.
3. **Mark-check coordinate bug, found by the gate test.** The
   `low_quality` profile first appeared to destroy every mark
   (retention 0.0). Root cause was the CHECK, not the profile: it
   measured unscaled bboxes against the 1.5x-upscaled image. Fixed
   by scaling regions per image; marks were never actually lost.
4. **Upscaling removed from `low_quality`.** Upscaling a 200-DPI A4
   page 1.5x before denoising pushed fresh-process peak RSS to
   ~457 MB — too close to Render free's 512 MB for a Stage-1
   default. Peaks after removal: 285–325 MB. The upscale operation
   still exists for per-page use; only M3 OCR evidence can justify
   its cost.
5. **Blank-page comparison guard.** Blur 0 on a blank page triggered
   the second-profile comparison (4 s wasted on an empty page).
   Blank pages (ink < 0.005) now skip it (blank: 0.37 s/page).

## 4. Not verified / limitations

- **No GitHub push** (owner instruction: push later). Code is local
  on branch `officerpath-phase1-engine`; CI has never run on GitHub;
  the Docker build is verified by config only, NOT RUN (no Docker on
  the VM) — the first CI run after the push must be watched,
  including the M2 wheels in `python:3.12-slim`.
- **Render numbers are UNKNOWN.** All timings/RSS above are VM
  numbers (4 vCPU). Render free (0.1 CPU / 512 MB) will be slower
  and tighter; the noisy page's 8.6 s on the VM could be 30–60 s+
  there. M7 owns the worker, memory guard, and per-page time budget.
- **90°/180° content rotation is NOT detected.** Page rotation stored
  in the PDF is applied at render; a sideways scan inside an upright
  page needs OCR geometry (M3). Recorded as a limitation.
- **Bleed-through is not measured** (no reliable signal without a
  clean reference page) — recorded as None with the reason.
- **Skew is None on 3 of 7 PPSC-66 pages** (p-3, p-5, p-6) and after
  processing on noisy pages (agreement guard). Deskew only runs when
  a skew IS measured.
- **The two-profile comparison score favours binarisation** (it
  inflates contrast/blur), so `low_quality` usually wins the
  comparison. Whether binarisation helps OCR is an M3 benchmark
  question, not decided here.
- **Highlight detection on real pages is unverified** (see §3).
- **Upload still reads the whole file into memory** (M1 wart, M7 work).
  Preprocessing itself is one page at a time with buffers released.
- **Blur is confounded by noise** (Laplacian variance rises with
  noise: noisy fixture blur 1726 vs clean 708). Blur is only
  meaningful when noise is low; the report states this, the code
  does not "correct" it.
- Pillow was upgraded 11.3.0 → 13.0.0 for the audit fix; the suite
  passes, but CI's first run should be watched for regressions.

## 5. Risks and decisions

- **PyMuPDF AGPLv3 (ADR-004):** accepted with the repo public; if the
  engine is ever distributed closed-source, PyMuPDF must be replaced
  or licensed commercially first. Flagged for the owner, not hidden.
- **pdfplumber deferred to M3** (adds nothing for M2's scope; its
  table extraction is M3 layout work).
- **Render memory risk:** low_quality pages peak at ~285–325 MB in a
  fresh process; alongside the API server in one container that is
  tight against 512 MB. M7 must separate the worker or add a guard.
  No code change in M2 beyond removing upscale from the profile.
- **Decisions owed by the owner (unchanged from M1):** (1) add
  `officerpath-pdf-engine` to the Muse GitHub App installation, then
  push branch `officerpath-phase1-engine`; (2) go-ahead to apply
  migration 015 live; (3) Render deploy steps. None blocks M3 (local).
- No new owner decisions are needed for M2 itself.

## 6. Existing app status

Unaffected — **VERIFIED**: no file under `~/workspace/officerpath-ai`
was modified (only read: the PPSC-66 fixtures, copied read-only into
the engine repo with provenance). No live Supabase data/tables/buckets
touched; no GCP resources; no paid services; no Gemini key. The 69
pre-existing engine tests still pass, plus 44 new ones.

## 7. Next step (one clear action)

**Start M3 locally:** build the OCR abstraction + digital extractor +
Tesseract/PaddleOCR adapters behind the `OCREngine` protocol, benchmark
all engines on the golden fixtures (including the PPSC-66 pages and the
M2 synthetic set), and produce the engine benchmark report (CER/WER per
engine per fixture class). The M2 renders + quality metrics are the
inputs; nothing in M2 needs re-doing for M3 to start.

## M2 gate verdict: MET

- **Met:** quality metrics per page on all synthetic fixtures and all
  7 real PPSC-66 pages (before/after recorded, persisted to
  `document_pages`); marks preserved on fixtures (retention
  0.997–1.076 on all six profiles, colour copies byte-identical);
  classification exact per page (digital/scanned/mixed/blank);
  rendering bounded (DPI guard verified); per-page failures isolated.
- **Not met:** nothing in the gate itself. The limitations in §4
  (Render numbers, Docker build, 90° rotation, bleed-through, highlight
  ground truth) are documented M3/M7 work, not gate failures.
