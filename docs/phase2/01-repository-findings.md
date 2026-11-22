# Phase 2 M1 — Repository Findings

**Date:** 2026-11-22
**Branch:** `officerpath-phase2-web` (from `69ca62d`)
**Method:** read the code and ran read-only inspections. Every claim below
cites the file it was verified against, or is labelled **UNVERIFIED**.
The Phase 1 completion report (`docs/PHASE_1_COMPLETION_REPORT.md`) was
used as a starting point and checked against the code; where they disagree,
the code wins and the disagreement is listed in §6.

## 1. Git state (verified 2026-11-22)

- **No remote is configured** (`git remote -v` returns nothing). Nothing
  has ever been pushed from this machine; CI has never run on GitHub.
- **Phase 1 head:** `69ca62d` — "M8: full suite, final benchmark, docs,
  deployment guide, Phase 1 completion report" (`git log`).
- **Phase 2 branch:** `officerpath-phase2-web`, created from `69ca62d`
  in this milestone. All Phase 2 work lives here.
- **Working tree at M1 start:** clean (`git status --short` empty, apart
  from the 2 M6 run logs, which are gitignored — see §4).
- **Commit history (Phase 1):** `9a584f0` (M1) → `9e20654` (M2) →
  `5b397ec`/`670df43`/`a769157`/`d1e11ac` (M3) → `111f3f2` (M4) →
  `a430297` (M5) → `9db0fc0` (M6) → `1051fe4` (M7) → `69ca62d` (M8).

## 2. What exists — inventory

### 2.1 Backend (the Phase 1 engine — complete, local only)

- **Stack:** Python 3.12, FastAPI 0.165.0, Pydantic v2, SQLAlchemy 2.0.44,
  Alembic 1.16.4, psycopg 3.2.10, supabase-py 2.15.3
  (`requirements.txt`, `pyproject.toml:24` pins `python_version = "3.12"`).
- **Entry point:** `app/main.py` — FastAPI app, lifespan (Supabase
  clients + optional in-process worker), two middlewares (request-id +
  JSON logging; request-size limit 422 `file_too_large`), three exception
  handlers (ApiError / validation / unhandled). Routers included at
  `app/main.py:174-178`: `health`, `metrics`, `v1/routes`, `v1/review`,
  `v1/async_jobs`.
- **Routes (verified live from `app.openapi()`):** 17 paths — 14 under
  `/api/v1/*` plus `GET /health`, `GET /version`, `GET /metrics`. Full
  list with request/response shapes: `docs/phase2/02-api-integration-map.md`.
- **Pipeline packages (`app/pipeline/`):** `ingestion` (validator,
  classifier, service), `pdf` (analysis, classifier, quality, renderer),
  `preprocess` (6 profiles, mark retention), `ocr` (digital, tesseract,
  paddle, gemini-advisory, registry, router, service, normalize, metrics,
  psm, deployment), `layout` (analyzer, columns, service), `extract`
  (12 files — Dart parser port), `answers` (9 files — key, inline, style,
  visual, handwriting detectors + precedence), `matching` (9 files —
  promotion, key-region, validation, calibration, report, service, store).
- **Workers:** `app/workers/processor.py` (atomic claim, per-stage
  timeout, cancel, retry) + `app/workers/runner.py` (`run_once` /
  `run_forever` / CLI) — ADR-009.
- **Config:** `app/config.py` — every setting is an env var with a
  default; `.env.example` is the complete inventory (Supabase URL/keys,
  DATABASE_URL, storage, limits, rate limits, OCR, Gemini, worker).
- **Observability:** `app/utils/logging.py` (structured JSON, secret
  redaction — regex `key|token|secret|password|auth|bearer`,
  `app/utils/logging.py:12`), `app/utils/metrics.py`,
  `app/api/metrics.py` (Prometheus-style), `app/api/health.py` (real
  dependency state, truthfully `degraded` without a database).
