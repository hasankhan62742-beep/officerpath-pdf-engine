# OfficerPath PDF Engine — API Reference (Phase 1, M8)

Generated from the actual routes in `app/main.py`,
`app/api/health.py`, `app/api/metrics.py`,
`app/api/v1/routes.py`, `app/api/v1/review.py`,
`app/api/v1/async_jobs.py` (2026-11-22). If a route is not
listed here, it does not exist.

Base URL (local): `http://127.0.0.1:8000`. Render: the service
URL from the Render Dashboard (see `docs/deploy-render.md`).

## Conventions

- **Auth:** every `/api/v1/*` endpoint requires a Supabase JWT
  (`Authorization: Bearer <token>`). The token is verified by
  Supabase Auth (`auth.get_user`); tokens are never decoded
  locally. Without a token: **401**. A token for another user
  accessing someone else's job/document: **404** (never leaks
  existence). `/health`, `/version`, `/metrics` need no auth.
- **Errors:** all errors are `{ "error": { "code": "...",
  "message": "..." } }` with an HTTP status. Common codes:
  `file_too_large` (422), `invalid_file` (422),
  `validation_error` (422), `rate_limited` (429),
  `auth_unavailable` (503, Supabase not configured),
  `database_unavailable` (503, no DATABASE_URL),
  `not_found` (404). A bad request body is always a 4xx, never
  a 500.
- **Oversize:** one shape everywhere — a request body or file
  larger than `max_file_size_bytes` (default 100 MB) is
  **422 `file_too_large`** (M1 contract, fixed in M7).
- **Rate limit:** parse/register attempts are limited per user
  (default 10/minute; retry 5/minute). The 11th attempt is
  **429 `rate_limited`**. In-memory per process; resets on
  restart (see `app/security/rate_limit.py`).
- Every response carries an `X-Request-Id` header.

## Operational endpoints

### `GET /health`
No auth. Real dependency state, never a hardcoded "ok".

Response `200`:
```json
{"status": "degraded", "service": "officerpath-pdf-engine",
 "version": "0.1.0", "environment": "development",
 "checks": {"config": "ok", "supabase": "ok",
  "database": "not_configured", "ocr_tesseract": "available",
  "ocr_paddleocr": "available", "disk": "ok"}}
```
`status` is `ok` only when every check is ok; `degraded`
otherwise (e.g. `database: not_configured` until migration 015
is applied and `DATABASE_URL` is set — that is the honest
behaviour, not a failure). Individual checks: `config`,
`supabase`, `database` (`ok` / `unreachable` /
`not_configured`), `ocr_tesseract` (`available` /
`unavailable`), `ocr_paddleocr` (`available` / `disabled` /
`unavailable` / `disabled_on_render_free`), `disk` (`ok` /
`low` below 100 MB free).

### `GET /version`
No auth. `{"version": "0.1.0", "environment": "development",
"git_commit": "<short sha or null>"}`.

### `GET /metrics`
No auth. Prometheus-style plain text. Aggregates only (no
per-user data). Counters appear on first event. Families:
`documents_parsed_total{engine}`, `ocr_calls_total{engine}`,
`officerpath_stage_seconds_total{stage}`,
`officerpath_jobs_current{status}` (live DB gauge — absent
when no database is configured, never faked),
`jobs_total{status}`, `http_requests_total{status}`,
`errors_total{code}`.

## Documents — register / upload (M1; ADR-011, M3)

M3 note: these endpoints now read/write the ENGINE DB (the same
Postgres Supabase hosts, via `DATABASE_URL`) — the PostgREST
repositories are deleted (ADR-011). `GET /api/v1/jobs/{id}` and
`GET /api/v1/async-jobs/{id}` read the same row. The terminal job
status is `done` (the live 015 check constraint rejects
`completed`). `DATABASE_URL` is required; without it these
endpoints answer 503 `database_unavailable`.

