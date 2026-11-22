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
Rate-limited (10/minute). The job is marked register-source; since
M4 the worker claims it and downloads the bytes once from the
`pdf-documents` bucket (service-role client only, via
`download_bucket_bytes`) into the local write-once cache before
parsing. A missing bucket/object fails the job with a named
storage error (`storage_bucket_missing` /
`storage_object_missing`); without a service-role client the
job fails with 503 `storage_unavailable`. Live-bucket status is
UNVERIFIED-live (migration 016 not applied — owner step).

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

## Documents — listing / detail / delete (Phase 2, M4)

All owner-only (other user: **404**), all read the engine DB
(ADR-011 single store). `questions`/`answered` come from the
job's `result_summary` when the job is `done`; `null` while the
job has not produced them.

### `GET /api/v1/documents` → 200
Auth. Query: `limit` (1–100, default 20), `offset` (≥ 0,
default 0), optional `status` filter (one of
`queued`, `uploading`, `processing`, `done`, `failed`,
`cancelled`). Returns `{documents: [{id, title, file_type,
file_size_bytes, page_count, created_at, job, questions,
answered}], total, limit, offset}`. Soft-deleted documents are
excluded; re-upload after delete creates a fresh document.
(M6 fix: the (user_id, content_hash) unique index is PARTIAL —
`WHERE deleted_at IS NULL` — in the model, Alembic 0006, and
Supabase migration 017. Before M6 the plain unique index made
delete → re-upload 500 on Alembic-built and live databases,
because the soft-deleted row still held the unique slot.)

### `GET /api/v1/documents/{document_id}` → 200
Auth. Returns `{document, job, stages}` — the document, its
latest job (with `result_summary`), and the job's stage
history. Other user / unknown id: **404**.

### `DELETE /api/v1/documents/{document_id}` → 200
Auth. Soft delete (sets `deleted_at`): the document disappears
from list/summary/detail (**404** afterwards). A queued or
processing job is cancelled first (`job_cancelled: true` in the
response). Local bytes are deleted best-effort; bucket bytes
are never touched. Returns `{document_id, deleted: true,
job_cancelled}`.

## Question bank + extraction results (Phase 2, M5)

All owner-only (other user: **404**), all read the engine DB
(ADR-011 single store). Questions are the stored
`extracted_questions` rows written by the Phase 1 store —
this API never edits them; corrections go through the M6
endpoint below and only the audit trail is listed here.

**Truth rules:** `correct_index` is `-1` when the engine does
not know the answer (rendered UNKNOWN, never as a correct
option); `confidence` is `null` when there is no answer row;
`inferred` answers carry an explicit flag and are never shown
as verified; `answer_status` is one of `verified` /
`detected` / `unknown` / `needs_review` / `conflicting`.
Q&A pairs are NOT stored as question rows (the Phase 1 store
keeps their count only) — `qa_pairs` in the document-questions
response is that count, never fake rows.

### `GET /api/v1/documents/{document_id}/questions` → 200
Auth. One document's extraction results, in printed-number
order (numeric when parseable — never created_at order, which
ties on SQLite). Query: `limit` (1–100, default 50), `offset`.
Returns `{document_id, questions: [QuestionItem], total, limit,
offset, counts: {questions, answered, unknown, pending,
inferred, corrected}, qa_pairs}`. Each item carries its
options, `correct_index`, `answer_source`, `confidence`,
`verified` / `inferred` / `corrected` flags, `status`,
`answer_status`, `page`, and its subject assignments.

### `GET /api/v1/questions` → 200
Auth. The question bank: all of the caller's questions across
documents, newest first. Query: `q` (search question text),
`document_id`, `status` (`answered` / `unknown` / `pending` /
`inferred` / `corrected` / `conflicting`), `subject_id`,
`confidence_min` / `confidence_max` (0–1; only questions with
an answer row can match a band), `limit` (1–100, default 20),
`offset`. Returns `{questions: [QuestionItem], total, limit,
offset}`. Bad `status`: **422**.

### `GET /api/v1/questions/{question_id}` → 200
Auth. One question with its full evidence trail and correction
history. Returns `QuestionItem` + `evidence: [{detector,
source_type, value_normalized, page_number,
detector_confidence, artifact_ref}]` (from `answer_evidence`
rows; empty for unknown answers — no detector claimed them) +
`corrections: [{id, field_name, old_value, new_value, reason,
created_at}]` (newest first).

### `GET /api/v1/documents/{document_id}/questions/{question_id}/corrections` → 200
Auth. The audit trail for one question: every manual
correction with old/new values, newest first. Returns
`{question_id, corrections, total}`.

### `GET /api/v1/subjects` → 200
Auth. All active subjects with their topics (global reference
data — no user filter). Returns `{subjects: [{id, name, slug,
description, topics: [{id, name, slug}]}], total}`. The 13
subjects from the Phase 2 prompt §12 are seeded by Alembic
0005; no topics are seeded yet. Classification is optional and
manual only — the engine never auto-assigns a subject.