- **Security:** `app/security/dependencies.py` (`get_current_user` —
  Supabase JWT via `auth.get_user`, never decoded locally,
  `app/integrations/supabase_auth.py:12-52`), `app/security/rate_limit.py`
  (in-memory per-user sliding window), `app/core/errors.py` (uniform
  `{error: {code, message}}` shape, 4xx never 500 for bad input).

### 2.2 Database — two persistence paths (the most important finding)

Phase 1 has **two different stores holding two different kinds of rows**,
and Phase 2 must not pretend they are one.

| Path | Used by | Tables / rows | Auth |
|---|---|---|---|
| **Supabase PostgREST** (`app/database/repositories.py`, `app/database/supabase_client.py`) | `POST /documents/register`, `POST /documents/upload`, `POST /documents/upload/batch`, `GET /jobs/{id}`, `POST /jobs/{id}/retry` | `public.documents`, `public.jobs` (migration 015 — **not applied live**) | anon client for reads, service client for writes; RLS policies in 015 |
| **SQLAlchemy engine DB** (`app/db/session.py`, `DATABASE_URL`, pool 2+2) | `POST /documents/parse`, `POST /documents/parse-image`, review list, corrections, report, async-jobs submit/poll/cancel/retry, worker | 17 engine tables via Alembic 0001/0002 (`app/db/models.py`) | JWT user id carried in `user_id` columns; ownership checked in code |

Consequences, verified in code:

- A job created by `register` (Supabase) **is not the same row** as a job
  created by `async-jobs/parse` (engine DB). `GET /api/v1/jobs/{id}`
  reads Supabase (`app/services/jobs.py:108-114`); `GET
  /api/v1/async-jobs/{job_id}` reads the engine DB
  (`app/api/v1/async_jobs.py:52` uses `get_session()`). Neither endpoint
  can see the other's jobs.
- `GET /api/v1/jobs/{job_id}/review` reads the **engine DB**
  (`app/api/v1/review.py:174` uses `get_session()`), so a Supabase-only
  job has no review queue until it is parsed through the engine path.
- **Status vocabulary split:** Supabase `public.jobs.status` check
  constraint is `('queued','uploading','processing','done','failed',
  'cancelled')` (`supabase/migrations/015_documents_jobs.sql`, and the
  `JobStatus` enum in `app/schemas/documents.py:25-31` matches it with
  `done`). The async worker uses **`completed`** instead
  (`app/workers/processor.py:222`, `app/api/v1/async_jobs.py` responses,
  `jobs_total{status="completed"}` metric). The SQLAlchemy `Job.status`
  is a plain `String(32)` with no check constraint
  (`app/db/models.py:107-135`), so `completed` is legal in the engine
  DB — but it would **violate the 015 check constraint** if ever written
  to `public.jobs`. Phase 2 must unify the vocabulary (see
  `03-database-extension-plan.md` §5) and must never write a
  `completed` status through PostgREST.

### 2.3 SQLAlchemy models (17 tables, `app/db/models.py`)

`documents`, `jobs`, `document_pages` (+ `layout_applied` JSON, Alembic
0002), `processing_stages`, `ocr_blocks`, `extracted_questions`,
`question_options`, `question_assets`, `extracted_answers`,
`answer_evidence`, `answer_sources`, `extraction_reports`,
`manual_corrections`, `review_history`, `processing_errors`,
`audit_log`, `rule_sets`. Key columns for Phase 2 reuse:
`ExtractedQuestion` (`original_text` vs `normalized_text`,
`source_pages`, `ocr_confidence`, `extraction_confidence`,
`validation_status` default `unreviewed`, `content_fingerprint`,
`duplicate_of_id`, soft-delete `deleted_at`); `QuestionOption`
(`original_label`/`normalized_label`, `label_inferred`, `position`);
`ExtractedAnswer` (`status`, `resolved_label`, `resolution_method`,
`resolution_score`); `ManualCorrection` + `ReviewHistory`
(`reviewer_id`, `target_type`, `target_id`, `decision`, `note`) —
the audit trail for corrections; `ExtractionReport` (counts +
`requires_review` + `review_reasons`); `Document` (`content_hash`
SHA-256 dedup, `deleted_at` soft delete, indexes on
`(user_id, created_at)` and `(user_id, content_hash)`).

