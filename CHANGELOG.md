# CHANGELOG — officerpath-pdf-engine

All notable changes to this project. Dates in PKT (Asia/Karachi).

## [2.10.0] — 2026-11-23 — Phase 2 M10: complete QA + deployment readiness (FINAL Phase 2 milestone)

### Added
- Async-jobs dedup fix (M7 edge, carried from M9 §6.5): re-submitting
  identical bytes to `POST /api/v1/async-jobs/parse` no longer 500s
  on the unique index — it returns the ORIGINAL job with 200 +
  `idempotent_replay: true`, consistent with the register contract;
  a race guard re-reads the winner on `IntegrityError`. Regression
  tests: replay returns original job (done status), replay after
  soft-delete creates a fresh job, same bytes from another user are
  fresh.
- Migration runbook (`docs/phase2/migration-runbook.md`): ordered
  owner steps for Supabase 016 + 017 + Alembic 0001–0009, with
  verification queries and failure handling.
- Rollback runbook (`docs/phase2/rollback-runbook.md`): separate
  web (Vercel) and engine (Render) rollback, Alembic downgrade
  behaviour per revision 0003–0009 (incl. which refuse with rows).
- Phase 2 completion report (`docs/phase2/PHASE_2_COMPLETION_REPORT.md`):
  M1–M10 summary, final tables, architecture, ADRs, limitations,
  and every remaining owner step listed honestly.

### Changed
- `render.yaml` branch: `officerpath-phase1-engine` →
  `officerpath-phase2-web`.
- Performance tuning (Lighthouse TBT): `QueryClientProvider` moved
  out of the root layout into the dashboard + admin layouts only —
  public pages no longer load the TanStack Query chunk (see
  MILESTONE_10_REPORT.md for before/after Lighthouse numbers).
- `CHANGELOG.md` + `TEST_REPORT.md` refreshed (were stale since
  M4 / M0).

### Verified
- Full gate (pytest + ruff + mypy + tsc + npm build + lint +
  Playwright E2E) green; the three acceptance files (PPSC-66 PDF,
  computer table photo, Paper 60 photo) parsed end-to-end through
  the WEB UI against the local backend — counts quoted in
  MILESTONE_10_REPORT.md. No deploy happened in M10.

## [2.9.0] — 2026-11-23 — Phase 2 M9: admin foundation, notifications, security + SEO

### Added
- Admin foundation (GAP-10): admin = `app_metadata.is_admin` claim
  from the VERIFIED JWT only; `require_admin` dependency (non-admin
  → 404 `not_found` on all 6 admin routes); 6 admin endpoints
  (overview/users/documents/jobs/errors/questions, real rows,
  paginated); `/admin/*` pages (6 + server guard).
- Notifications (GAP-9, Alembic 0009): `notifications` table
  (per-user only, no broadcast); rows written by real flows in the
  same transaction (upload done/failed, test submitted + result
  ready); `GET /api/v1/notifications` + `PATCH .../read`
  (idempotent); `/dashboard/notifications` + live unread badge.
- SEO: canonical + OG + JSON-LD Organization/WebSite on home, no
  FAQ JSON-LD (no real FAQ section); noindex on `/dashboard/*`,
  `/admin/*`, auth pages (metadata + X-Robots-Tag); robots.txt
  disallows `/dashboard/` `/admin/` `/auth/` `/api/`; sitemap lists
  11 public pages. PWA manifest + icons (no service worker, no
  offline — not claimed).
- Security hardening: engine security headers middleware
  (nosniff/DENY/strict-origin-when-cross-origin/Permissions-Policy/
  CSP `default-src 'none'`); CORS final (exact origins, never `*`).

### Fixed
- **M7 design flaw (found by measuring):** the exam session
  returned `correct_index` + `answer_source` mid-test (key readable
  from the network tab) — fixed with `SessionSnapshotItem` (no key,
  only `is_unknown`); 2 M7 tests updated to the new contract.
- Admin questions counted soft-deleted docs' questions (131 vs live
  bank 91) — fixed with `deleted_at IS NULL` join.

