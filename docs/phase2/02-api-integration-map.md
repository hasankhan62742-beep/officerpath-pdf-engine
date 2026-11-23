# Phase 2 M1 — API Integration Map

**Date:** 2026-11-22
**Source of truth:** the live route table from `app.openapi()`
(verified 2026-11-22) and `docs/API.md` (M8, generated from the same
routes). Where this doc and `docs/API.md` disagree, `docs/API.md` +
the code win.

## 0. Conventions (apply to every endpoint below)

- **Base URL:** local `http://127.0.0.1:8000`; production is the Render
  service URL (not deployed yet — see `06-deployment-plan.md`).
- **Auth:** every `/api/v1/*` endpoint requires a Supabase JWT
  (`Authorization: Bearer <token>`). Verified by Supabase Auth
  (`auth.get_user`) in `app/security/dependencies.py:get_current_user`;
  tokens are never decoded locally. No token → **401**. Another user's
  resource → **404** (never leaks existence). `/health`, `/version`,
  `/metrics` need no auth.
- **Errors:** `{ "error": { "code": "...", "message": "..." } }`.
  Common codes: `file_too_large` (422), `invalid_file` (422),
  `validation_error` (422), `rate_limited` (429), `auth_unavailable`
  (503), `database_unavailable` (503), `not_found` (404). Bad input is
  always 4xx, never 500.
- **Rate limits:** register/parse 10 attempts/user/minute; retry
  5/minute; 11th attempt → 429 (`app/security/rate_limit.py`,
  `app/config.py:36-40`). In-memory, per process; resets on restart.
- **Every response** carries an `X-Request-Id` header
  (`app/main.py:83-87`).
- **Job-status vocabulary — RESOLVED in M3 (ADR-011):** the split
  is gone. The engine DB is the single access path for documents +
  jobs and the terminal status is `done` everywhere (the live 015
  check constraint rejects `completed`). `GET /api/v1/jobs/{id}`
  and `GET /api/v1/async-jobs/{id}` read the same row. See
  `docs/adr/ADR-011-dual-job-store-resolution.md`.

## 1. Operational endpoints (no auth)

| Method + path | Response | Consumed by (Phase 2) |
|---|---|---|
| `GET /health` | `200 {"status": "ok"\|"degraded", "checks": {config, supabase, database, ocr_tesseract, ocr_paddleocr, disk}}` — real state, never hardcoded. Today: `degraded`, `database: not_configured` (migration 015 unapplied). | Status page / deploy verification (M10); frontend shows "engine unavailable" when not `ok`. |
| `GET /version` | `200 {"version": "0.1.0", "environment": "...", "git_commit": "<sha\|null>"}` | Footer/debug info; deploy verification. |
| `GET /metrics` | `200 text/plain` Prometheus-style. Families: `documents_parsed_total{engine}`, `ocr_calls_total{engine}`, `officerpath_stage_seconds_total{stage}`, `officerpath_jobs_current{status}` (absent without a DB — never faked), `jobs_total{status}`, `http_requests_total{status}`, `errors_total{code}`. | Admin monitoring (M9); never exposed to students. |

## 2. Documents — register / upload (M1, Supabase PostgREST path)

| Method + path | Request | Response | Consumed by |
|---|---|---|---|
| `POST /api/v1/documents/register` → 201 (200 on idempotent replay) | JSON: `title`, `storage_path` (Supabase `pdf-documents` path), `file_size_bytes`, `page_count`, optional `idempotency_key` (`app/schemas/documents.py:34-51`) | `RegisterResponse`: `document` + `job` + `idempotent_replay: bool` | Upload flow alternative: client uploads the file to the `pdf-documents` bucket directly (signed URL via `app/integrations/supabase_storage.py` — defined but unused; M4 must wire or replace it), then registers metadata. Idempotent on same key or same storage path + user. **M3 (ADR-011): writes the engine DB now; the job is register-source and is not claimed by the worker until M4 wires bucket download.** |
| `POST /api/v1/documents/upload` → 200 | Multipart `file` | `UploadResponse`: document + job + per-page classification; rejected files → 422 with machine code (`magic_bytes_mismatch`, `pdf_encrypted`, `file_too_large`) | **Primary upload path (M4).** Validates magic bytes, rejects encrypted PDFs, SHA-256 dedup per user (`idempotent_replay: true` on repeat). Limits: 100 MB/file, 100 pages/job, 5 MB/page image, images ≤ 25 MP. |
| `POST /api/v1/documents/upload/batch` → 200 | Multipart, up to 20 files | `BatchUploadResponse`: per-file stored / replay / rejected with reasons; one bad file never blocks the batch | Multi-upload (M4). |
| `GET /api/v1/jobs/{job_id}` → 200 | — | `JobResponse`: job status + `result_summary` (vocabulary: `queued/uploading/processing/done/failed/cancelled`) | Job status polling for the register/upload path. **M3 (ADR-011): reads the engine DB — the same row `GET /api/v1/async-jobs/{id}` reads.** |
| `POST /api/v1/jobs/{job_id}/retry` → 200 | — | Re-queues a `failed`/`cancelled` job (`retry_count` +1); other states → 409. Rate-limited 5/min. | Retry from the document list (M4/M5). |