### `POST /api/v1/documents/register` → 201
Auth. Body (JSON): document metadata — `title`, `storage_path`
(Supabase `pdf-documents` path), `file_size_bytes`,
`page_count`, optional `idempotency_key`. Creates a document
record + a durable processing job. Idempotent: the same
idempotency key, or the same storage path + user, returns the
original job (`idempotent_replay: true`). Ownership enforced.
Rate-limited (10/minute). The job is marked register-source and
is NOT claimed by the worker until M4 wires bucket download
(its bytes live in the bucket, not on local disk).

### `POST /api/v1/documents/upload` → 200
Auth. Multipart `file`. Validates the file bytes (magic bytes,
encrypted-PDF rejection, size limits), stores the original
immutably (local disk in dev; Supabase bucket when configured),
dedups by SHA-256 (same user + same file → original document +
job, `idempotent_replay: true`), returns per-page
classification. Rejected files: **422** with a
machine-readable code (`magic_bytes_mismatch`,
`pdf_encrypted`, `file_too_large`).

### `POST /api/v1/documents/upload/batch` → 200
Auth. Up to 20 files. Per-file results (stored / replay /
rejected with reasons). One bad file never blocks the batch.

### `GET /api/v1/jobs/{job_id}` → 200
Auth, owner-only (other user: **404**). Job status +
`result_summary`.

### `POST /api/v1/jobs/{job_id}/retry` → 200
Auth, owner-only. Only from `failed`/`cancelled`; increments
the retry count. Rate-limited (5/minute).

## Review — synchronous parse (M6/M7)

