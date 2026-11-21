# ADR-005 — OCR engine evaluation (M3)

- **Status:** ACCEPTED (2026-11-21)
- **Context:** ADR-002 (hybrid OCR: digital first, Gemini-advisory when a
  server key exists, PaddleOCR/Tesseract fallback). M3 had to decide
  each engine on measurements, not on the vendors' claims — in
  particular whether PP-OCRv5's Arabic-script model reads the real
  fixtures (Nastaliq quality was UNPROVEN), whether Tesseract
  eng+urd is usable, and whether pdfplumber adds anything over
  PyMuPDF.
- **Decision:** keep all four engines behind the registry, with the
  routing and the deployment consequences below. PaddleOCR is
  demoted from "fallback" to "VPS-only option": it cannot run in the
  Render free envelope at all (measured).

## What was measured (all VERIFIED, 2026-11-21)

Hardware: dev VM, 4 vCPU, 8 GB RAM (shared cell, 1.5 CPU). Every
number below is a VM number, never a Render number. Dataset: golden
v1 (`app/tests/fixtures/golden/dataset.json`, 19 entries). Full
tables: `docs/benchmarks/BENCHMARK_M3_2026-11-21.md` and the merged
JSON `docs/benchmarks/m3-benchmark-2026-11-21.json`.

### Digital extractor (PyMuPDF 1.26.3)

- CER 0.0000 / WER 0.0000 on every applicable synthetic page
  (clean p1/p2, mixed p1, low-contrast p1, blank p1). Two-column
  reading order correct (column-order accuracy 1.0 on clean p2).
- 0.2 s for the whole pass; peak RSS 62.8 MB.
- Decision: **the digital extractor is exact and stays the first
  route for every page with a text layer.** No OCR runs on digital
  pages.

### Tesseract 5.3.4 (eng+urd, PSM 3, 200-DPI renders)

- Synthetic clean text: CER 0.0755 (WER 0.1231). Low-contrast:
  0.0027. Skewed (+5°): 0.0943. Noisy: 0.0728. Reading order 1.0
  on all synthetic pages.
- **Two-column synthetic page: CER 0.5445.** PSM 3 merges the two
  columns into single lines ("Q1 text Q3 text" on one line) — the
  layout stage cannot un-merge blocks the engine already merged.
  Column splitting before OCR is future work (M4/M5), not an M3 fix.
- PPSC-66 real pages (vs Gemini reference): p1 0.0935, p2 0.1113,
  p3 0.0681, p4 0.1273, p5 0.1519, p6 0.5368, p7 0.3183. Tables:
  computer 0.5410, interjection 0.3434.
- The fresh run reproduces the stored 20-Nov Tesseract output
  within ~0.03–0.07 CER on most pages (stored: p1 0.0663, p2
  0.1189, p3 0.0678, p4 0.1247, p5 0.1522, p6 0.5515, p7 0.3895;
  tables 0.5860 / 0.3315). The cited baseline "Tesseract 14–20/100"
  is consistent with these CERs: a parser needs near-exact text,
  and CER 0.07–0.15 on question pages plus 0.32–0.55 on key pages
  breaks exact question/option/key matching.
- p6 is the worst real page (0.5368): its bottom half is a dense
  answer-key grid in small type, and the page starts mid-question.
  p7 (0.3183) is the second worst.