## 3. Review — synchronous parse (M6/M7, engine-DB path)

| Method + path | Request | Response | Consumed by |
|---|---|---|---|
| `POST /api/v1/documents/parse` → 200 | Multipart `file` (PDF); optional query `multi_pass=true` (union-merge mode, ADR-010; default `false`) | `ParseResponse` (`app/schemas/review.py:58`): `document_id`, `job_id`, `persisted` (false without DATABASE_URL — a bookkeeping failure never fails a good parse), `filename`, `is_digital`, `page_count`, `matched` (questions, qa_pairs, pending, validation_issues, promotion, counts, notes, answered, unknown), `report` (counts, by_status, by_answer_source, confidence_distribution, pending, unknown, validation_issues, evidence_trail), `debug` (psm_by_page). Non-PDF → 422 `invalid_file`. | **Sync parse for small digital PDFs only (M4).** A 7-page scan takes ~130 s on the dev VM (~20 min at Render free 0.1 CPU) — the frontend must use async jobs for scans, never block the UI on this call. |
| `POST /api/v1/documents/parse-image` → 200 | Multipart `file` (JPEG/PNG photo) | Same `ParseResponse` shape, one scanned page. Non-image → 422; undecodable → 422. | Photo upload path (M4/M5). Same latency warning as parse. |
| `GET /api/v1/jobs/{job_id}/review` → 200 | — | `ReviewListResponse`: `{job_id, items: [{question_id, document_id, number, text, options, status: pending\|unknown, page}], count}`. 503 `database_unavailable` without a DB; 404 unknown/other-user job. | Review queue (M5). **Reads the engine DB** — only jobs parsed through the engine path appear here. |
| `POST /api/v1/documents/{document_id}/questions/{question_id}/corrections` → 200 | JSON: `field` (`question_text` \| `option_text:<0-3>` \| `answer`), `new_value`, `reason` | `CorrectionResponse`: `question_id`, `number`, `field`, `old_value`, `new_value`, `validation_status`, `validation_issues`. Bad field → 422; other user → 404. | Correction workflow (M5). Never edits the original extraction (`original_*` untouched); writes `manual_corrections` + `review_history`, re-runs validation. Top of the precedence chain. |
| `GET /api/v1/documents/{document_id}/report` → 200 | — | `DocumentReportResponse`: `questions_extracted`, `questions_missing_options`, `uncertain_answers`, `conflicting_answers`, `unmatched_key_entries`, `duplicates_found`, `requires_review`, `review_reasons`, `summary`, `rule_set_version`, `created_at`. | Document detail / report view (M5). |

### Resolved-MCQ shape (the frontend's core data model)

Each question in `matched.questions`: `number`, `text`, `options`
(4 strings for MCQ, `[]` for `qa_pair`), `correct_index`
(**−1 = UNKNOWN — the frontend must render it as "Unknown Answer",
never as a correct option**), `correct_letter`, `answer_source`
(`manual` / `trailing-key` / `inline` / `style` / `visual` /
`inferred` / `""`), `confidence`, `raw_confidence`, `verified`,
`inferred`, `status` (`answered` / `unknown` / `conflict-resolved`),
`kind` (`mcq` / `qa_pair`), `answer_text` (qa_pair only), `page`,
`paper`. Plus `pending` items with reasons, `validation_issues`
with codes, `promotion` report, `evidence_trail` per answered
question. Answer precedence (standing): manual > explicit key >
inline > digital style > visual > inferred. Keys never cross-apply
between papers.

### Job stages (async path, `app/workers/processor.py`)

`queued → uploaded → validated → extracted → answers_detected →
matched → scored → completed`, each with per-stage seconds in
`stages[].detail`. Failure names the stage; cancel stops at the next
stage boundary (`cancelled`, never `failed`).

## 4. Async jobs — background processing (M7, engine-DB path)