### `POST /api/v1/documents/parse` → 200
Auth. Multipart `file` (PDF), optional query `multi_pass`
(`true` = union-merge mode, M7/ADR-010; default `false`).
Parses one PDF end to end in-process (digital text first,
else per-page Tesseract OCR at 200 DPI, PSM 3) and returns the
resolved MCQs + report. **Synchronous and slow on scans** —
a 7-page PPSC-66 parse takes ~130 s on the dev VM (~20 min
estimated at Render free's 0.1 CPU); long work belongs in the
async job model below, not in a single HTTP call.

Response (`ParseResponse`):
```json
{"document_id": "...", "job_id": "...", "persisted": true,
 "filename": "x.pdf", "is_digital": false, "page_count": 7,
 "matched": {"questions": [...], "qa_pairs": [...],
  "pending": [...], "validation_issues": [...],
  "promotion": {...}, "counts": {"questions": 41,
  "answered": 41, "pending": 27, ...}, "notes": [...],
  "answered": 41, "unknown": 0},
 "report": {"counts": {...}, "by_status": {...},
  "by_answer_source": {...}, "confidence_distribution": {...},
  "pending": [...], "unknown": [...],
  "validation_issues": [...], "evidence_trail": [...]},
 "debug": {"is_digital": false, "page_count": 7,
  "psm_by_page": {"1": 3, ...}}}
```
Each resolved question: `number`, `text`, `options` (4 for
MCQ, `[]` for `qa_pair`), `correct_index` (−1 = UNKNOWN,
never guessed), `correct_letter`, `answer_source` (winning
detector: `manual` / `trailing-key` / `inline` / `style` /
`visual` / `inferred` / `""`), `confidence`,
`raw_confidence`, `verified`, `inferred`, `status`
(`answered` / `unknown` / `conflict-resolved`), `kind`
(`mcq` / `qa_pair`), `answer_text` (qa_pair only), `page`,
`paper`. When `DATABASE_URL` is configured the Document + Job
rows and the matched result are persisted (`persisted:
true`); without a database the parse still returns with
`persisted: false` — a bookkeeping failure never fails a good
parse. Non-PDF: **422 `invalid_file`**.

### `POST /api/v1/documents/parse-image` → 200
Auth. Multipart `file` (JPEG/PNG — a photo, not a PDF).
Same pipeline and same `ParseResponse` shape as the PDF path,
for one scanned page. This is the server side of the Flutter
`importImage` path (toggle ON). Non-image bytes: **422
`invalid_file`**; undecodable image: **422**.

### `GET /api/v1/jobs/{job_id}/review` → 200
Auth, owner-only. The pending/unknown items for a job (the
review queue). **503** `database_unavailable` when no
database is configured; **404** for an unknown job or another
user's job.

Response (`ReviewListResponse`): `{ "job_id": "...",
"items": [{ "question_id", "document_id", "number",
"text", "options", "status": "pending" | "unknown",
"page" }], "count": N }`.

### `POST /api/v1/documents/{document_id}/questions/{question_id}/corrections` → 200
Auth, owner-only. Manual correction — the top of the
answer-precedence chain (manual > key > inline > style >
visual > inferred). Body: `{ "field":
"question_text" | "option_text:<0-3>" | "answer",
"new_value": "...", "reason": "..." }`. The correction never
edits the original extraction (`original_*` untouched); it
writes the normalized field, records old/new in
`manual_corrections`, appends a `review_history` row, and
re-runs validation. Response (`CorrectionResponse`):
`question_id`, `number`, `field`, `old_value`, `new_value`,
`validation_status`, `validation_issues`. Bad field:
**422**; other user: **404**.

### `GET /api/v1/documents/{document_id}/report` → 200
Auth, owner-only. The stored document report
(`DocumentReportResponse`): `questions_extracted`,
`questions_missing_options`, `uncertain_answers`,
`conflicting_answers`, `unmatched_key_entries`,
`duplicates_found`, `requires_review`, `review_reasons`,
`summary`, `rule_set_version`, `created_at`.

## Async jobs — background processing (M7)

### `POST /api/v1/async-jobs/parse` → 202
Auth. Multipart `file` (PDF). Submits the document to the
background worker and returns immediately. Response
(`AsyncJobCreatedResponse`): `{ "job_id", "document_id",
"status": "queued", "filename", "page_count" }`. The worker
(in-process when `WORKER_ENABLED=true`, or `python -m
app.workers.runner` as its own process on the VPS) claims the
job atomically and runs the pipeline with per-stage timing
and a per-stage timeout (default 600 s — the stage is named
in the failure). Poll `GET` below for the result.

### `GET /api/v1/async-jobs/{job_id}` → 200
Auth, owner-only (**404** for another user). Response
(`AsyncJobStatusResponse`): `job_id`, `document_id`,
`status` (`queued` / `processing` / `done` / `failed` /
`cancelled`), `retry_count`, `error`, `result_summary`
(`{ "questions", "answered", ... }` when done),
`created_at`, `started_at`, `completed_at`, `stages` (each:
`stage`, `status`, `detail` with per-stage seconds,
`created_at`).

### `POST /api/v1/async-jobs/{job_id}/cancel` → 200
Auth, owner-only. Cancels a queued or processing job; the
result is `cancelled`, never `failed`. A second cancel is
**409**. A processing job stops at the first stage boundary.

### `POST /api/v1/async-jobs/{job_id}/retry` → 200
Auth, owner-only. Re-queues a `failed` or `cancelled` job
(`retry_count` +1). Retrying a job in any other state is
**409**.

## Job states (summary)

| State | Meaning |
|---|---|
| `queued` | Submitted, waiting for the worker. |
| `processing` | Claimed by the worker, a stage is running. |
| `done` | All stages done; `result_summary` has the counts. |
| `failed` | A stage failed (reason in `error`, stage named); retryable. |
| `cancelled` | Cancel requested (queued or at a stage boundary); retryable. |

## What Phase 1 does NOT expose

No admin endpoints, no quota/premium endpoints, no user
management, no Gemini endpoints (the advisory adapter is
disabled by default and has no HTTP surface), no upload to
any third party. The engine never writes
`profiles.plan` / `premium_until` / `is_admin`, never touches
`activation_codes` or `payments`, and never grants Premium.
