# Benchmark M3 — OCR engines + layout on golden dataset v1

- **Date:** 2026-11-21
- **Dataset:** golden v1 (`app/tests/fixtures/golden/dataset.json`, 19 entries)
- **Hardware (VERIFIED):** dev VM, 4 vCPU, 8 GB RAM (shared cell, 1.5 CPU
  quota), Python 3.12. **All timings and memory numbers are VM numbers.
  They are NOT Render numbers** (Render free is 0.1 CPU / 512 MB).
- **Engines:** digital extractor (PyMuPDF 1.26.3), Tesseract 5.3.4
  (eng+urd, PSM 3, 200-DPI renders), PaddleOCR 3.7.0 (PP-OCRv5 server
  det + `arabic_PP-OCRv5_mobile_rec`, ONNX Runtime 1.32.0),
  stored-Tesseract (20-Nov output files, same Tesseract 5.3.4).
- **Method:** `scripts/benchmark_m3.py` (one fresh process per engine;
  peak RSS is the fresh-process peak via `ru_maxrss`). PaddleOCR ran
  one fresh process per page (`scripts/benchmark_paddleocr_perpage.py`)
  because the single-process pass was OOM-killed (exit 137). CER/WER
  use the comparison normalisation (NFC + Urdu/Arabic-Indic digits
  unified + whitespace collapsed). Order score is the pairwise
  line-order score; column-order accuracy is the two-column check.
