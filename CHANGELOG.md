# CHANGELOG — officerpath-pdf-engine

All notable changes to this project. Dates in PKT (Asia/Karachi).

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