**What does NOT exist in the engine schema:** no `profiles` table, no
`subjects`/`topics`, no test/session/result/bookmark/mistake/notification
tables, no admin/role column, no subscription/premium fields. The engine
never writes `profiles.plan` / `premium_until` / `is_admin` and never
touches `activation_codes` or `payments` (`docs/API.md`, "What Phase 1
does NOT expose"). Those live in the Flutter app's Supabase schema
(migrations 001–014, see §2.4) and are out of scope for the engine.

### 2.4 Supabase (project `officerpath-ai`, ref `gliebuyyjguxrwdfuakz`)

- Verified in `.env.example` (`SUPABASE_URL=https://gliebuyyjguxrwdfuakz.supabase.co`)
  and `README.md:195`.
- **Migrations 001–014 are live** in the Flutter repo
  (`~/workspace/officerpath-ai/supabase/migrations/001_schema.sql` …
  `014_realtime_payments.sql` — listing verified 2026-11-22). They own
  the Flutter app's auth-adjacent tables (`profiles`,
  `activation_codes`, `payments`, `test_results`, `waitlist`,
  `sent_notifications`, `redeem_attempts` — named in
  `supabase/migrations/015_documents_jobs.sql:11-14` as tables 015 must
  never touch).
- **Migration 015 is written but NOT applied live**
  (`supabase/migrations/015_documents_jobs.sql`, 170 lines, + down file
  `015_documents_jobs_down.sql`, 29 lines). It creates `public.documents`
  and `public.jobs`, RLS policies (owner view/insert; cancel-only update;
  admin view-all), and the private `pdf-documents` bucket with per-user
  path policies. Apply procedure + verification queries:
  `docs/migration-015-apply.md`.
- **Live Supabase state was NOT re-checked in this milestone** (no
  dashboard access from this agent). The claim "001–014 live" rests on
  the M0 audit (2026-11-21, live-verified then) and the Phase 1
  completion report; label it **UNVERIFIED as of today** for the current
  state of tables, RLS, and the bucket. M2 must re-verify it before
  building auth against it.
- **Storage integration:** `app/integrations/supabase_storage.py`
  (`create_signed_download_url`) is defined but **unused by any flow**
  (0% coverage, M8 report) — the register/upload path stores originals
  on local disk (`var/storage`, `app/storage/local.py`) in dev and relies
  on the client having already uploaded to the bucket for the register
  flow. `var/` is currently empty (verified).

### 2.5 Tests and fixtures

- **492 tests collected** (`pytest --collect-only -q`, 2026-11-22) —
  matches the M8 claim. 57 test files under `app/tests/`.
- **Golden dataset:** `app/tests/fixtures/golden/dataset.json`
  (38 entries) + `ppsc66/` fixtures (PDFs, OCR text, ground-truth JSON,
  photos) + `synthetic-nastaliq/` + `m2/` synthetic PDFs.
- **CI:** `.github/workflows/ci.yml` — lint, typecheck, test (with
  system Tesseract), security (pip-audit, detect-secrets vs
  `.secrets.baseline`), Alembic up/down on SQLite, Docker build.
  **Gap:** it triggers only on `main` and `officerpath-phase1-engine`
  — it will **not** run on `officerpath-phase2-web` until the branch
  list is updated (M2 task).
- **Coverage (M8, agent-measured, not re-run here):** 89% overall;
  schemas/storage 100%, db 99.3%, matching 93.2%, layout 93.8%, api
  87.1%, answers 86.7%, ocr 86.3%, workers 79.7%, ingestion 77.2%,
  integrations 51.6% (`supabase_storage.py` 0%).

### 2.6 Deployment configuration