### `POST /api/v1/questions/{question_id}/subjects` → 200
Auth. Manually assign a subject (optionally a topic) to one of
the caller's questions. Body: `{subject_id, topic_id?}`.
Idempotent: re-assigning the same subject returns the existing
row with `already_assigned: true`. Unknown subject/topic or
another user's question: **404**.

### `DELETE /api/v1/questions/{question_id}/subjects/{subject_id}` → 200
Auth. Remove a subject assignment. Returns `{question_id,
subject_id, removed: true}`. Missing assignment: **404**.

## Test builder (Phase 2, M6)

All owner-only (other user: **404**), all read/write the engine DB
(ADR-011 single store). A test freezes its own copy of every
question — **snapshots, not foreign keys**: creating a test copies
the question text, options, correct answer and evidence state
into `test_question_snapshots`, plus the marking config id, so a
later bank correction never changes the test (proven by the M6
unit test and the M6 E2E snapshot-immutability check). Marking
is backend-only: `score_answers` (Decimal, 2dp) is a pure service
function — the frontend never computes a score. Taking a test is
M7; these endpoints only build and manage tests.

**Selection rules:** no duplicates in a test unless
`allow_repetition: true` (recorded on the test; explicit picks
without the flag: **422** `duplicate_questions`). Unknown answers
(`correct_index = -1`) are excluded from filter-based selection
by default and reported as `excluded_unknown`; explicit picks of
an unknown question without `include_unknown: true` are
**422**. Q&A pairs (no options) can never be scored and are
always excluded, reported as `excluded_no_options`. Asking for
more questions than the pool holds is **422**
`insufficient_questions` (never a silently short test).
Question counts are 1–200; the UI offers 25/50/100/150/200 as
quick picks. Marking ranges: correct 0.25–10, incorrect −5–0,
unattempted −1–0; anything outside is **422**.

### `GET /api/v1/marking-configs` → 200
Auth. All marking configs, the PPSC default
(`PPSC default`, +1 / −0.25 / 0, `is_default: true`, seeded by
Alembic 0006) first. Returns `{marking_configs, total}`.

### `POST /api/v1/marking-configs` → 201
Auth. Create a custom marking config. Body: `{name,
correct_marks, incorrect_marks, unattempted_marks}` (ranges
above). Returns the created config.

### `GET /api/v1/tests/availability` → 200
Auth. How many questions a source can supply, before building.
Query: `source_type` (`all` / `documents` / `subjects` /
`topics` / `mixed`), `document_ids` / `subject_ids` /
`topic_ids`, `include_unknown` (default false). Returns
`{available, excluded_unknown, excluded_no_options, sample:
[{question_id, document_id, document_title, number, text,
correct_index}]}` (5-question sample). The three counts always
partition the pool.

### `POST /api/v1/tests` → 201
Auth. Create a test. Body: `{name, description?,
question_count, source_type, source_ids?, marking_config_id?
| marking?, allow_repetition?, include_unknown?,
time_limit_seconds?}`. `source_type` `all` ignores
`source_ids`; `documents` / `subjects` / `topics` take id
lists; `mixed` takes `{document_ids, subject_ids}`;
`explicit` takes the question ids in order. Selection is a
random sample with a saved `selection_seed` (reproducible);
explicit mode keeps the given order. Returns the full test
with `snapshots: [{snapshot_id, question_id, position,
question_text, options: [{label, text}], correct_index,
answer_source, source_document_id, source_page}]` (a
`correct_index` of −1 means explicitly included as unknown),
`marking_config`, `excluded_unknown`, `excluded_no_options`.
Unknown source / bad count / duplicate or unknown picks
without their flags: **422**. `server_started_at` is null
until M7 starts the test.

### `GET /api/v1/tests` → 200
Auth. The caller's tests, newest first. Query: `limit`
(1–100, default 20), `offset`. Returns `{tests:
[TestResponse], total, limit, offset}`.

### `GET /api/v1/tests/{test_id}` → 200
Auth. One test with its snapshots + marking config + exclusion
counts (same shape as the create response). Other user: **404**.

### `PATCH /api/v1/tests/{test_id}` → 200
Auth. Rename / re-describe a test (`{name?, description?}`).
Only while `status == "created"` — after an attempt exists
(M7) the test is frozen: **409** `test_already_started`.

### `DELETE /api/v1/tests/{test_id}` → 200
Auth. Delete a test, only while `status == "created"` (no
attempts yet — the M6 rule; attempts arrive in M7). After an
attempt exists: **409** `test_already_started`. Missing test:
**404** on re-read.

## Dashboard — summary (Phase 2, M4)

### `GET /api/v1/dashboard/summary` → 200
Auth. Real numbers only, from the signed-in user's
non-deleted documents: `{documents_total,
jobs_by_status: {queued, uploading, processing, done, failed,
cancelled} (all six keys, zeros included), recent_documents:
[DashboardDocumentItem, newest 5]}`. No test-result numbers
yet — no test rows exist until M7/M8, so the dashboard does
not invent that section.

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