### Verified
- pytest 610/0 (parent re-ran, 833.37s); OpenAPI 41 → 49 paths;
  Lighthouse 13.6.0 localhost: Home 73/96/100/100, Features
  60/94/100/100 (TBT-bound under VM throttling).

## [2.8.0] — 2026-11-23 — Phase 2 M8: results + student analytics

### Added
- Results + analytics (GAP-7 + GAP-8, Alembic 0008
  `student_question_collections`): subject/topic breakdowns at
  submit + recompute-on-read backfill for M7 NULL rows; weak/strong
  areas (named subjects, ≥3 scored); `GET /api/v1/results`;
  `POST /tests/{id}/retry` (byte-identical snapshots);
  `POST /tests/from-mistakes` (original snapshots, never the live
  bank); collections API (bookmark-once = idempotent-200); mistake
  rows written in the same submit transaction.
- Frontend: `/dashboard/tests/[id]/result`, `/dashboard/results`
  (history, compare-over-time only with ≥2 attempts),
  `/dashboard/mistakes` (notes, bookmark toggle, practice button).

### Verified
- pytest 593/0; OpenAPI 36 → 41 paths. Hand-checked submit
  4/3/2/1 → 3.25/9.0 = 36.11% server-exact; backfill of the M7 row
  persisted.

## [2.7.0] — 2026-11-22 — Phase 2 M7: examination interface

### Added
- Exam engine (GAP-6, Alembic 0007 `student_responses` /
  `test_results`): start/session/answers/submit/result endpoints;
  server-clock timer (no local tick — proven by freezing the
  browser clock +1h); unknown snapshots excluded from scoring
  (`unknown_count`); duplicate submit idempotent; save after expiry
  → 409 `time_expired`, nothing stored.
- Frontend: `/dashboard/tests/[id]/take` (palette, mark-for-review,
  clear response, autosave + retry, localStorage draft, submit
  confirmation).

### Fixed
- Alembic `fileConfig` disabled app loggers (order-dependent test
  failure) — `disable_existing_loggers=False` in `alembic/env.py`.
- Duplicate snapshot in one answers batch → 500 UNIQUE violation —
  fixed in `save_answers` (last item wins).

### Verified
- pytest 575/0; OpenAPI 31 → 36 paths. Hand-checked submit
  5/2/2/1 → 4.5/9.0 = 50.0% server-exact.

## [2.6.0] — 2026-11-22 — Phase 2 M6: test builder

### Added
- Test builder (GAP-5, Alembic 0006): `MarkingConfig` /
  `TestTemplate` / `TestSession` / `TestQuestionSnapshot` models;
  marking-config + test endpoints; backend-only `score_answers`
  (Decimal, 2dp); snapshots copied at creation and byte-identical
  after a bank correction (sha256-proven).
- Frontend: `/dashboard/tests`, `/dashboard/tests/new` (builder:
  all/documents/subjects/explicit, counts 1–200, PPSC default,
  repetition/unknown toggles, availability preview),
  `/dashboard/tests/[id]` (snapshot preview).

### Fixed
- Delete → re-upload 500: 015's plain unique index didn't ignore
  soft-deleted rows — fixed with a PARTIAL index
  (`WHERE deleted_at IS NULL`) in the models + Alembic 0006 + new
  Supabase migration 017 (written, NOT applied live — owner step).

### Verified
- pytest 555/0; OpenAPI 27 → 31 paths. Scoring re-verified by
  hand: 10/2/3 at PPSC default = 9.5/15.0.

## [2.5.0] — 2026-11-22 — Phase 2 M5: extraction results + question bank

### Added
- Question-bank/results API (GAP-3 + GAP-4, Alembic 0005):
  `GET /api/v1/questions` (search/filter/paginate),
  `GET /api/v1/questions/{id}` (+ evidence trail + corrections),
  `GET /api/v1/documents/{id}/questions`,
  `GET .../corrections`, `GET /api/v1/subjects`,
  `POST/DELETE .../subjects`; 13 subjects seeded.
- Frontend: per-document results view, corrections UI with audit
  history, `/dashboard/questions` bank + question detail.