- `render.yaml` — Blueprint for a Docker web service, plan `free`,
  `healthCheckPath: /health`, env vars incl. `DEPLOYMENT_PROFILE=
  render-free`, `PADDLEOCR_ENABLED=false`, `WORKER_ENABLED=true`,
  `WORKER_STAGE_TIMEOUT_SECONDS=1800`, `TESSERACT_TIMEOUT_SECONDS=300`,
  secrets as `sync: false`. **Note:** `branch:` is still
  `officerpath-phase1-engine` — it must be updated when the Phase 2
  backend is deployed (see `06-deployment-plan.md`).
- `Dockerfile` — multi-stage, python:3.12-slim, non-root `appuser`,
  installs `tesseract-ocr` + `eng`/`urd`/`ara`/`osd`, copies `app/` +
  `alembic/`, `HEALTHCHECK` on `/health`, CMD `uvicorn app.main:app`.
  **Never built** — no Docker on the VM (stated in the file itself and
  in `docs/deploy-render.md`); the first CI build after the push
  verifies it.
- `docs/deploy-render.md` (M8, verified against M8 code) — Render free
  Stage 1, keep-alive **DEFERRED**, `ENVIRONMENT=production`, secrets
  via Dashboard only.
- **Nothing is deployed.** No Render service exists from this work
  (owner step, never done). No push, no CI run, no Docker build.

### 2.7 Flutter app (legacy client — NOT the Phase 2 frontend)

- `~/workspace/officerpath-ai/`, v2.0.5+5500, the live product today.
- **"Server parse" toggle prepared only:** exactly 3 files touched
  2026-11-22 — `lib/services/server_parse_service.dart` (new,
  `parsePdf` + `parseImage`), `lib/services/pdf_import_service.dart`
  (`importPdf` + `importImage` route to the server when ON),
  `lib/screens/ai_settings_screen.dart` (SwitchListTile, default OFF,
  not-deployed-yet warning). Verified present 2026-11-22.
- **No `.git` in `~/workspace/officerpath-ai/`** (verified) — no branch
  exists, changes are uncommitted files only; `flutter analyze` was
  never run (no SDK on the VM — owner step). No APK, no release, no
  version bump.
- The Flutter app must not dictate the web architecture (Phase 2
  prompt §1). It remains a legacy client.

## 3. What is live vs local-only

| Item | State |
|---|---|
| Engine code (M0–M8) | Local only, branch `officerpath-phase1-engine`, commit `69ca62d`. Never pushed (no remote). |
| Engine tests (492) | Local only; CI never ran (no push). |
| Migration 015 | Written, **not applied live**. |
| Alembic 0001/0002 | Verified on SQLite only (CI job); never applied to live Postgres. |
| Render deploy | Never done. `render.yaml` + `Dockerfile` are config only. |
| Docker image | Never built. |
| Gemini key | Deferred by the owner; no key provisioned; no Gemini API call ever made. |
| Flutter toggle | Prepared-only files; no branch, no analyze, no release. |
| Supabase 001–014 | Live (per M0 audit 2026-11-21; **UNVERIFIED today** — re-check in M2). |
| Flutter app v2.0.5 | Live product (separate repo, out of Phase 2 scope except as legacy client). |

## 4. Working-tree notes

- The 2 M6 run logs (`docs/benchmarks/m6-benchmark-run.log`,
  `m6-psm-experiment-run.log`) are deliberately uncommitted and are now
  in `.gitignore` (`docs/benchmarks/*.log`, added in M8) — verified
  ignored, not committed, on the new branch.
- `.coverage` is also gitignored (M8).

## 5. Measured Phase 1 realities Phase 2 must design around

(Copied from the Phase 1 completion report §3/§6 — all VM numbers,
M7 clean baseline unless noted.)

- PPSC-66 live: 40/100 single-path, 53/100 multi-pass (61/62 correct);
  Q1–9 clipped at the page edge (ceiling ≤ 91/100). Paper 60 live: 1/20
  via Tesseract. **The web UI must present these as the engine's real
  limits, never promise better.**
