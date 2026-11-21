# Milestone 3 Report — OCR + Layout (Phase 1, M3)

- **Date:** 2026-11-21
- **Branch:** `officerpath-phase1-engine` (local only — NO push; GitHub App
  install still pending, owner step)
- **Gate verdict: MET** — benchmark report written
  (`docs/benchmarks/BENCHMARK_M3_2026-11-21.md` +
  `docs/benchmarks/m3-benchmark-2026-11-21.json`) and reading order is
  correct on the multi-column fixtures (digital clean-p2
  column-order accuracy 1.0; PaddleOCR clean-p2 column-order accuracy
  1.0). Tesseract's clean-p2 failure is an engine limitation
  (PSM 3 merges columns), documented in the benchmark report, not a
  layout failure.

## Objective

Implement the M3 scope from audit §10: OCR abstraction + registry;
adapters (digital extractor, Tesseract, PaddleOCR, Gemini-advisory
disabled-by-default); per-page engine routing + disagreement handling;
layout analysis (columns, reading order, header/footer, regions,
tables, figures, cross-page continuation); golden dataset v1 with
ground-truth annotations; and the benchmark report (CER/WER per engine
per fixture class, pages/min + peak memory on stated hardware). No MCQ
extraction / answer detection / matching (M4–M6). No push, no live
Supabase, no deploys, no paid services, no GCP, no Gemini key, no
student content sent anywhere.

## Implemented (files changed)

**New — OCR (`app/pipeline/ocr/`):**
- `interfaces.py` (extended) — `PageContext` gains optional
  `image_png`, `pdf_bytes`, `dpi_used` (one page at a time);
  `OCREngine.version` is now a read-only property in the protocol.
- `normalize.py` — comparison-only normalisation (NFC + Urdu/
  Arabic-Indic digits → ASCII + collapsed whitespace; stored
  originals never touched) + `detect_script`.
- `metrics.py` — CER/WER (Levenshtein), pairwise order score,
  column-order accuracy, sequence alignment.
- `digital.py` — `DigitalExtractor` (PyMuPDF dict-blocks; exact text
  + font/size/bold/italic/colour; confidence None, never 1.0;
  reading order via shared columns module).
- `tesseract.py` — `TesseractAdapter` (eng+urd, PSM 3, word-level
  confidences, `-1` dropped) + `probe_tesseract` +
  `EngineUnavailableError` + OSD rotation probe.
- `paddle.py` — `PaddleOCRAdapter` (PP-OCRv5 Arabic-script models via
  ONNX Runtime; line-level scores only; result parsing verified
  against the real `OCRResult` dict shape).
- `gemini.py` — `GeminiAdvisoryProvider` (disabled by default; needs
  flag + key + nonzero budget; httpx, no redirects, 120 s timeout,
  call log; statuses disabled/no_key/budget_exceeded/error/
  suggestion) + verbatim Flutter prompt baseline +
  `build_ocr_request` (1000 px JPEG q88, no send) +
  `plan_crop_retry` (designed, not proven) + `MockGeminiProvider`.
- `registry.py` — `OCRRegistry` (lazy cached availability probing)
  + `default_registry` (digital always; Tesseract + PaddleOCR gated).
- `router.py` — `route_page`, `deduplicate_blocks` (IoU ≥0.5 +
  similarity ≥0.85), `compare_engines` (agreement score + flagged
  regions; both outputs stored, never silently picked).
