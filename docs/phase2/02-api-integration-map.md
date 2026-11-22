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
| **GAP-2: document listing for a student** (`GET /api/v1/documents` — paginated, owner-only, with status/counts) | M4 dashboard + My Documents | M4 | No list endpoint exists. `register`/`upload` return single documents only. Must read the unified job/document view (see §6). |
| **GAP-3: question-bank endpoints** (`GET /api/v1/questions` — search/filter by subject/topic/source/status/bookmark; `GET /api/v1/questions/{id}`) | M5 question bank | M5 | Extracted questions exist in the engine DB but have no read API except via parse response / review list / report. |
| **GAP-4: subjects/topics endpoints** (CRUD-lite: list, create, assign to question) | M5 | M5 | No subject/topic model exists anywhere. New tables, see doc 03. |
| **GAP-5: test builder + sessions** (`POST /api/v1/tests`, `GET /api/v1/tests`, `GET /api/v1/tests/{id}`, question snapshots) | M6 test builder | M6 | Entirely new. Snapshot rule: a past test must not change when the bank is edited. |
| **GAP-6: exam attempt endpoints** (`POST /api/v1/tests/{id}/start`, `POST /api/v1/tests/{id}/answers` (periodic persist), `POST /api/v1/tests/{id}/submit`, server-side timer + marking) | M7 exam interface | M7 | Marking (+1 / −0.25 / 0) must be computed on the backend and stored with the session. Never trust frontend-supplied marks. |
| **GAP-7: results + analytics endpoints** (`GET /api/v1/tests/{id}/result`, `GET /api/v1/analytics/summary`, subject/topic breakdowns) | M8 results/analytics | M8 | Computed from saved attempts only — never fabricated. |
| **GAP-8: bookmarks + mistake notebook endpoints** (`POST/DELETE /api/v1/questions/{id}/bookmark`, `GET /api/v1/mistakes`, notes) | M8 | M8 | Private per student. |
| **GAP-9: notifications endpoints** (`GET /api/v1/notifications`, mark-read) | M9 (in-app only) | M9 | In-app only in Phase 2. Email only when a provider is configured and confirms delivery. |
| **GAP-10: admin endpoints** (`GET /api/v1/admin/users`, `/admin/documents`, `/admin/jobs`, `/admin/questions`) | M9 admin foundation | M9 | Backend-enforced admin role. **No admin role exists anywhere today** — no `is_admin` in the engine; the Flutter app's admin concept lives in its own Supabase tables. New design required (doc 05). |
| **GAP-11: unified job/document view** (one endpoint that resolves the dual-store split in doc 01 §2.2) | M4 (blocks document listing) | M3 (design) / M4 (build) | **RESOLVED in M3 (ADR-011):** the engine DB is the single access path; `GET /api/v1/jobs/{id}` and `GET /api/v1/async-jobs/{id}` read the same row; vocabulary unified on `done`. No new endpoint was needed — the unified view IS the single store. M4 builds the document listing on top of it. |
| **GAP-12: per-question image/asset serving** (signed URL for `question_assets` crops) | M5 (questions with figures) | M5 | `question_assets` rows exist; no endpoint serves them. Must go through signed, owner-checked URLs — never public. |

## 6. Endpoints the frontend must NOT use

- **No admin/quota/premium/user-management endpoints exist** — do not
  call any; do not invent them (GAP-10 covers the real need).
- **No Gemini endpoints** — the advisory adapter has no HTTP surface
  and is disabled by default.
- **No direct Supabase PostgREST calls from the browser for engine
  tables** — the frontend talks to the FastAPI backend; Supabase JS
  client is used for Auth only (see doc 04 §5, doc 05 §2).
- **`/metrics`** is for admin/monitoring, not for student-facing UI.
