# OfficerPath PDF Engine

Server-side document intelligence engine for **OfficerPath AI**
(Phase 1, Master Prompt Ultimate Edition + v2, Milestones M0–M8).

> **Phase 1 M2 scope.** This service registers documents, ingests and
> validates uploaded files (magic bytes, limits, SHA-256 dedup,
> per-page classification), stores originals immutably, tracks
> processing jobs + pipeline stage history, and exposes health/version
> endpoints. M2 adds the PDF stage: PyMuPDF analysis (digital/scanned/
> mixed/blank per page), rendering at bounded DPI, measured per-page
> quality (blur, contrast, noise, skew, ink), and adaptive OpenCV
> preprocessing with mark preservation (ticks/stars/circles/underlines/
> highlights survive; colour copies kept). Run it with
> `scripts/run_m2_pipeline.py <file>` (the M7 worker will call the same
> `run_pdf_stage`). It does **not** do OCR, layout, or parsing yet —
> that is M3–M5. The Flutter app and live Supabase are untouched by this
> repo except for the documented migration steps below.

## What it does (M1)

- `GET /health` — app health; checks Supabase reachability when configured
  (200 healthy, 503 when a configured dependency is unreachable). No secrets
  in the response.
- `GET /version` — app version, git commit (when available), environment.
- `POST /api/v1/documents/register` — authenticated (Supabase JWT), validates
  document metadata, creates a document record + a durable processing job.
  Ownership enforced; idempotent (idempotency key, or same storage path +
  user → same job, no duplicates).
- `POST /api/v1/documents/upload` — authenticated multipart upload: validates
  file bytes, stores the original immutably, dedups by SHA-256 (same user +
  same file → original document + job, `idempotent_replay: true`), returns
  per-page classification. Rejected files answer 422 with a
  machine-readable code (e.g. `magic_bytes_mismatch`, `pdf_encrypted`,
  `file_too_large`). No OCR yet — the file is queued for M2+ processing.
- `POST /api/v1/documents/upload/batch` — up to 20 files; per-file results
  (stored / replay / rejected with reasons). One bad file never blocks
  the batch.
- `GET /api/v1/jobs/{job_id}` — job status, owner-only (404 for other users).
- `POST /api/v1/jobs/{job_id}/retry` — owner-only, only from
  `failed`/`cancelled`, increments the retry count, rate-limited.

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.x + Alembic ·
PyMuPDF · OpenCV (headless) · Pillow · NumPy ·
Uvicorn · Supabase Python client · structured JSON logging · pytest ·
ruff · mypy.

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill in your own keys; never commit .env
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/version
```

Without Supabase env vars the app still starts; `/health` reports
`supabase: not_configured` (status `degraded`) and authenticated
endpoints answer 503 `auth_unavailable` until Supabase is configured.

## Tests

```bash
pytest -q
```

Tests use an in-memory fake Supabase client — no network, no live
Supabase. See `TEST_REPORT.md`.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | yes (for auth) | e.g. `https://gliebuyyjguxrwdfuakz.supabase.co` |
| `SUPABASE_ANON_KEY` | yes (for auth) | Publishable key; used to verify user JWTs |
| `SUPABASE_SERVICE_ROLE_KEY` | yes (for job writes) | **Server-side only.** Never in the Flutter app, never in a response, never logged |
| `DATABASE_URL` | no | SQLAlchemy URL for the engine-owned tables (Alembic). Without it the API still serves; stage history is logged, not persisted |
| `STORAGE_BACKEND` | no | `local` (M1 only) |
| `STORAGE_ROOT` | no | Default `var/storage` |
| `ENVIRONMENT` | no | `development` / `staging` / `production` |
| `PORT` | no | Default `8000` |
| `RATE_LIMIT_REGISTER_PER_MINUTE` | no | Default 10 |
| `RATE_LIMIT_RETRY_PER_MINUTE` | no | Default 5 |

## Database — NOT applied live yet

1. Supabase migration `supabase/migrations/015_documents_jobs.sql`
   creates two new tables (`documents`, `jobs`) with RLS and a new
   private bucket (`pdf-documents`). **It has not been applied to live
   Supabase.** Apply it only with the owner's go-ahead, via Dashboard
   → SQL Editor — exact steps + verification queries:
   `docs/migration-015-apply.md`. It is additive-only: it does not
   modify any existing table, policy, trigger, bucket, or Edge
   Function, and never touches `profiles`, `activation_codes`,
   `payments`, `test_results`, `waitlist`, `sent_notifications`, or
   `redeem_attempts`.
2. Alembic revision `0001_m1_engine_tables` creates the 15
   engine-owned §14 tables (pages, stages, OCR blocks, questions,
   options, answers, evidence, reports, corrections, review history,
   errors, audit log, rule sets). Apply AFTER 015, with `DATABASE_URL`
   set: `alembic upgrade head`. Reversible: `alembic downgrade base`.
   Local up/down is tested on SQLite (see `app/tests/test_schema.py`);
   Postgres-only behaviour (RLS, bucket) is verified only by the
   Dashboard queries in `docs/migration-015-apply.md`.

