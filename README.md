# OfficerPath PDF Engine

Server-side document intelligence engine for **OfficerPath AI**
(Phase 1, complete 2026-11-22 — Milestones M0–M8, branch
`officerpath-phase1-engine`, local only, not yet pushed or
deployed).

It turns a student's upload — a PDF or a phone photo of a
competitive-exam paper (PPSC/FPSC/BPSC/SPSC/KPSC/CSS/PMS/NTS)
— into structured, traceable, test-ready MCQs: question +
4 options + answer + the evidence for that answer (which
detector fired, its confidence, its source page). An answer
with no evidence is never returned; an unknown answer stays
UNKNOWN, never guessed.

The Flutter app (v2.0.5) stays the product; this engine is the
server it talks to when the "Server parse" toggle is ON
(prepare-only in Phase 1 — see "Flutter toggle" below).

## What it does (Phase 1, final)

- **Ingest + validate (M1):** magic-byte checks, size/page
  limits, SHA-256 dedup, per-page classification, immutable
  originals.
- **PDF analysis + rendering (M2):** PyMuPDF analysis, bounded
  200 DPI rendering, 6 OpenCV preprocessing profiles, per-page
  failure isolation.
- **OCR + layout (M3):** digital text first; Tesseract 5.3.4
  (eng+urd, PSM 3) for scans; PaddleOCR measured and gated to
  VPS-only (it peaks at 1.8–3.7 GB — it cannot run on Render
  free); Gemini-advisory disabled by default (no key
  provisioned, no Gemini API calls ever made).
- **MCQ extraction (M4):** a verbatim port of the Flutter Dart
  parser — 5 format paths including first-class `qa_pair`
  (Q&A without options), table paths, candidate scoring.
- **Answer detection (M5):** trailing-key, inline, style
  (star/bold), visual marks, handwriting (marginalia only);
  precedence resolver (manual > key > inline > style >
  visual > inferred); paper-identity gate (a key never
  cross-applies between papers).
- **Matching + calibration + review (M6):** resolved MCQs with
  evidence trails, pending-question promotion (ADR-007),
  key-region location, per-question validation with reason
  codes, empirical confidence calibration, per-document
  reports (JSON + markdown), review/correction APIs.
- **Jobs + security + observability + performance (M7):**
  async job pipeline with per-stage timeouts, retry and
  cancel; per-user 404s, size limits, rate limits; structured
  JSON logs, real `/health` and `/metrics`; profiled latency
  (Tesseract is ~93% of a PPSC-66 parse); multi-pass union
  merge as an optional mode; server image endpoint for photos.
- **M8:** full suite + coverage, final benchmark, this
  documentation, deployment guide, Phase 1 completion report
  (`docs/PHASE_1_COMPLETION_REPORT.md`).

Full API reference: `docs/API.md`. Deployment:
`docs/deploy-render.md` (+ `render.yaml` blueprint).
Decisions: `docs/adr/ADR-001` … `ADR-010`. Milestone
reports: `docs/milestones/MILESTONE_1_REPORT.md` …
`MILESTONE_8_REPORT.md`. Benchmarks:
`docs/benchmarks/BENCHMARK_M3` … `BENCHMARK_M8_2026-11-22.md`.

## Measured results (M8 final, VM numbers — NOT Render numbers)

| Fixture | Questions | Answers | Notes |
|---|---|---|---|
| TestPoint (1,375 GT) | Q 0.98 / 1.0 / 0.9899 | **1.0 / 1.0 / 1.0** | 28 residual FPs (numberless fragments, never a wrong answer) |
| Computer Q&A (960 GT) | Q 0.8846 / 0.6948 / 0.7783 | 0.991 | Q&A pairs, no options by design |
| CA40 (40 GT) | 1.0 / 1.0 / 1.0 | **1.0** | |
| Urdu NOA (135 GT) | Q 1.0 / 0.7778 / 0.875 | **1.0** | Lowercase (a.–d.) option markers |
| PPSC-66 live (single-path) | 41 q, 41 answered | 40/100 distinct numbers, 40/40 correct | OCR ceiling; Q1–9 clipped at page edge |
| PPSC-66 live (multi-pass, optional) | 62 q, 62 answered | 53/100, 61/62 correct | 2.8–3.1× time, same memory band |
| Paper 60 photo (live) | 1/20 recovered | 1.0 on the 1 matched | Tesseract segmentation fails on this two-column photo |
| Key region (live key) | whole-blob 0.9756/0.80/0.8791 → region **1.0/0.84/0.913** (84 TP, 0 FP) | | |
| Calibration (1,559 pairs) | ECE 0.0003 before AND after (identity — detectors already calibrated) | Below 1.0: UNVERIFIED (no samples) | |