- Truth rules verified in code: `correct_index = -1` renders
  "Answer: unknown." with zero options highlighted; inferred
  answers carry a visible "Inferred" flag; Q&A pairs shown as
  Q&A, never forced into 4 options.

### Fixed
- Migration 0005 seed stored dashed UUIDs while `sa.Uuid` stores
  CHAR(32) hex on SQLite → subject assign 404'd — fixed to
  `uuid.uuid4().hex` + regression test.

### Verified
- pytest 536/0; OpenAPI 21 → 27 paths. Bank 108 total
  (81 answered / 27 unknown / 27 pending).

## [2.4.0] — 2026-11-22 — Phase 2 M4: dashboard + upload

### Added
- Dashboard engine (GAP-2): `GET /api/v1/documents` (paginated,
  owner-only), `GET /api/v1/documents/{id}`,
  `DELETE /api/v1/documents/{id}` (soft delete, cancels the job
  first), `GET /api/v1/dashboard/summary` (real counts).
- Bucket download wired: worker no longer skips register jobs
  (`download_bucket_bytes`, service-role only, classified errors).
- Frontend: real `/dashboard` (stat cards + recent docs),
  `/dashboard/upload` (drag-drop, live JobTracker),
  `/dashboard/documents` (filter, pagination, View/Retry/Cancel/
  Delete), `/dashboard/documents/[id]` (counts + stages + actions).

### Fixed
- Alembic 0003 omitted server defaults on
  `student_profiles.created_at/updated_at` → `POST /api/v1/me`
  500'd on migration-built DB — fixed by Alembic 0004 + regression
  test upgrading a scratch DB to head.

### Verified
- pytest 529/0; OpenAPI 17 → 21 paths. CA40 upload → done ≈3.0s,
  40/40.

## [2.3.0] — 2026-11-22 — Phase 2 M3: auth + profiles

### Added
- Real Supabase Auth (`@supabase/ssr` + `@supabase/supabase-js`):
  login/register/forgot-password/reset-password,
  `/auth/callback` (code exchange + engine profile from sign-up
  metadata), `proxy.ts` guards `/dashboard/*` → 307 login, header
  session state + logout, `/dashboard/profile` reads/writes
  `GET/POST/PATCH /api/v1/me` (StudentProfile + Alembic 0003).
- CORS added (`CORS_ALLOWED_ORIGINS`, default
  `http://localhost:3000`, credentials, never `*`).