## Deploy (Render free tier, Stage 1) — NOT deployed yet

Full procedure: `docs/deploy-render.md` (+ `render.yaml` blueprint).
Summary: the owner connects the GitHub repo
`hasankhan62742-beep/officerpath-pdf-engine` (branch
`officerpath-phase1-engine`) to Render as a Docker web service on the
**Free** plan, sets the env vars from the table above in the Render
Dashboard, and deploys. Health check path is `/health`.

Cloud Run is PARKED (ADR-001): GCP billing is paused after 3–4
rejected cards, and Cloud Run needs a billing account even inside the
free tier. Do not create any GCP resource in Phase 1.

**Blockers (need the user, in his own browser):**

1. The GitHub repo link + branch (M1 git step; the repo exists but is
   still empty on GitHub — code is local until pushed).
2. Migration 015 applied live (see above).
3. Render account + repo connection (free tier; if Render asks for a
   card at signup, stop and report — do not enter payment details).

Keep-alive decision: **deferred** (ADR-001). Render free sleeps after
15 min idle (~30–60 s wake). No keep-alive ping is configured in M1.

### Rollback

Render Dashboard → service → **Rollback** restores the previous
deploy with no rebuild. Rollback restores code + config, not external
state (Supabase data, secrets changed since). Database rollback is
the Alembic/015 down paths in `docs/migration-015-apply.md` — only
after confirming no jobs depend on them.

## Graceful shutdown

Render sends **SIGTERM** when stopping an instance. Uvicorn handles
it: it stops accepting new connections and finishes in-flight requests
before exiting. Keep individual requests short; long work belongs in
the async job model (register → poll), not in a single HTTP call.

## Rate limiting

Phase 1 uses a simple in-memory per-user sliding window (see
`app/security/rate_limit.py`). It is **not shared across instances**;
with max-instances=1 that is acceptable. Replace with a distributed
limiter before running more than one replica.

## Security rules (from `SECURITY_AUDIT_2026-11-20.md`)

- No secrets in code, in the repo, in logs, or in API responses.
  `.env.example` has placeholders only.
- The service-role key is used server-side only, from env vars.
- Auth is verified by Supabase Auth itself (`auth.get_user`); tokens
  are never decoded locally with a hardcoded secret.
- Ownership is enforced on every endpoint; other users' jobs answer
  404, never leak existence.
- This backend never writes `profiles.plan` / `premium_until` /
  `is_admin`, never touches `activation_codes` or `payments`, and
  never grants Premium. Quota (Phase 1B) is a convenience limit, not
  an entitlement control.

## Project layout

```
app/
  main.py            FastAPI app, middleware, error handlers
  config.py          Settings (env only)
  api/health.py      GET /health, GET /version
  api/v1/routes.py   register, upload (single + batch), jobs
  core/errors.py     Structured error model
  database/          Supabase clients + repositories (documents, jobs)
  db/                SQLAlchemy models + session (ADR-003)
  integrations/      Supabase Auth verify, Storage signed URLs
  pipeline/          Stage interfaces + registry + state machine (M1)
  pipeline/ingestion/  Validation, per-page classification, ingestion service
  schemas/           Pydantic v2 request/response models
  security/          Auth dependency, in-memory rate limiter
  services/jobs.py   Register / status / retry business rules
  storage/           StorageBackend interface + local-disk impl
  workers/processor.py  Job worker skeleton (M2+: OCR + parse)
  utils/logging.py   Structured JSON logging (secrets redacted)
  tests/             pytest suite (fake Supabase client, no network)
alembic/             Alembic env + revisions (0001: §14 tables)
supabase/migrations/015_documents_jobs.sql   (NOT applied live)
  015_documents_jobs_down.sql  (reversal)
docs/                audit, ADRs, deploy + migration guides, M1 report
render.yaml          Render Blueprint (Stage 1, free tier)
Dockerfile  .github/workflows/ci.yml  requirements.txt
```

## M2+ (not started)

- M2: PDF analysis, page classification (exact, PyMuPDF), rendering,
  adaptive preprocessing (OpenCV).
- M3: OCR abstraction + engines (digital extractor, Tesseract,
  PaddleOCR benchmarked; Gemini-advisory disabled by default).
- M4–M5: MCQ/option extraction, answer detection.
- M6: matching, confidence scoring, reports, review APIs.
- M7–M8: background jobs, security hardening, benchmarks, deployment.

The Gemini server key is deferred by the owner ("baad ki bat hai") —
do not keep asking for it. No paid AI or infrastructure is provisioned
without his explicit approval.