Latency (VM): PPSC-66 single-path ~128 s, multi-pass
~358–403 s, TestPoint 21 s, table photo ~14 s, Paper 60
photo ~31 s. Memory: single PPSC-66 parse peaks at
398–461 MB tree RSS — **fits Render free's 512 MB with
~50 MB headroom (marginal)**. A long-lived worker
accumulates RSS (73 MB → 369 MB after one parse); no restart
policy is wired in Phase 1.

## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.x +
Alembic · PyMuPDF · OpenCV (headless) · Pillow · NumPy ·
Uvicorn · Supabase Python client · structured JSON logging ·
pytest · ruff · mypy.

## Quick start (local)

System dependency first — the Tesseract binary + language
data must exist (the engine shells out to it; the Python
packages alone are not enough). On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-urd tesseract-ocr-osd
tesseract --version   # expect 5.3.4; tesseract --list-langs must show eng, osd, urd
```

Lesson from M7: system packages are VM-ephemeral — a runtime
restart wiped tesseract from the dev VM mid-milestone. The
Docker image installs them itself (`Dockerfile`); never rely
on the host.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill in your own keys; never commit .env
uvicorn app.main:app --reload --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/version
```

Without Supabase env vars the app still starts; `/health`
reports `supabase: not_configured` (status `degraded`) and
authenticated endpoints answer 503 `auth_unavailable` until
Supabase is configured. Verified 2026-11-22 (M8, no env vars):
`/health` → 200 `{"status":"degraded", "checks":{"config":
"ok","supabase":"not_configured","database":
"not_configured","ocr_tesseract":"available","ocr_paddleocr":
"available","disk":"ok"}}`, `/version` →
`{"version":"0.1.0","git_commit":"1051fe4",...}`, and an
unauthenticated parse is 401.

## Tests and gates

```bash
.venv/bin/python -m pytest -q
# M8: 492 passed / 0 failed in ~9 min (489 M7 + 3 acceptance
# tests; the acceptance tests run real OCR on the three
# acceptance files, ~3 min of that total).

.venv/bin/python -m pytest --cov=app --cov-report=term-missing -q
# Coverage of the shipped code (tests excluded). See the M8
# report for the per-package figures and the untested areas.

.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app/db app/pipeline app/storage
# The CI gate. A broad `mypy app/` shows ~382 errors in
# app/tests/ + the pre-existing skeleton app/main.py — out of
# scope per pyproject.toml, not a regression.
```

Tests use an in-memory fake Supabase client — no network, no
live Supabase. The Tesseract tests run the real binary
(eng+urd); CI installs it (`.github/workflows/ci.yml`).

## Using the API

Full reference: `docs/API.md`. The short version:

```bash
# Synchronous parse (slow on scans — a 7-page PPSC-66 takes
# ~130 s on the dev VM; use async jobs for real traffic):
curl -X POST http://127.0.0.1:8000/api/v1/documents/parse \
  -H "Authorization: Bearer <user-jwt>" \
  -F "file=@ppsc_paper_66.pdf"

# A photo instead of a PDF:
curl -X POST http://127.0.0.1:8000/api/v1/documents/parse-image \
  -H "Authorization: Bearer <user-jwt>" \
  -F "file=@paper60.jpg"

# Async (recommended): submit, then poll.
curl -X POST http://127.0.0.1:8000/api/v1/async-jobs/parse \
  -H "Authorization: Bearer <user-jwt>" \
  -F "file=@ppsc_paper_66.pdf"
# -> 202 {"job_id": "...", "status": "queued", ...}
curl http://127.0.0.1:8000/api/v1/async-jobs/<job_id> \
  -H "Authorization: Bearer <user-jwt>"
# -> {"status": "completed", "result_summary": {"questions": 40, "answered": 40, ...}, "stages": [...]}

# Review queue + manual correction (top of the precedence chain):
curl http://127.0.0.1:8000/api/v1/jobs/<job_id>/review \
  -H "Authorization: Bearer <user-jwt>"
curl -X POST http://127.0.0.1:8000/api/v1/documents/<doc_id>/questions/<qid>/corrections \
  -H "Authorization: Bearer <user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"field": "answer", "new_value": "B", "reason": "verified against the key"}'
```