- **ADR-011:** engine DB (SQLAlchemy) is the single store;
  PostgREST repos deleted; vocabulary unified on `done`
  (M7's `completed` would have violated the live 015 constraint).
  Engine now REQUIRES `DATABASE_URL` (503 otherwise).

### Verified
- pytest 510/0; OpenAPI 17 paths. **Live correction:** migration
  015 tables ARE live (only the `pdf-documents` bucket is missing
  — migration 016 written, NOT applied — owner step).
- **Blocker (owner step):** confirm → login → profile loop NOT
  live-proven — the confirmation email went to a mailbox nobody
  can read; test user `officerpath.m3.test@gmail.com` exists
  UNCONFIRMED in live Auth.

## [2.2.0] — 2026-11-22 — Phase 2 M2: frontend foundation + design system

### Added
- Next.js 16.4.6 + React 19.3.0 + TypeScript 5.9.3 (strict) +
  Tailwind 4.3.3, TanStack Query, React Hook Form + Zod.
- 11 public pages (Home, About, Features, How It Works, Exam
  Preparation, Pricing, Contact, Login, Register, Privacy, Terms)
  + forgot-password + robots.txt + sitemap.xml; 17 reusable UI
  components; Pakistan-map SVG watermark (hero/CTA only).
- **Vercel free CONFIRMED** as frontend host (Netlify fallback;
  Render rejected for now). No account, nothing deployed.
- CI: `officerpath-phase2-web` branch added + new `web` job.

### Verified
- `npm run build` PASS (15 static routes); lint 0; tsc exit 0;
  prod server 14/14 HTTP 200; mobile 360px 12/12 pages zero
  horizontal overflow.

## [2.1.0] — 2026-11-22 — Phase 2 M1: audit + architecture (docs only)

### Added
- Seven Phase 2 design docs (`docs/phase2/01–07`): repository
  findings, API integration map (17 paths, 12 GAPs), database
  extension plan, frontend architecture, security architecture,
  deployment plan (Vercel free recommended), milestone execution
  plan M2–M10.
- **Biggest finding:** dual job stores + `done` vs `completed`
  (register path writes Supabase `public.jobs` with `done`; M6/M7
  review + async-jobs path writes the engine DB with `completed`;
  `completed` would violate the live 015 check constraint).
  Resolution assigned to M3 (ADR-011).

## [1.0.0] — 2026-11-22 — Phase 1 M8: COMPLETE (local only)

### Added
- Acceptance tests through the public API (PPSC-66 via parse
  41q/41ans/27 pending; table photo via parse-image 0q/2 pending;
  Paper 60 4q/4ans/9 pending). `docs/PHASE_1_COMPLETION_REPORT.md`,
  README rewritten, `docs/deploy-render.md` rewritten,
  `docs/API.md`.
- `render.yaml`: `WORKER_ENABLED=true` +
  `WORKER_STAGE_TIMEOUT_SECONDS=1800` +
  `TESSERACT_TIMEOUT_SECONDS=300`; Dockerfile installs
  `tesseract-ocr-eng` + `osd`.

### Verified
- pytest 492/0; every M7 number reproduced exactly. Render-free
  fit CONFIRMED marginal (47 MB headroom).

## [0.8.0] — 2026-11-22 — Phase 1 M7: async jobs + security + observability

### Added
- `app/workers/` async job pipeline (atomic claim, per-stage
  timeout 600s naming the stage, cancel, retry, in-process worker
  + CLI runner, ADR-009); security (per-user 404s, size limits 422,
  rate limit 10 parse attempts/user/min → 429, secrets grep 0);
  observability (JSON logs, honest `/health`, `/metrics`);
  `POST /api/v1/documents/parse-image`.
- **Union merge kept as optional mode only (ADR-010):** PPSC-66
  40→53 distinct answered numbers, 41→62 questions, 61/62 correct,
  2.8–3.1× time.

### Verified
- pytest 489/0. Job proof (real HTTP): CA40 queued→done
  0.27–0.51s 40/40; corrupt PDF fails with reason → retry
  completes; cancel queued (2nd cancel 409) + cancel processing.

## [0.7.0] — 2026-11-22 — Phase 1 M6: matching + review APIs

### Added
- `app/pipeline/matching/` (resolved MCQs with evidence trails,
  ADR-007 promotion rule, key-region location, validation reason
  codes, calibration, reports JSON+md, store); review APIs (POST
  parse, GET review, POST corrections with audit trail, GET
  report); `app/pipeline/ocr/psm.py` (ADR-008: `select_psm`
  always PSM 3).
- PPSC-66 promotion 14→41 answered, 54→27 pending (27 promoted
  under ADR-007, never inferred). Key-region: whole-blob
  0.9756/0.80/0.8791 → region 1.0/0.84/0.913 (84 TP, 0 FP).

### Fixed
- Number-only verdict join gave end-to-end answers 0.5084 on
  TestPoint — fixed by occurrence pairing/positional alignment →
  1.0, regression tests added.

### Verified
- pytest 448/0.

## [0.6.0] — 2026-11-22 — Phase 1 M5: answers engine

### Added
- `app/pipeline/answers/` (9 files) + positional fix in
  `extract/tables.py`. Answer precedence (standing): manual >
  explicit key > inline > digital style > visual > inferred.
- Trailing key ideal 1.0s; live PPSC-66 OCR 0.9744/0.38/0.5468
  (38/1/62); TestPoint FP 248 → 28 (Q precision 0.8472 → 0.98).

### Verified
- pytest 377/0. PPSC-66 single-path recovery unchanged at 41/100
  (Q1–9 clipped at page edge → ceiling ≤91/100).

## [0.5.0] — 2026-11-21 — Phase 1 M4: MCQ extraction (Dart parser port) + measurement

### Added
- Extraction package (`app/pipeline/extract/`): `models` (ExtractedQuestion,
  QAPair, PendingQuestion, ParseResult — all JSON-serialisable),
  `numbers` (clean/OCR-misread/bare numbers, Urdu-digit normalisation
  for matching only — D1), `markers` (option regexes, E-rule, inline
  markers, split_option_line, 5→4 normalisation, noise filter),
  `signals` (answer-line/tick/bold/asterisk, precedence, confidence
  ladder, OCR-provenance downgrade to unverified 0.54 — D4),
  `keys` (paper-heading segments, strict same-paper join, key-match
  ladder, orphan adoption, token-stream key parsing), `blocks`
  (standard/one-liner/numberless-stem/interpolation/cross-page),
  `qa` (Q&A-without-options + flashcard path; NEVER fabricates 4
  options), `tables` (delimiter-aware Sr# path — D8 addition, not a
  Dart port; row-wise grid; column-wise), `scoring` (candidate
  confidence from number/option/marker/position/column signals —
  evidence only, never overrides a rule), `validate` (separate
  duplicate/conflict/fabrication checks), `service`
  (`extract_document`, `extract_from_ocr_blocks`,
  `extract_from_digital_pdf`; format order table → block → one-liner
  → q-only → flashcard; paper-identity gate: one call = one document).
- Per-line bold in the digital extractor (`app/pipeline/ocr/digital.py`,
  the only M4 change under `app/pipeline/ocr/`): `style["bold_lines"]`
  lists 0-based line indices whose spans are bold (PyMuPDF span flags
  & 16); the extract service appends U+E000 per bold line (Dart marker
  contract, consumed by the parser, never stored). OCR pages: bold
  unavailable, never approximated (D17).
- Benchmark harness (`scripts/benchmark_m4.py`): precision/recall/F1
  for question detection, option extraction, answer correctness per
  fixture + overall (digital vs scanned), PPSC-66 live end-to-end
  (Tesseract eng+urd PSM 3, 200 DPI, layout reading order, p7 key
  under the strict paper rule), clean Nastaliq CER re-measurement.
  Results in `docs/benchmarks/m4-benchmark-2026-11-21.json`.
- Deliberate changes from Dart (recorded): D8 Sr# table path (above);
  D10 Q-only distractor shuffle seeded `random.Random(20261121)`; D13
  paper-identity fields (`source_document_id`, `paper_number`,
  `paper_title`, `exam`, `year` — nullable, missing = unknown, never
  a wildcard match); D14 unknown Subject labels stay "unknown".
  Not in M4: D15 separately attached key (app flow; M5/M6). No Alembic
  migration — extraction results are not persisted in M4.

## [0.4.0] — 2026-11-21 — Phase 1 M3: OCR + layout, golden dataset v1, benchmark

### Added
- OCR abstraction (`app/pipeline/ocr/`): `OCREngine` protocol +
  `OCRRegistry` (lazy availability probing; an unavailable engine
  reports its reason and is skipped, never faked), per-page routing
  (`router.py`: digital first, OCR for scanned, mixed combines both
  with IoU+similarity dedup), disagreement comparison (agreement
  score + flagged regions, both outputs stored).
- Adapters: digital extractor (PyMuPDF dict-blocks; exact text +
  font/size/bold/italic/colour, confidence left None, never 1.0);
  Tesseract 5.3.4 (eng+urd, PSM 3, OSD rotation probe);
  PaddleOCR 3.7.0 (PP-OCRv5 Arabic-script models via ONNX Runtime —
  ships without paddlepaddle; line-level scores only); Gemini
  advisory provider (disabled by default; needs flag + server key +
  nonzero budget; no key provisioned, no calls made; Flutter prompt
  reused verbatim; crop-retry plan for the recitation filter).
- Layout analysis (`app/pipeline/layout/`): column detection by
  left-edge clustering + reading order (column-major, spanning
  blocks inserted by y), header/footer/page-number detection,
  region classification (question/option/key/heading/table/figure/
  noise), grid-table detection from OCR geometry, figure
  association with nearest block, cross-page continuation flags.
- OCR + layout pipeline stages (`app/pipeline/ocr/service.py`,
  `app/pipeline/layout/service.py`) with per-page failure isolation;
  OCR blocks persist to the `ocr_blocks` table and layout JSON to
  `document_pages.layout_applied` (Alembic 0002).
- Golden dataset v1 (`app/tests/fixtures/golden/dataset.json`, 19
  entries): exact ground truth for the M2 synthetic fixtures +
  Gemini reference text (labelled as reference, not ground truth)
  for PPSC-66 p1–p7 and both table photos; p1 hand-verified
  (1 word error in ~700). Paper 60 has no file in the source
  fixtures — recorded as `reference_kind: none`, not silently
  dropped.
- Benchmark harness (`scripts/benchmark_m3.py`,
  `scripts/benchmark_paddleocr_perpage.py`) + report
  (`docs/benchmarks/BENCHMARK_M3_2026-11-21.md`): digital CER
  0.0000; Tesseract PPSC-66 CER 0.07–0.54; PaddleOCR synthetic CER
  0.016–0.024 but PPSC-66 CER 0.31–0.43, 42–63 s/page, 1.8–3.7 GB
  peak RSS, OOM on full-res phone photos — PaddleOCR cannot run on
  Render free (ADR-005).
- ADR-005 (OCR engine evaluation) + M3 milestone report.

### Fixed
- M2 fixture generator drew the highlighted option twice (text over
  highlight rect), duplicating "(B) Lahore" in the text layer. The
  rect is now drawn before the text; all M2 fixtures regenerated
  (manifest mark bboxes byte-identical; full suite still passes).
- Column clustering first used x-interval overlap (single-linkage),
  which chained all 37 Tesseract blocks on PPSC-66 p1 into one
  column and gave CER 0.61 where the engine scores 0.06. Replaced
  with left-edge (x_min) gap clustering + distance-limited
  singleton merge: layout-order CER on p1 is now 0.0935.

### Changed
- `OCREngine.version` is a read-only property in the protocol
  (adapters were split between plain attributes and properties).
- `requirements.txt`: + pytesseract 0.3.13, pdfplumber 0.11.11,
  paddleocr 3.7.0, onnxruntime 1.32.0 (PaddleOCR optional/heavy).
  Dockerfile + CI install the Tesseract binary + `urd`/`ara` data.
  pip-audit: 0 known vulnerabilities.
- `.env.example`: M3 OCR + Gemini-advisory settings (all defaults
  shown; advisory stays off).

## [0.3.0] — 2026-11-21 — Phase 1 M2: PDF analysis, rendering, adaptive preprocessing

### Added
- PDF analysis with PyMuPDF 1.26.3 (`app/pipeline/pdf/analysis.py`):
  per-page text chars/spans, image count + coverage, fonts, rotation,
  embedded-image DPIs; encrypted files raise (never bypassed).
- Real per-page classification from PyMuPDF evidence
  (`app/pipeline/pdf/classifier.py`): digital / scanned / mixed /
  blank / unreadable / unknown. The M1 byte heuristic remains only as
  the fallback when no PDF bytes are available. Ingestion now passes
  the raw bytes, so uploads get exact classification.
- Bounded-DPI rendering (`app/pipeline/pdf/renderer.py`): one page at
  a time, colour PNG, DPI lowered automatically to fit
  `max_render_pixels` (default 12 MP); image files normalised via Pillow.
- Per-page quality metrics (`app/pipeline/pdf/quality.py`): blur
  (Laplacian variance), contrast, background-noise sigma (MAD estimate),
  skew (Hough lines, with an agreement guard), brightness, ink coverage.
  Bleed-through is recorded as not measured (no reference page).
- Adaptive preprocessing (`app/pipeline/preprocess/`): six versioned
  profiles (`m2-v1`) selected from measured quality; operations are
  deskew, denoise, CLAHE, sharpen, upscale, Otsu/adaptive threshold,
  border crop. Low-quality pages get a recorded second-profile
  comparison. Colour copies are kept byte-identical; mark preservation
  (tick/star/circle/underline) is checked on fixtures and gates the build.
- PDF pipeline stage (`app/pipeline/pdf/service.py`): analysis ->
  classification -> rendering -> preprocessing, page by page, with
  state-machine transitions, per-page failures recorded as
  `processing_errors` (the document continues), metrics + render paths
  persisted to `document_pages`. Deliberately NOT wired into the upload
  request path — the M7 worker calls it; `scripts/run_m2_pipeline.py`
  runs it from the CLI. `scripts/benchmark_m2.py` prints the measured table.
- ADR-004 (library evaluation + PyMuPDF AGPLv3 licence flag +
  pdfplumber deferred to M3 + Render memory measurements).
- Test fixtures: generated synthetic PDFs (clean/scanned/mixed/skewed/
  low-contrast/noisy/blank) with a mark manifest, plus PPSC-66 page
  copies with provenance (`app/tests/fixtures/`).

### Changed
- `requirements.txt`: PyMuPDF 1.26.3, opencv-python-headless 4.11.0.86,
  Pillow 13.0.0 (upgraded from 11.3.0 — pip-audit found 59
  vulnerabilities in 11.3.0, fixed in 13.0.0), NumPy 2.3.2.
- `StageRecorder` protocol extended with `update_page` + `record_error`
  (both recorders implement them).
- `low_quality` profile: upscaling removed after calibration (peak RSS
  ~457 MB -> ~285–325 MB; Render free is 512 MB). The upscale operation
  still exists for per-page use, pending M3 OCR evidence.

### Verified
- 113 tests pass (69 M1 + 44 new), ruff + mypy clean, pip-audit 0
  vulnerabilities. M2 gate: quality metrics per page on all fixtures +
  PPSC-66 (see `docs/milestones/MILESTONE_2_REPORT.md`); marks
  preserved (retention 0.997–1.076) on all six profiles.

## [0.2.0] — 2026-11-21 — Phase 1 M1: structure, schema, ingestion, storage

### Added
- SQLAlchemy 2.x models for the full prompt §14 schema (17 tables:
  `documents`/`jobs` mirrored from migration 015 + 15 engine-owned
  tables) and Alembic revision `0001_m1_engine_tables` (up/down tested
  locally on SQLite; Postgres-only parts verified by Dashboard queries
  only — see `docs/migration-015-apply.md`).
- Pipeline plugin interfaces (`OCREngine`, `LayoutAnalyzer`,
  `QuestionDetector`, `OptionDetector`, `AnswerSourceDetector`,
  `Matcher`, `ConfidenceScorer`, `AIAssistProvider`) + `StageRegistry`
  + pipeline state machine with an allowed-transition table.
- Ingestion stage: extension + magic-byte validation, configurable
  size/page/dimension/pixel limits, PDF structure checks (encrypted
  files reported, never bypassed; truncation detected), image
  dimension/DPI/rotation parsing (stdlib only), decompression guard
  (absolute pixel cap; high ratio is a warning, not a rejection),
  SHA-256 dedup (per user), per-page classification (byte-heuristic;
  unknown is recorded, never guessed), batch upload with per-file
  results.
- Storage abstraction (`StorageBackend` + write-once local-disk
  implementation, safe generated names, traversal protection).
- API: `POST /api/v1/documents/upload` (single) and
  `POST /api/v1/documents/upload/batch` (up to 20 files). File types
  `webp`/`tiff`/`tif` accepted end to end.
- ADR-003 (persistence: SQLAlchemy + Alembic; supabase-py kept for
  Auth + documents/jobs), Render deploy docs (`docs/deploy-render.md`,
  `render.yaml`), migration 015 apply guide
  (`docs/migration-015-apply.md`) + down-migration.
- CI gates: ruff (lint + format), mypy (M1 packages), pip-audit,
  detect-secrets secret scan (baseline `.secrets.baseline`), Alembic
  up/down on SQLite, Docker build. `pyproject.toml` tool config.

### Changed
- Migration 015 (still unapplied): `file_type` gains `webp`/`tiff`/
  `tif`; `documents` gains `content_hash` + unique index
  `(user_id, content_hash)`; bucket allows `image/webp` + `image/tiff`.
- Deploy docs rewritten for Render free tier (ADR-001); Cloud Run
  references removed (Cloud Run parked, GCP billing paused).
- Dependency upgrades (pip-audit-driven, all 14 findings fixed):
  FastAPI 0.115.6 → 0.165.0, pytest 8.3.4 → 9.0.3,
  python-multipart 0.0.20 → 0.0.34. Full suite green after upgrade.
- `admin/config.js` finding from the M0 audit: RESOLVED — verified
  live via the public GitHub API that `config.js` is NOT tracked in
  `officerpath-ai` (only `config.example.js` is), and the local
  `admin/.gitignore` does list `config.js`.

### Not done (blocked, not forgotten)
- GitHub repo `officerpath-pdf-engine` still empty on GitHub (size 0,
  verified live); local code is committed on branch
  `officerpath-phase1-engine` — push is a separate step (see M1 report).
- Migration 015 NOT applied live (needs the owner's separate go-ahead).
- No Render deploy (needs repo link + 015 + owner's browser steps).
- No OCR / parsing (M2–M5). Per-page classification is byte-heuristic
  in M1; exact classification is M2 (PyMuPDF). Skew/blur/noise/
  contrast are recorded as not-measured in M1 (need OpenCV, M2).

## [0.1.0] — 2026-11-20 — Phase 1A: contract + skeleton

### Added
- FastAPI service skeleton (Python 3.12, FastAPI, Pydantic v2, Uvicorn,
  Supabase Python client, structured JSON logging, pytest).
- `GET /health` — app health; checks Supabase reachability when
  configured; 200 healthy / 503 when a configured dependency is
  unreachable; no secrets in the response.
- `GET /version` — app version + git commit (when available) +
  environment name.
- `POST /api/v1/documents/register` — Supabase-JWT authenticated;
  validates document metadata (title, storage path, file type, file
  size ≤ 100 MB, page count ≤ 100); creates a `documents` row + a
  durable `jobs` row (id, user_id, document_id, status, created /
  started / completed times, retry count, error details). Ownership
  enforced (own user id + own storage folder). Idempotent via
  client-supplied idempotency key and via same storage path + user.
- `GET /api/v1/jobs/{job_id}` — job status, owner-only (404 for other
  users, never leaks existence).
- `POST /api/v1/jobs/{job_id}/retry` — owner-only; only from
  `failed`/`cancelled`; increments retry count; rate-limited.
- API versioning under `/api/v1`; Pydantic request validation;
  structured error bodies (no internal details leaked); structured
  JSON logging with secret redaction; in-memory per-user rate limiting
  (documented as Phase 1 only, not shared across instances).
- Supabase integration: anon client for user-scoped calls, service-role
  client server-side only from env vars (never in code, never in
  `.env.example` — placeholders only).
- Migration `supabase/migrations/015_documents_jobs.sql` (NOT applied
  live): new `documents` + `jobs` tables with RLS, new private
  `pdf-documents` bucket + policies. Additive-only; does not modify any
  existing table, bucket, or the money path.
- Worker skeleton (`app/workers/processor.py`): atomic job-claim pattern
  documented; processing itself is Phase 1B, not implemented.
- Dockerfile (python:3.12-slim, multi-stage, non-root user,
  HEALTHCHECK on `/health`, Uvicorn SIGTERM graceful shutdown,
  env vars only, no secrets baked in).
- CI workflow (`.github/workflows/ci.yml`): pytest + Docker image
  build on push/PR. No deploy, no push, no live access.
- `TEST_REPORT.md` with the acceptance-test results (honest: live
  tests blocked, reasons given).

### Not done (blocked, not forgotten)
- GitHub repo does not exist yet (needs the user).
- No deploy to Cloud Run (needs a billing account + payment method —
  user decision pending; no cloud resource created, billing untouched).
- Migration 015 not applied to live Supabase (needs owner's go-ahead).
- No OCR / parsing (Phase 1B).
- No Flutter app changes; no live Supabase changes.