- **Machine-readable results:** `docs/benchmarks/m3-benchmark-2026-11-21.json`
- **What "reference" means:** synthetic pages measure against EXACT
  ground truth. PPSC-66 pages and table photos measure against the
  Gemini OCR text (model `gemini-3.5-flash-lite`, the app's own
  prompt) — i.e. how close an engine comes to Gemini's reading, NOT
  to the printed page. Only p1 was hand-verified (1 word error in
  ~700 words: "(C) Ala" should be "(C) A/a"; Q1–Q9 numbers are cut
  off at the scan's left edge and absent from the reference).

## Headline results (VERIFIED)

| Engine | Best case | Real PPSC-66 pages | Speed (VM) | Peak RSS (VM) |
|---|---|---|---|---|
| Digital (PyMuPDF) | CER 0.0000 everywhere applicable | n/a (no text layer) | 0.2 s / 5 pages | 62.8 MB |
| Tesseract 5.3.4 | CER 0.0027–0.0755 synthetic | CER 0.068–0.152 (p1–p5), 0.32–0.54 (p6–p7) | ~13 s/page real | 228.7 MB |
| PaddleOCR 3.7.0 | CER 0.016–0.024 synthetic | CER 0.31–0.43 (p1/p3/p6) | 42–63 s/page | 1,775–3,667 MB |
| Stored Tesseract (20 Nov) | — | CER 0.066–0.55 | n/a (stored files) | — |

No engine is claimed at 100% accuracy. The poor numbers are reported
alongside the good ones; the sections below explain each.

## Per-engine tables

### Digital extractor — exact (VERIFIED)

| Entry | CER | WER | Order | s | Blocks | Cols |
|---|---|---|---|---|---|---|
| synthetic-clean-p1 | 0.0000 | 0.0000 | 1.000 | 0.01 | 9 | 1 |
| synthetic-clean-p2 (two-column) | 0.0000 | 0.0000 | 1.000 | 0.00 | 9 | 2, col-acc 1.0 |
| synthetic-mixed-p1 | 0.0000 | 0.0000 | 1.000 | 0.00 | 9 | 1 |
| synthetic-low_contrast-p1 | 0.0000 | 0.0000 | 1.000 | 0.00 | 9 | 1 |
| synthetic-blank-p1 | 0.0000 | 0.0000 | 1.000 | 0.00 | 0 | 0 |

Scanned entries are `not_applicable_digital` by design (no text
layer to extract). The digital extractor reproduces the fixture
ground truth exactly, including the two-column reading order — the
ground truth itself is cross-checked this way (the benchmark asserts
CER 0.0 in `test_golden_dataset.py`).

### Tesseract 5.3.4 (eng+urd, PSM 3) — the offline fallback (VERIFIED)

| Entry | CER | WER | Order | s | Blocks | Cols |
|---|---|---|---|---|---|---|
| synthetic-clean-p1 | 0.0755 | 0.1231 | 1.000 | 1.34 | 5 | 1 |
| synthetic-clean-p2 | **0.5445** | 0.7077 | 1.000 | 1.69 | 3 | 1, col-acc 1.0* |
| synthetic-scanned-p1 | 0.0755 | 0.1231 | 1.000 | 1.32 | 5 | 1 |
| synthetic-mixed-p1 / p2 | 0.0755 | 0.1231 | 1.000 | 1.32/1.68 | 5 | 1 |
| synthetic-skewed-p1 (+5°) | 0.0943 | 0.1692 | 1.000 | 2.05 | 11 | 1 |
| synthetic-low_contrast-p1 | 0.0027 | 0.0154 | 1.000 | 1.18 | 5 | 1 |
| synthetic-noisy-p1 | 0.0728 | 0.1077 | 1.000 | 3.33 | 6 | 1 |
| synthetic-blank-p1 | 0.0000 | 0.0000 | 1.000 | 0.48 | 0 | 0 |
| ppsc66-p1 | 0.0935 | 0.1627 | 0.696 | 11.08 | 38 | 3 |
| ppsc66-p2 | 0.1113 | 0.2329 | 0.638 | 14.47 | 44 | 3 |
| ppsc66-p3 | 0.0681 | 0.1357 | 0.367 | 17.02 | 31 | 3 |
| ppsc66-p4 | 0.1273 | 0.2343 | 0.457 | 15.86 | 41 | 3 |
| ppsc66-p5 | 0.1519 | 0.2703 | 0.438 | 18.82 | 38 | 3 |
| ppsc66-p6 | **0.5368** | 0.6454 | 0.875 | 20.89 | 28 | 4 |
| ppsc66-p7 | 0.3183 | 0.4049 | 0.844 | 15.05 | 20 | 4 |
| ppsc66-table-computer-q67-81 | 0.5410 | 0.6757 | 1.000 | 10.53 | 48 | 5 |
| ppsc66-table-interjection-q230-257 | 0.3434 | 0.5668 | 1.000 | 19.65 | 4 | 2 |

\* clean-p2's order 1.0 / col-acc 1.0 are computed over the tiny
matched subset — the CER 0.5445 is the real story there (see below).

Total: 195.4 s for 18 pages; peak RSS 228.7 MB.

**Clean-p2 (CER 0.5445):** PSM 3 merges the two columns into single
lines ("1. What is the capital of Pakistan? 3. The largest desert
of Pakistan is?" on one line, verified by dumping the blocks). The
layout stage cannot un-merge blocks the engine already merged.
Column splitting before OCR is future work (M4/M5). PSM 6 is worse
on these pages (p1 CER 0.68, a single block) — PSM 3 stays default.

**p6 (CER 0.5368, worst real page):** its bottom half is a dense
answer-key grid in small type, and the page starts mid-question
(the reference opens mid-sentence, "college."). p7 (0.3183) is
second worst. Both are the pages where exact key extraction matters
most — Tesseract alone cannot carry M4/M5 on them.

**Order scores on p3/p4/p5 (0.367–0.457) are not reliable evidence
about reading order.** The metric matches whole lines exactly, and
on these pages Tesseract merges each option row into one line
("(A) Aqua-group (B) Swarm") while the Gemini reference lists one
option per line — 79 of p3's 110 reference lines have no exact match
in the hypothesis (verified by direct comparison), so the score is
computed over a small, unrepresentative subset. The p3 reference is
also a crop-stitch with uneven coverage (verified: its 7 source
crops contribute 0–100% of their lines verbatim). Fresh and stored
Tesseract runs give nearly identical order scores on these pages
(0.367/0.457/0.433), confirming the score is dominated by the
reference's line structure and the engine's segmentation, not by
the layout. The character content is present (CER 0.07–0.15) and the
matched lines appear in question order. A segmentation-insensitive
order metric is needed before these scores can be read as layout
quality.

### Stored Tesseract (20-Nov output files — no engine run) (VERIFIED)

| Entry | CER | WER | Order |
|---|---|---|---|
| ppsc66-p1 | 0.0663 | 0.1257 | 0.704 |
| ppsc66-p2 | 0.1189 | 0.2314 | 0.638 |
| ppsc66-p3 | 0.0678 | 0.1311 | 0.367 |
| ppsc66-p4 | 0.1247 | 0.2360 | 0.457 |
| ppsc66-p5 | 0.1522 | 0.2576 | 0.433 |
| ppsc66-p6 | 0.5515 | 0.6739 | 0.844 |
| ppsc66-p7 | 0.3895 | 0.4553 | 0.817 |
| table-computer | 0.5860 | 0.7402 | 1.000 |
| table-interjection | 0.3315 | 0.5560 | 1.000 |

The fresh run reproduces the stored baseline within ~0.03–0.07 CER
on most pages (p7 differs more: 0.3183 fresh vs 0.3895 stored —
the stored run's exact input pipeline is unknown, 20 Nov, Flutter
repo). The cited baseline "Tesseract 14–20/100" is consistent with
these CERs: a parser needs near-exact text, and CER 0.07–0.15 on
question pages plus 0.32–0.55 on key pages breaks exact
question/option/key matching. The baseline is reproduced in
character, not claimed as an exact re-measurement (the 20-Nov parse
score method is not recorded).

### PaddleOCR 3.7.0 (PP-OCRv5, ONNX engine) (VERIFIED)

Per-page subprocess (the single-process pass OOM-killed, exit 137).

| Entry | CER | WER | Order | s | Blocks | Cols | Peak RSS |
|---|---|---|---|---|---|---|---|
| synthetic-clean-p1 | 0.0162 | 0.0462 | 1.000 | 62.69 | 21 | 1 | 3,586 MB |
| synthetic-clean-p2 | 0.0243 | 0.1077 | 1.000 | 58.31 | 21 | 2, col-acc 1.0 | 3,667 MB |
| synthetic-scanned-p1 | 0.0243 | 0.0923 | 1.000 | 55.70 | 21 | 1 | 3,653 MB |
| ppsc66-p1 | 0.3434 | 0.4270 | 0.649 | 56.10 | 189 | 5 | 1,775 MB |
| ppsc66-p3 | 0.3128 | 0.4055 | 0.406 | 57.00 | 168 | 5 | 1,776 MB |
| ppsc66-p6 | 0.4316 | 0.5489 | 0.961 | 42.29 | 199 | 5 | 1,782 MB |
| table-computer † | 0.6692 | 0.8132 | 1.000 | 34.23 | 162 | 8, 2 tables | 1,707 MB |
| table-interjection † | 0.7380 | 0.8520 | 1.000 | 40.76 | 261 | 7, 2 tables | 1,708 MB |

† Downscaled to max 1600 px (900×1600): the full-resolution
2160×3840 phone photos OOM-killed the per-page process twice
(exit 137), even in isolation with ~6 GB free.

Total for the 8 pages: 614.6 s; max single-page peak RSS 3,667 MB.

**Two findings, both against the prior expectation:**

1. **On clean synthetic text PaddleOCR is 4× better than Tesseract**
   (CER 0.016–0.024 vs 0.0755), and it separates two-column text
   where Tesseract merges it (clean-p2 CER 0.0243 vs 0.5445,
   column-order accuracy 1.0).
2. **On the real PPSC-66 pages PaddleOCR is 3–4× WORSE than
   Tesseract** (CER 0.31–0.43 vs 0.07–0.15 on p1/p3; 0.43 vs 0.54
   on p6 — its only win). The Arabic-script model does not read
   this English printed book well. On the key-grid tables it is
   worst of all (0.67–0.74 vs Tesseract 0.34–0.54).

**Cost rules it out of Stage 1:** 42–63 s/page on a 4-vCPU VM and
1.8–3.7 GB peak RSS per page — 7× the Render free 512 MB. It
OOM-kills on full-resolution phone photos on an 8 GB VM. PaddleOCR
is a VPS-only option (Hostinger Stage 2, 4 GB — and even there,
phone photos need downscaling), never a Render free engine.

**Nastaliq:** still UNPROVEN. These PPSC pages are Latin script; the
dataset has no Urdu Nastaliq fixture with ground truth, so no
Nastaliq claim is made about any engine. M4/M5 must add one.

## Layout findings (VERIFIED)

- **Column clustering by left edge, not x-overlap.** The first
  version clustered by x-interval overlap (single-linkage) and
  chained all 37 Tesseract blocks on PPSC-66 p1 into ONE column —
  long lines bridge the gutter — giving y-order reading and CER
  0.61 where the engine's own order scores 0.06. Left-edge (x_min)
  gap clustering separates p1 cleanly (left 0.05–0.09, right
  0.47–0.48) and brings layout-order CER to 0.0935. Both the
  failure and the fix are measured above (the first tesseract pass
  ran with the old clustering: p1 0.6145, p2 0.6996, p7 0.6167).
- **Reading order on the multi-column fixture (the M3 gate):**
  digital clean-p2 column-order accuracy 1.0, PaddleOCR clean-p2
  column-order accuracy 1.0. Tesseract clean-p2 fails at the engine
  level (column merge, CER 0.5445) — not a layout failure.
- The layout finds 3 columns on PPSC question pages (two question
  columns + a top-right header group) and 4–8 on key/table pages.
  The header group reading last costs ~0.03 CER vs the engine's
  native order on p1 (0.0935 vs 0.0636). Headers are flagged as
  header/footer metadata; M4 excludes them from question text.
- **Grid tables:** detected from PaddleOCR's line-level blocks
  (2 tables per table photo; 3 on p1, 1 each on p3/p6) but NOT from
  Tesseract blocks (0 everywhere). Tesseract merges each table row
  into one wide block (visible in the stored 20-Nov output: whole
  rows on single lines), so the detector's input has no cell
  structure. The detector is correct; its Tesseract input is not
  cell-structured. pdfplumber's ruled-table extraction (5×4 grid
  recovered exactly on a synthetic ruled grid, 0 tables on the
  unruled clean fixture) is adopted for digital pages in M4 — see
  ADR-005.

## Recitation-filter behaviour

NOT observed in M3: no Gemini calls were made (no key provisioned),
so the VM baseline's pp. 3/5 block cannot be reproduced or
disproved here. The mitigation (page crops + `[?]` marking) is
designed in the Gemini adapter (`plan_crop_retry`) and unproven. A
keyed test is owed in M6/M7. The p3 reference exists only because
the baseline used crops — its stitch order is part of why p3's
order score is unreliable (above).

## What was NOT measured (UNVERIFIED / UNKNOWN)

- **Render numbers:** nothing was run on Render. VM timings
  (Tesseract ~13 s/page, PaddleOCR 42–63 s/page) will be much worse
  on 0.1 CPU; no factor is claimed.
- **90°/180° rotation:** the Tesseract OSD probe is implemented and
  returns 0° on upright fixtures, but no rotated fixture was
  benchmarked (M2 limitation carried forward).
- **Bleed-through:** not measured (no reference page).
- **Skew on PPSC-66 p-3/p-5/p-6:** M2 reported skew None there;
  Tesseract still read p3/p5 at CER 0.07–0.15, so the pages are
  readable despite the unmeasured skew.
- **Paper 60:** no file exists in the source fixtures (checked
  2026-11-21) — recorded as `no_reference`, not run.
- **Gemini 100/100:** cited from the 20-Nov VM baseline, NOT
  reproduced in M3 (no key, no calls). Nothing in this report
  confirms or contradicts it.
- **Pages/minute:** Tesseract ≈ 4.6 real pages/min on the VM
  (195.4 s / 18 pages incl. synthetic); PaddleOCR ≈ 1.0–1.4
  pages/min; digital ≈ 1,500 pages/min (0.2 s / 5 pages). All VM
  rates, not Render rates.

## Reproducing this benchmark

```bash
.venv/bin/python scripts/benchmark_m3.py --engine digital --out /tmp/m3-digital.json
.venv/bin/python scripts/benchmark_m3.py --engine tesseract --out /tmp/m3-tesseract.json
.venv/bin/python scripts/benchmark_m3.py --engine stored-tesseract --out /tmp/m3-stored.json
HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/benchmark_paddleocr_perpage.py --out /tmp/m3-paddleocr.json
.venv/bin/python scripts/benchmark_m3.py --merge /tmp/m3-digital.json /tmp/m3-tesseract.json /tmp/m3-paddleocr.json /tmp/m3-stored.json --out docs/benchmarks/m3-benchmark-2026-11-21.json
```

Notes: PaddleOCR needs `HF_HUB_DISABLE_XET=1` (Hugging Face xet
downloads stall on this VM's proxy) and ~4 GB free RAM per page;
the table photos need downscaling to max 1600 px or they OOM.
Tesseract needs the system binary + `urd`/`ara` data installed.