| Method + path | Request | Response | Consumed by |
|---|---|---|---|
| `POST /api/v1/async-jobs/parse` → 202 | Multipart `file` (PDF) | `AsyncJobCreatedResponse`: `{job_id, document_id, status: "queued", filename, page_count}` | **The main upload path for scans (M4).** Returns immediately; the frontend polls `GET` below. Worker runs in-process when `WORKER_ENABLED=true` (Render) or as `python -m app.workers.runner` (VPS). |
| `GET /api/v1/async-jobs/{job_id}` → 200 | — | `AsyncJobStatusResponse`: `job_id`, `document_id`, `status` (`queued` / `processing` / `done` / `failed` / `cancelled`), `retry_count`, `error`, `result_summary` (`{questions, answered, ...}` when done), `created_at`, `started_at`, `completed_at`, `stages[]` (stage, status, detail with per-stage seconds, created_at). | Polling (M4/M5). Poll interval: 5 s while `queued`/`processing` (matches `worker_poll_seconds`); back off to 15 s after 2 min; stop on terminal state. **No webhook/push exists** — polling is the only mechanism. **M3 (ADR-011): reads the same row `GET /api/v1/jobs/{id}` reads.** |
| `POST /api/v1/async-jobs/{job_id}/cancel` → 200 | — | Cancels queued/processing job → `cancelled`. Second cancel → 409. | Cancel button on a processing document (M4). |
| `POST /api/v1/async-jobs/{job_id}/retry` → 200 | — | Re-queues `failed`/`cancelled` (`retry_count` +1); other states → 409. | Retry button (M4/M5). |

## 5. What the frontend needs that does NOT exist yet (GAPs)

These are **not** endpoints. They must be built in the milestones
named, behind the same auth/ownership rules. Do not invent them as if
they already exist.