- Latency: PPSC-66 single-path ~128 s on the dev VM (~20 min estimated
  at Render free 0.1 CPU); multi-pass ~359 s. **Sync parse is not a
  web-UX path for scans — the async job model is mandatory for the
  frontend.**
- Memory: worst fresh-process tree peak 465 MB vs 512 MB Render free
  (~47 MB headroom, marginal). One parse at a time; long-lived worker
  accumulates RSS with no restart policy.
- Rate limits: 10 register/parse attempts per user per minute,
  5 retries per minute (in-memory, per process).
- File limits: 100 MB per file, 100 pages per job, 5 MB per page image,
  batch ≤ 20 files; images ≤ 25 MP / 12,000 px per side.
- Calibration: ECE 0.0003, but below confidence 1.0 **UNVERIFIED**
  (1,558 of 1,559 pairs are at 1.0). Handwriting answer-mark class
  **UNVERIFIED**. Monthly Current Affairs answers **UNKNOWN**.
- PyMuPDF is AGPLv3 (ADR-004) — unresolved for closed-source
  distribution.

## 6. Drift and disagreements found (code vs Phase 1 report/docs)

1. **Dual job stores + `done` vs `completed` (REAL, §2.2).** The
   completion report §8 lists one job-state machine (`queued →
   processing → completed / failed / cancelled`) but the M1 register
   flow and migration 015 use `done`, and the two job tables are
   different rows in different stores. The report's single state
   machine describes the **async-jobs/engine-DB path only**. Phase 2
   must unify this before the frontend polls job status (see
   `03-database-extension-plan.md` §5).
2. **Gemini activation needs THREE conditions, not two.**
   `app/pipeline/ocr/gemini.py:8-14` header says "TWO things" but the
   code checks three (`gemini.py:109-114`): `enabled`, `api_key`,
   `max_calls_per_day > 0`. Minor doc drift; the behaviour (disabled
   by default, no calls ever made) is as reported.
3. **`CHANGELOG.md` is stale** — latest entry is `[0.5.0] — 2026-11-21 —
   Phase 1 M4`. M5–M8 were never logged. The milestone reports are the
   current record; the CHANGELOG is not.
4. **`TEST_REPORT.md` is stale** — dated 2026-11-20, reports "22 passed",
   the M0 skeleton. Superseded by the milestone reports and M8
   (492 tests). It should be archived or updated, not quoted.
5. **CI does not cover the Phase 2 branch** (`.github/workflows/ci.yml`:
   `branches: [main, officerpath-phase1-engine]`). Not a Phase 1
   error — the branch did not exist — but M2 must add
   `officerpath-phase2-web` or CI silently skips Phase 2 work.
6. **`render.yaml` branch is `officerpath-phase1-engine`.** Correct for
   the Phase 1 backend today; it must change when the Phase 2 backend
   ships, or Render will keep deploying the Phase 1 branch.
7. **No disagreement found** in: route list (17 paths — matches
   `docs/API.md`), response shapes (spot-checked `ParseResponse`,
   `AsyncJobStatusResponse`, `CorrectionResponse` against
   `app/schemas/review.py` and `app/schemas/async_jobs.py`), test count
   (492 collected — matches M8), model inventory (17 tables — matches
   ADR-003/M1), or the accuracy/latency/memory tables (not re-run in
   M1; they are M8 measurements, cited as such).

## 7. What M1 could not verify

- **Live Supabase state** (tables, RLS policies, bucket, Edge
  Functions, auth settings): not re-checked — no dashboard access from
  this agent. M2 must verify before building auth.
- **Live Render/GitHub state:** no remote, no dashboard access; the
  "never deployed / never pushed" claims rest on the absence of a
  remote and the Phase 1 record.
- **Docker build:** no Docker on the VM — `Dockerfile` verified by
  config only (as in M1–M8).
- **M8 benchmark numbers:** not re-run in M1 (audit only); cited from
  the M8 benchmark JSON and report.