- `service.py` — `run_ocr_stage` (PREPROCESSING→OCR_DONE, per-page
  failure isolation, persists both engines' blocks).

**New — layout (`app/pipeline/layout/`):**
- `columns.py` — shared `assign_columns` / `reading_order_indices` /
  `column_boundaries`. Column clustering by LEFT-EDGE gaps (see
  "Fixed" below); spanning blocks (width ≥0.45) assigned -1 and
  inserted by y.
- `analyzer.py` — `GeometryLayoutAnalyzer` (columns, reading order,
  header/footer positional+pattern in top/bottom 6%, region labels
  question/option/key/heading/text/noise, grid-table detection
  ≥3 rows × ≥3 short-token columns, figure candidates from
  embedded-image bboxes, optional rotation hint).
- `service.py` — `run_layout_stage` (OCR_DONE→LAYOUT_DONE; persists
  layout JSON; continuation flags at confidence 0.5; repeated
  headers on ≥3 pages promoted).

**Changed:**
- `app/config.py` — M3 settings (routing, Tesseract, PaddleOCR,
  Gemini advisory off, dataset version).
- `app/db/models.py` + `alembic/versions/0002_m3_layout_column.py` —
  nullable `layout_applied` JSON on `document_pages`.
- `app/pipeline/ingestion/service.py` — `record_ocr_blocks` on the
  `StageRecorder` protocol + both recorders.
- `scripts/build_golden_dataset.py` — golden dataset v1 (19 entries,
  25 reference texts in `app/tests/fixtures/golden/`).
- `scripts/benchmark_m3.py` + `scripts/benchmark_paddleocr_perpage.py`
  + `scripts/_paddleocr_one.py` — benchmark harness (per-engine
  fresh process; PaddleOCR per-page subprocess after the OOM kill).
- `scripts/generate_m2_fixtures.py` — highlight fix (see below);
  all M2 fixtures regenerated (manifest mark bboxes byte-identical).
- `requirements.txt` (+ pytesseract 0.3.13, pdfplumber 0.11.11,
  paddleocr 3.7.0, onnxruntime 1.32.0 — PaddleOCR optional/heavy),
  `.env.example`, `Dockerfile` (Tesseract binary + `urd`/`ara` data),
  `README.md`, `CHANGELOG.md`, `docs/deploy-render.md` (M3 PaddleOCR
  numbers), `.github/workflows/ci.yml` (Tesseract apt install for
  the test job), `docs/adr/ADR-005-ocr-engine-evaluation.md`.

**Tests (90 new, 203 total):** `test_ocr_metrics`,
`test_ocr_normalize`, `test_layout_columns`, `test_ocr_digital`,
`test_ocr_router`, `test_ocr_gemini`, `test_layout_analyzer`,
`test_ocr_tesseract`, `test_ocr_paddle`, `test_ocr_service`
(OCR + layout stages, SQLite recorder, Alembic 0002 up/down),
`test_golden_dataset` (manifest integrity + digital-extractor
cross-check of ground truth).

## Verified (commands + results)

- `pytest -q` — **203 passed, 0 failed** (113 old + 90 new) in ~53 s.
  (VERIFIED — re-run after the final layout fix.)
- `ruff check .` — all checks passed. `ruff format --check .` — 95
  files formatted. `mypy app/db app/pipeline app/storage` — no issues
  in 36 source files. (VERIFIED.)
- `pip-audit --strict` — no known vulnerabilities. (VERIFIED.)
- Alembic 0002 upgrade → downgrade → upgrade on SQLite — verified
  in `test_ocr_service.py::test_alembic_0002_layout_column`.
- **Benchmark** (full tables in
  `docs/benchmarks/BENCHMARK_M3_2026-11-21.md`):
  - Digital: CER 0.0000 / WER 0.0000 on all applicable synthetic
    pages; two-column col-acc 1.0; 0.2 s; 62.8 MB peak RSS.
  - Tesseract 5.3.4: synthetic CER 0.0027–0.0755 (clean-p2 0.5445 —
    PSM 3 column merge); PPSC-66 CER 0.068–0.152 (p1–p5),
    0.32–0.54 (p6–p7); tables 0.54/0.34; ~13 s/page; 228.7 MB.
    Fresh run reproduces the stored 20-Nov output within ~0.03–0.07
    CER on most pages — the cited "Tesseract 14–20/100" baseline is
    reproduced in character.
  - PaddleOCR 3.7.0: synthetic CER 0.016–0.024 (4× better than
    Tesseract; clean-p2 0.0243, col-acc 1.0) BUT real PPSC-66 CER
    0.31–0.43 (3–4× worse than Tesseract); tables 0.67–0.74
    (downscaled); 42–63 s/page; peak RSS 1.8–3.7 GB; OOM-killed on
    full-res 2160×3840 phone photos (twice) and on the
    single-process full pass. **Cannot run on Render free.**
  - Paper 60: no file in the source fixtures — `no_reference`,
    not run. (VERIFIED by listing the Flutter fixtures dir.)
  - Gemini 100/100: cited, NOT reproduced (no key, no calls).
- **Layout bug found and fixed by measurement:** the first
  x-overlap column clusterer chained all 37 Tesseract blocks on
  PPSC-66 p1 into one column (CER 0.61 vs the engine's 0.06).
  Left-edge clustering brings layout-order CER to 0.0935
  (VERIFIED by direct comparison on p1).
- **pdfplumber decision (VERIFIED):** 0 tables on the unruled clean
  fixture (no false positives); exact 5×4 cell grid on a synthetic
  ruled grid; same 65 words as PyMuPDF. ADOPTED for ruled digital
  tables only (M4 integration); PyMuPDF stays the text extractor.
- **Gemini advisory:** disabled by default, no key provisioned, no
  calls made (VERIFIED — no network calls in any test; mock-only
  tests + disabled/no-key/budget paths).

## Not verified / limitations

- **Render numbers:** nothing ran on Render. VM timings will be much
  worse on 0.1 CPU; no factor claimed. PaddleOCR on Render free is
  ruled out by measurement (3.7 GB peak vs 512 MB), not by guess.
- **90°/180° rotation:** OSD probe implemented (returns 0° on upright
  fixtures) but no rotated fixture benchmarked (M2 limitation carried).
- **Bleed-through:** not measured (no reference page).
- **Skew on PPSC-66 p-3/p-5/p-6:** M2 reported skew None; Tesseract
  still read p3/p5 at CER 0.07–0.15.
- **Recitation filter:** not observed in M3 (no Gemini calls). Crop
  retry is designed, unproven; needs a keyed test (M6/M7).
- **Nastaliq:** no Urdu Nastaliq fixture with ground truth exists;
  no Nastaliq claim is made about any engine.
- **Order scores on p3/p4/p5 (0.37–0.46)** are confounded by
  Tesseract's line-merging vs the reference's one-option-per-line
  plus the p3 crop-stitch reference (verified) — see the benchmark
  report. A segmentation-insensitive order metric is owed.
- **PaddleOCR tables** were measured downscaled (max 1600 px) after
  two full-res OOM kills; labelled as such in the merged JSON.
- **Tesseract clean-p2 (CER 0.5445)** needs column splitting before
  OCR (M4/M5); the layout cannot fix engine-merged blocks.
- **Router is deployment-blind:** it prefers PaddleOCR on scanned
  pages whenever available. On Render free it must be disabled via
  `PADDLEOCR_ENABLED=false` or omitted from requirements until M4
  makes routing deployment-aware.
- No Docker run locally (no Docker on the VM); no CI run on GitHub
  yet (no push — owner step). Dockerfile/CI changes are UNVERIFIED
  until the first CI run after the push.

## Risks and decisions

- **PaddleOCR demoted to VPS-only** (ADR-005): it wins on clean
  synthetic text but loses 3–4× to Tesseract on the real paper and
  needs 1.8–3.7 GB/page. The Stage-1 OCR path is Gemini-vision
  (keyed) or Tesseract — unchanged from ADR-002's intent, now with
  numbers.
- **Tesseract alone cannot carry M4/M5** on key pages (p6 CER 0.54,
  p7 0.32, tables 0.34–0.54). Exact question/option/key matching
  needs Gemini-advisory or better preprocessing; M4 must not assume
  clean OCR input.
- **M2 fixture bug fixed in M3:** the generator drew the highlighted
  option twice, duplicating "(B) Lahore" in the text layer. Fixed
  (rect before text, once) and all fixtures regenerated; manifest
  bboxes identical; suite still green. Ground truth now matches the
  PDF exactly (title extracts as "·" under Helvetica/WinAnsi — the
  generator writes "—"; recorded in the dataset builder).
- **Paper 60 gap:** the third acceptance file has no file in the
  Flutter test-fixtures at all. The dataset keeps the entry with
  `reference_kind: none` so the gap stays visible.
- **Memory discipline:** the benchmark OOM-killed three processes
  during M3 (one single-process PaddleOCR pass, two table retries,
  one concurrent Tesseract run). All are recorded as measured
  failures with exit 137, never hidden. The VM needs ~4 GB free per
  PaddleOCR page; don't run heavy engines concurrently.

## Existing app status

- Flutter app v2.0.5 is unchanged and untouched by M3 (only its
  test-fixtures were read, never modified). The engine remains
  local-only on branch `officerpath-phase1-engine`; the GitHub
  remote still has no push (owner step: add the repo to the Muse
  GitHub App installation, then push). Migration 015 still not
  applied live; Render deploy still an owner step. No live Supabase
  changes in M3.

## Next step (one clear action)

Start M4 locally on the same branch (owner go-ahead needed):
MCQ/option extraction + answer detection on top of the M3 OCR
blocks + layout — with the M3-measured input quality in mind
(Tesseract CER 0.07–0.15 on question pages, 0.32–0.55 on key
pages; Gemini-advisory still keyless until the owner provisions
the server key). M4 must also make routing deployment-aware
(PaddleOCR off on Render free) and add a Nastaliq fixture before
any Nastaliq claim.

## M3 gate verdict: MET

Evidence: (1) benchmark report + merged JSON written with
per-engine CER/WER per fixture class, pages/min + peak memory on
stated hardware, and every poor number reported;
(2) reading order correct on the multi-column fixtures — digital
clean-p2 column-order accuracy 1.0 and PaddleOCR clean-p2
column-order accuracy 1.0 (the Tesseract clean-p2 failure is an
engine column-merge, measured and documented, not a layout
failure); (3) 203 tests passing, ruff + mypy clean, pip-audit
clean. The gate's two deliverables exist and are measured, not
asserted.