Every `/api/v1/*` endpoint needs a Supabase JWT; another
user's job/document is a 404, never a leak. Oversize files
are 422 `file_too_large`; bad input is 422, never 500.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | yes (for auth) | e.g. `https://gliebuyyjguxrwdfuakz.supabase.co` |
| `SUPABASE_ANON_KEY` | yes (for auth) | Publishable key; used to verify user JWTs |
| `SUPABASE_SERVICE_ROLE_KEY` | yes (for job writes) | **Server-side only.** Never in the Flutter app, never in a response, never logged |
| `DATABASE_URL` | no | SQLAlchemy URL for the engine-owned tables (Alembic). Without it the API still serves; stage history is logged, not persisted |
| `STORAGE_BACKEND` | no | `local` (only backend in Phase 1) |
| `STORAGE_ROOT` | no | Default `var/storage` |
| `ENVIRONMENT` | no | `development` / `staging` / `production` |
| `PORT` | no | Default `8000` |
| `RATE_LIMIT_REGISTER_PER_MINUTE` | no | Default 10 |
| `RATE_LIMIT_RETRY_PER_MINUTE` | no | Default 5 |
| `DEPLOYMENT_PROFILE` | no | `local` / `render-free` / `vps`. Default `local`. PaddleOCR is never selected below a 4 GB budget |
| `PADDLEOCR_ENABLED` | no | Default `true`; `false` on Render free (belt and braces) |
| `WORKER_ENABLED` | no | Default `false`. `true` on Render (in-process worker, ADR-009) |
| `WORKER_STAGE_TIMEOUT_SECONDS` | no | Default 600. **1800 on Render** — a 7-page OCR stage is ~20 min at 0.1 CPU |
| `TESSERACT_TIMEOUT_SECONDS` | no | Default 300 (per-page; a hung page fails per-page, never hangs a job) |
| `RENDER_DPI` / `TESSERACT_PSM` | no | Defaults 200 / 3. 200 DPI is the measured sweet spot; 150 DPI was rejected (loses 5 recovered questions) |
| `GEMINI_ADVISORY_ENABLED` | no | Default `false`. Needs `GEMINI_API_KEY` + `GEMINI_MAX_CALLS_PER_DAY` > 0 to do anything — none provisioned in Phase 1 |

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
2. Alembic revisions `0001_m1_engine_tables` + `0002_m3_layout_column`
   create the engine-owned tables. Apply AFTER 015, with
   `DATABASE_URL` set: `alembic upgrade head`. Reversible:
   `alembic downgrade base`. Local up/down is tested on SQLite
   (see `app/tests/test_schema.py`); Postgres-only behaviour (RLS,
   bucket) is verified only by the Dashboard queries in
   `docs/migration-015-apply.md`.

## Deploy (Render free tier, Stage 1) — NOT deployed yet

Full procedure: `docs/deploy-render.md` (+ `render.yaml`
blueprint). Summary: the owner connects the GitHub repo
`hasankhan62742-beep/officerpath-pdf-engine` (branch
`officerpath-phase1-engine`) to Render as a Docker web service on the
**Free** plan, sets the env vars from the table above in the Render
Dashboard, and deploys. Health check path is `/health`.

Cloud Run is PARKED (ADR-001): GCP billing is paused after 3–4
rejected cards, and Cloud Run needs a billing account even inside the
free tier. Do not create any GCP resource in Phase 1.

**Blockers (need the user, in his own browser):**

1. GitHub App install + push (the repo exists but is still empty
   on GitHub — code is local until pushed).
2. Migration 015 applied live (see above).
3. Render account + repo connection (free tier; if Render asks for
   a card at signup, stop and report — do not enter payment details).