- Reading-order scores on p3/p4/p5 (0.367/0.457/0.438) at CER
  0.068–0.152 are NOT reliable evidence about reading order: the
  metric matches whole lines exactly, and on these pages Tesseract
  merges each option row into one line ("(A) Aqua-group (B)
  Swarm") while the Gemini reference lists one option per line —
  79 of p3's 110 reference lines have no exact match in the
  hypothesis, so the score is computed over a small, unrepresentative
  subset. The p3 reference is also a crop-stitch with uneven
  coverage (verified: its 7 source crops contribute 0–100% of
  their lines verbatim). Fresh and stored Tesseract runs give
  nearly identical order scores on these pages (0.367/0.457/0.433),
  which confirms the score is dominated by the reference's line
  structure and the engine's segmentation, not by the layout. A
  segmentation-insensitive order metric is needed before these
  scores can be read as layout quality. The character content is
  present (CER 0.07–0.15) and the matched lines appear in question
  order.
- Cost: 195.4 s for 18 pages (~13 s/page on real pages); peak RSS
  228.7 MB. Needs the system binary + `urd`/`ara` traineddata
  (apt: `tesseract-ocr tesseract-ocr-urd tesseract-ocr-ara`;
  Dockerfile + CI install them). PSM 6 is worse on these pages
  (p1 CER 0.68, one block) — PSM 3 stays the default.
- Decision: **Tesseract is the offline fallback.** It is the only
  OCR engine that fits the Render free envelope (229 MB peak).

### PaddleOCR 3.7.0 (PP-OCRv5, ONNX Runtime engine)

- Install: `paddleocr 3.7.0` ships WITHOUT `paddlepaddle`;
  plain `PaddleOCR(lang='ar')` fails ("Engine 'paddle_static' is
  unavailable"). The adapter runs the ONNX Runtime engine via a
  full pipeline config (`engine: onnxruntime` at top level).
  Models resolved for `lang='ar'`: det `PP-OCRv5_server_det`,
  rec `arabic_PP-OCRv5_mobile_rec` (verified in the installed
  package source). Models download ~50–100 MB on first use into
  `~/.paddlex/official_models/`; Hugging Face downloads stall on
  this VM's proxy unless `HF_HUB_DISABLE_XET=1` is set (xet
  protocol stalls at ~85 MB) — CI/Docker must set it.
- Synthetic clean text: CER 0.0162–0.0243 — **4× better than
  Tesseract**, and the two-column page scores 0.0243 with
  column-order accuracy 1.0 (its detector separates columns where
  Tesseract PSM 3 merges them).
- **Real PPSC-66 pages: CER 0.31–0.43 (p1 0.3434, p3 0.3128,
  p6 0.4316) — 3–4× WORSE than Tesseract on the same pages.**
  The Arabic-script model does not read this English printed book
  well. Nastaliq quality remains unproven (these pages are Latin
  script; no Nastaliq fixture exists in the dataset to test
  against). No claim is made either way.
- Tables (downscaled to max 1600 px, see below): computer 0.6692,
  interjection 0.7380 — worse than Tesseract (0.5410 / 0.3434).
  The geometry grid detector DID find 2 tables per photo from
  PaddleOCR's line-level blocks (162/261 blocks), where Tesseract's
  row-merged blocks yield 0 tables.
- **Cost — the decision driver: 42–63 s/page on the VM; peak RSS
  1.8–3.7 GB per page.** The single-process full-dataset pass was
  OOM-killed (exit 137); the per-page subprocess pass also
  OOM-killed both full-resolution (2160×3840) table photos twice.
  3.7 GB is 7× the Render free 512 MB. **PaddleOCR cannot run on
  Render free, full stop.** It is a VPS-only option (Hostinger
  Stage 2, 4 GB — and even there, phone photos need downscaling).
- Decision: **PaddleOCR stays in the registry as an optional,
  availability-gated engine (omitted from slim builds), routed
  only where it wins — clean synthetic/digital-render text — and
  never on Render free.** The router prefers it for scanned pages
  only when it is available AND the deployment can afford it; the
  M4 router work must make that deployment-aware (currently the
  router prefers PaddleOCR whenever available — see Consequences).

### Gemini advisory (disabled by default, no key)

- Built as specified: `GeminiAdvisoryProvider` needs the enabled
  flag AND a server key AND a nonzero daily budget; with any of
  those missing it reports `disabled`/`no_key` and never calls.
  No key is provisioned, no call was made, no student content left
  the VM. The request builder reuses the Flutter prompt verbatim
  (transcribe exactly, `[?]` for unreadable, left-column-first,
  1000 px JPEG q88, 2048 max tokens) and flags any deviation from
  it. Crop retry (left/right halves) is designed for the
  recitation-filter risk (VM baseline pp. 3/5 blocked) but is NOT
  proven — it needs a keyed test in M6/M7.
- Decision: **unchanged from ADR-002 — advisory only, disabled by
  default, suggestions never verified answers.** The 100/100
  Gemini baseline is cited, not reproduced (no key, no calls).

### pdfplumber 0.11.11 — decision: ADOPTED for ruled digital tables only

- Measured: on the M2 clean fixture, `extract_tables` finds 0
  tables (no false positives) and `extract_words` gives the same
  65 words PyMuPDF gives — no value as a text extractor.
- On a synthetic ruled 5×4 answer-key grid, `extract_tables`
  returns the cell-aligned grid (5 rows × 4 cols, first row
  `['1A', '1B', '1C', '1D']`) where PyMuPDF words give 20 words
  with no cell structure.
- Decision: **pdfplumber is adopted as the ruled-table extractor
  for DIGITAL pages only; PyMuPDF stays the digital text
  extractor.** Integration is deferred to M4 (answer-key grids):
  the layout stage will accept optional `ruled_tables` from
  pdfplumber alongside the geometry grid detector (which is the
  only option on scanned pages). pdfplumber adds nothing on
  scanned pages and is never a text extractor.

## Layout findings (folded into the benchmark)

- Column clustering by left edge (x_min gaps), NOT x-interval
  overlap: the first overlap version chained all 37 Tesseract
  blocks on PPSC-66 p1 into ONE column (long lines bridge the
  gutter), giving y-order reading and CER 0.61 where the engine's
  own order scores 0.06. Left-edge clustering separates p1
  (left 0.05–0.09, right 0.47–0.48) and brings layout-order CER to
  0.0935. The failure and the fix are both in the benchmark report.
- The layout finds 3 columns on PPSC question pages (two question
  columns + a top-right header group) and 4–5 on key pages; the
  header group reading last costs ~0.03 CER vs the engine's native
  order. Headers are flagged as header/footer metadata by the
  analyser; M4 excludes them from question text.
- Grid tables: detected from PaddleOCR line-level blocks (2 per
  table photo) but NOT from Tesseract blocks (0) — Tesseract
  merges each table row into one wide block (visible in the stored
  20-Nov output: whole rows on single lines), so the detector's
  input has no cell structure. The detector is correct; its
  Tesseract input is not cell-structured.

## Consequences

- Render free (Stage 1) OCR: Gemini-vision when a server key
  exists, Tesseract otherwise. PaddleOCR is NOT deployed there
  (docs/deploy-render.md updated with the measured numbers).
- The router's current preference (PaddleOCR first on scanned
  pages when available) is deployment-blind: on a Render-free
  deployment PaddleOCR must be disabled via
  `PADDLEOCR_ENABLED=false` or omitted from requirements, or the
  router will try to load a 3.7 GB pipeline into a 512 MB
  container. M4 must make routing deployment-aware; until then the
  deploy docs carry the warning and the slim-build note.
- CI installs the full requirements (PaddleOCR ~2 min, ~900 MB
  venv) but never runs the predictor in unit tests (parse-only
  tests + the benchmark script). CI installs the Tesseract system
  packages for the real-binary tests.
- `HF_HUB_DISABLE_XET=1` must be set wherever PaddleOCR models
  download (CI/Docker/VM), or the download stalls.
- No Nastaliq measurement exists yet: the dataset has no Urdu
  Nastaliq fixture with ground truth. M4/M5 must add one before
  any Nastaliq claim is made about any engine.