| GAP | Needed for | Milestone | Notes |
|---|---|---|---|
| **GAP-1: student profile endpoints** (`GET/POST/PATCH /api/v1/me`, profile fields: full name, phone, preferred exam, education level) | M3 auth/profile, M8 dashboard | M3 | **DONE in M3:** `student_profiles` table (Alembic 0003) + `GET/POST/PATCH /api/v1/me` (JWT user id only, per-user 404s). Supabase Auth owns identity (email/password); the profile is engine-DB data. Does not duplicate or write the Flutter app's Supabase `profiles` table. |
| **GAP-2: document listing for a student** (`GET /api/v1/documents` — paginated, owner-only, with status/counts) | M4 dashboard + My Documents | M4 | **DONE in M4:** `GET /api/v1/documents` (limit 1–100, default 20; `?status=` filter; owner-only; soft-deleted excluded) + `GET /api/v1/documents/{id}` (document + latest job + stage history) + `DELETE /api/v1/documents/{id}` (soft delete, cancels a queued/processing job first) + `GET /api/v1/dashboard/summary` (documents_total, jobs_by_status with all six values, recent 5). Reads the unified engine-DB store (GAP-11). |
| **GAP-3: question-bank endpoints** (`GET /api/v1/questions` — search/filter by subject/topic/source/status/bookmark; `GET /api/v1/questions/{id}`) | M5 question bank | M5 | **DONE in M5:** `GET /api/v1/questions` (search `q`, `document_id`, `status` answered/unknown/pending/inferred/corrected/conflicting, `subject_id`, confidence band, paginated, owner-only) + `GET /api/v1/questions/{id}` (full detail with evidence trail + correction history) + `GET /api/v1/documents/{id}/questions` (per-document results in printed-number order, with counts + `qa_pairs` count) + `GET .../corrections` (audit listing). Extracted questions exist in the engine DB; the read layer is new code in `app/services/questions.py` — the Phase 1 store is untouched. |
| **GAP-4: subjects/topics endpoints** (CRUD-lite: list, create, assign to question) | M5 | M5 | **DONE in M5 (manual assignment only):** `subjects` + `topics` + `question_subjects` tables (Alembic 0005 — doc 03 said 0004, but M4 already used that number), 13 subjects seeded, `GET /api/v1/subjects`, `POST /api/v1/questions/{id}/subjects` (idempotent), `DELETE .../subjects/{subject_id}`. **No auto-classification exists** — the engine never assigns a subject; uncategorised stays uncategorised. No topics are seeded yet. |
| **GAP-5: test builder + sessions** (`POST /api/v1/tests`, `GET /api/v1/tests`, `GET /api/v1/tests/{id}`, question snapshots) | M6 test builder | M6 | **DONE in M6 (builder only — taking the test is M7, results M8):** `test_templates` + `test_sessions` + `test_question_snapshots` + `marking_configs` tables (Alembic 0006, which also creates `documents`/`jobs` idempotently — the M5 carry-over); `GET/POST /api/v1/marking-configs`, `GET /api/v1/tests/availability`, `POST/GET /api/v1/tests`, `GET/PATCH/DELETE /api/v1/tests/{id}`. **Snapshot rule proven:** snapshots copy question text/options/correct answer/evidence state at creation (not FKs); a bank correction after creation leaves the snapshot byte-identical (unit test + E2E). No duplicates unless `allow_repetition: true` (422 otherwise); unknown excluded by default (`excluded_unknown` reported) or explicitly opted in and flagged (`correct_index: -1`); Q&A pairs always excluded (`excluded_no_options`). Marking per test, backend-scored (`score_answers`, Decimal 2dp); PPSC default +1/−0.25/0 seeded. Delete/update only while `status == "created"` (409 once an attempt exists). `test_sessions.server_started_at` stays null until M7. |
| **GAP-6: exam attempt endpoints** (`POST /api/v1/tests/{id}/start`, `POST /api/v1/tests/{id}/answers` (periodic persist), `POST /api/v1/tests/{id}/submit`, server-side timer + marking) | M7 exam interface | M7 | **DONE in M7:** `student_responses` + `test_results` tables (Alembic 0007; downgrade refuses while rows exist); `POST /api/v1/tests/{id}/start` (created → in_progress, `server_started_at` from the server clock, second start 409), `GET /api/v1/tests/{id}/session` (snapshots in order + saved responses + server-computed `remaining_seconds`, null when untimed), `POST /api/v1/tests/{id}/answers` (upsert per snapshot id; only while in_progress and within the limit — after expiry 409 `time_expired`, nothing stored; out-of-range 422; foreign snapshot 404), `POST /api/v1/tests/{id}/submit` (server-side `score_answers`, exactly ONE `test_results` row — double submit returns the same id/marks), `GET /api/v1/tests/{id}/result` (stored row only). Unknown snapshots (`correct_index -1`) are excluded from scoring and counted as `unknown_count` on the result — never scored as wrong, never a 500. `time_taken_seconds` from server timestamps. Marking (+1 / −0.25 / 0) computed on the backend and stored with the session. Never trust frontend-supplied marks. **AMENDED in M9 (security fix):** the session now returns `SessionSnapshotItem` — NO `correct_index`, NO `answer_source` (the key must not reach the browser mid-exam); only `is_unknown` is sent. The test-detail and result endpoints still return the full `SnapshotItem` with the key. |
| **GAP-7: results + analytics endpoints** (`GET /api/v1/tests/{id}/result`, `GET /api/v1/analytics/summary`, subject/topic breakdowns) | M8 results/analytics | M8 | **DONE in M8:** `GET /api/v1/tests/{id}/result` now returns the stored row + `subject_breakdown` + `topic_breakdown` + `weak_areas` + `strong_areas` + `review` (per-question: snapshot text/options, `selected_index`, `correct_index`, evidence source, status correct/incorrect/unattempted/unknown; unknown snapshots shown as unknown, never as correct/incorrect; NO fabricated explanations — review shows only what the engine stored) + `GET /api/v1/results` (paginated, owner-only, newest first). Breakdowns are computed at submit from SAVED attempts only (the test's snapshots + the student's responses + the bank questions' `QuestionSubject` links): per subject/topic {scored, correct, incorrect, unattempted, marks, max_marks, accuracy}; only subjects actually assigned; unassigned questions go under an honest "Uncategorised" bucket — never a forced or invented subject; first-assignment-wins (earliest `QuestionSubject` row). Weak/strong = lowest/highest accuracy among NAMED subjects with ≥3 scored questions (Uncategorised excluded); both empty when no subject qualifies. **Backfill:** M7 results stored with NULL breakdowns are recomputed on read (`ensure_breakdowns`) and persisted — proven on the M7-submitted row (4.5/9.0, 50.0%) in E2E. `POST /api/v1/tests/{id}/retry` (submitted-only, else 409 `test_not_submitted`; new template + session + snapshots byte-identical to the original — sha256-proven in E2E) + `POST /api/v1/tests/from-mistakes` (practice test from the ORIGINAL snapshots of incorrectly-answered questions, never the live bank — a later bank correction leaves the practice test unchanged, proven in E2E; 422 `no_mistakes` when the notebook is empty; cap 200 most recent). **No `/analytics/summary` endpoint was built:** the history page's compare-over-time is a plain chronological marks/% list from stored `GET /results` rows, shown only when ≥2 attempts exist — no fitted trend, no prediction. |
| **GAP-8: bookmarks + mistake notebook endpoints** (`POST/DELETE /api/v1/questions/{id}/bookmark`, `GET /api/v1/mistakes`, notes) | M8 | M8 | **DONE in M8:** `student_question_collections` table (Alembic 0008; downgrade refuses while rows exist): id UUID PK, user_id, question_id FK → extracted_questions ON DELETE CASCADE, collection_type CHECK IN ('bookmark','mistake','custom'), note NULL, UNIQUE(user_id, question_id, collection_type). `GET /api/v1/collections` (filter `?collection_type=`, paginated, owner-only, enriched with the bank question's text/options/correct answer) + `POST /api/v1/collections` (bookmark/custom; **bookmarking twice is idempotent-200** — 201 first time, 200 with `already_exists: true` after; same convention as M5 assign-subject) + `PATCH /api/v1/collections/{id}` (note) + `DELETE /api/v1/collections/{id}`. `POST` with `collection_type="mistake"` → **422** — only the submit flow writes mistake rows. **Mistake rows from submit:** M7's submit service now computes breakdowns and records a `mistake` row for every incorrectly-answered SCORED question in the SAME submit transaction; correct, unattempted and unknown questions create none; a re-submit (idempotent, same result) creates no duplicates. Owner-only everywhere: a foreign question id is a 404, never a leak. |
| **GAP-9: notifications endpoints** (`GET /api/v1/notifications`, mark-read) | M9 (in-app only) | M9 | **DONE in M9 (in-app only):** `notifications` table (Alembic 0009 — doc 03's "0006 in M9" line was stale; 0006 was M6) + `GET /api/v1/notifications` (owner-only, newest first, `?unread_only`, returns `unread_count`) + `PATCH /api/v1/notifications/{id}/read` (idempotent; foreign id 404). Rows written by the real flows in the same transaction: worker success → `upload_done` (+ `review_needed` only when the parse left questions pending), worker failure → `upload_failed`, exam submit → `test_submitted` + `result_ready`. **No email is ever sent or claimed** — email only when a provider is configured and confirms delivery (future, not Phase 2). |
| **GAP-10: admin endpoints** (`GET /api/v1/admin/users`, `/admin/documents`, `/admin/jobs`, `/admin/questions`) | M9 admin foundation | M9 | **DONE in M9:** admin = `app_metadata.is_admin` on the verified Supabase JWT (never a request-body field — a top-level `is_admin`/`role`/`plan` key in a JSON body is ignored and logged as a warning); `require_admin` dependency returns **404** `not_found` for non-admins on every admin route (no-leak pattern). 6 routes under `/api/v1/admin/*`: `overview` (real counts), `users` (profiles + per-user counts, **no email field — the engine DB stores none**), `documents` (latest job status), `jobs` (error text + `error_rows`, `?status=` filter), `errors` (`processing_errors`, newest first), `questions` (`?search=` + `?validation_status=` filters). All paginated, all real engine-DB rows. Admin is read-only in M9 — no `audit_log` writes yet (denied attempts are logged); the frontend `/admin/*` guard is UX only, the API 404 is the enforcement. |
| **GAP-11: unified job/document view** (one endpoint that resolves the dual-store split in doc 01 §2.2) | M4 (blocks document listing) | M3 (design) / M4 (build) | **RESOLVED in M3 (ADR-011):** the engine DB is the single access path; `GET /api/v1/jobs/{id}` and `GET /api/v1/async-jobs/{id}` read the same row; vocabulary unified on `done`. No new endpoint was needed — the unified view IS the single store. M4 builds the document listing on top of it. |
| **GAP-12: per-question image/asset serving** (signed URL for `question_assets` crops) | M5 (questions with figures) | M5 | **NOT BUILT in M5 — nothing to serve:** no code anywhere in the pipeline creates `question_assets` rows (verified by grep — only the model exists), so a serving endpoint would serve an empty set. Recorded for M9/M10: when a pipeline stage starts writing assets, the endpoint must go through signed, owner-checked URLs — never public. |

## 6. Endpoints the frontend must NOT use

- **No quota/premium/user-management endpoints exist** — do not
  call any; do not invent them. Admin endpoints DO exist now
  (M9, read-only, under `/api/v1/admin/*`, `require_admin`).
- **No Gemini endpoints** — the advisory adapter has no HTTP surface
  and is disabled by default.
- **No direct Supabase PostgREST calls from the browser for engine
  tables** — the frontend talks to the FastAPI backend; Supabase JS
  client is used for Auth only (see doc 04 §5, doc 05 §2).
- **`/metrics`** is for admin/monitoring, not for student-facing UI.