4. Live phone verification on the three acceptance files (the
   Phase 1 STOP CONDITION — no milestone is "done live" until the
   owner's phone proves it).

Keep-alive decision: **deferred** (ADR-001). Render free sleeps after
15 min idle (~30–60 s wake). No keep-alive ping is configured.

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

## Security rules

- No secrets in code, in the repo, in logs, or in API responses.
  `.env.example` has placeholders only. Secrets grep: 0 offenders
  in 101 shipped `.py` files (M7, re-verified M8).
- The service-role key is used server-side only, from env vars.
- Auth is verified by Supabase Auth itself (`auth.get_user`); tokens
  are never decoded locally with a hardcoded secret.
- Ownership is enforced on every endpoint; other users' jobs answer
  404, never leak existence.
- This backend never writes `profiles.plan` / `premium_until` /
  `is_admin`, never touches `activation_codes` or `payments`, and
  never grants Premium. Quota (Phase 1B) is a convenience limit, not
  an entitlement control.
- The Gemini-advisory adapter is disabled by default (flag + key +
  nonzero budget all required). No Gemini API calls have ever been
  made.

## Flutter toggle (prepare-only, NOT shipped)

`~/workspace/officerpath-ai/` (no `.git` locally, so no branch
exists — the changes are uncommitted files, intended branch
`officerpath-server-parse-toggle`): `lib/services/
server_parse_service.dart` (new), toggle wiring in
`lib/services/pdf_import_service.dart` (`importPdf` and
`importImage` route to the server when ON), SwitchListTile in
`lib/screens/ai_settings_screen.dart` (default OFF, with a
not-deployed-yet warning). Any server failure throws
`ServerParseException` — never a silent fallback to another
parser. Server URL default:
`https://officerpath-pdf-engine.onrender.com` — **not deployed
yet**. No APK, no release, no version bump. `flutter analyze`
could NOT be run on the VM (no Flutter/Dart SDK) — the owner
must run it before review.

## Project layout

```
app/
  main.py            FastAPI app, middleware, error handlers
  config.py          Settings (env only)
  api/health.py      GET /health, GET /version
  api/metrics.py     GET /metrics (Prometheus-style)
  api/v1/routes.py   register, upload (single + batch), jobs
  api/v1/review.py   sync parse, parse-image, review, corrections, report
  api/v1/async_jobs.py  async parse, status, cancel, retry
  core/errors.py     Structured error model
  database/          Supabase clients + repositories (documents, jobs)
  db/                SQLAlchemy models + session (ADR-003)
  integrations/      Supabase Auth verify, Storage signed URLs
  pipeline/          OCR (M3), layout (M3), extract (M4),
                     answers (M5), matching (M6)
  schemas/           Pydantic v2 request/response models
  security/          Auth dependency, in-memory rate limiter
  services/jobs.py   Register / status / retry business rules
  storage/           StorageBackend interface + local-disk impl
  workers/           processor.py + runner.py (M7, ADR-009)
  utils/logging.py   Structured JSON logging (secrets redacted)
  utils/metrics.py   Prometheus-style counters
  tests/             pytest suite (fake Supabase client, no network)
alembic/             Alembic env + revisions (0001, 0002)
supabase/migrations/015_documents_jobs.sql   (NOT applied live)
  015_documents_jobs_down.sql  (reversal)
docs/                audit, ADRs, API, deploy + migration guides,
                     milestone + benchmark reports, completion report
scripts/             benchmark_m2..m8.py + measurement scripts
render.yaml          Render Blueprint (Stage 1, free tier)
Dockerfile  .github/workflows/ci.yml  requirements.txt
```

## What Phase 1 does NOT do

- No live deployment, no live phone verification (STOP
  CONDITION unmet — everything above is local/VM-measured).
- No Gemini OCR (key deferred by the owner; advisory only,
  disabled).
- No worker restart policy / per-job subprocess isolation
  (long-lived worker RSS accumulates).
- No page-parallel OCR, no 150 DPI (both measured and
  rejected), no TestPoint FP fix (28 left deliberately).
- Paper 60 live recovery is 1/20 via Tesseract — it needs
  Gemini-vision OCR or better segmentation (Phase 2).

The Gemini server key is deferred by the owner ("baad ki bat
hai") — do not keep asking for it. No paid AI or infrastructure
is provisioned without his explicit approval.
