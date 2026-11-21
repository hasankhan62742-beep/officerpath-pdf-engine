# TEST REPORT — officerpath-pdf-engine, Phase 1A

**Date:** 2026-11-20 (PKT) · **Version:** 0.1.0 · **Runner:** pytest 8.3.4,
Python 3.12.3, local venv (`.venv/`), no network, fake in-memory Supabase
client (`app/tests/conftest.py`).

## Local results: 22 passed, 0 failed

Run: `python -m pytest -q` → `22 passed in 0.21s` (run 2026-11-20 ~22:20 PKT).
Live server proof (uvicorn, port 8123, no Supabase env):
`GET /health` → 200 `{"status":"degraded","checks":{"config":"ok","supabase":"not_configured"}}`;
`GET /version` → 200; unauthenticated `POST /api/v1/documents/register` → 401.
With Supabase pointed at an unreachable URL: `GET /health` → **503**
`{"supabase":"unreachable"}` (honest failure path verified).

## Acceptance tests from the Phase 1A prompt

| # | Acceptance test | Result | Evidence |
|---|---|---|---|
| 1 | `GET /health` verifies app health (config present, Supabase reachable when configured), no secrets, 200/503 honestly | **PASS** | `test_health.py` (3 tests): health ok with fake Supabase; no secret material in body; plus live uvicorn proofs above (200 degraded when unconfigured, 503 when unreachable) |
| 2 | `GET /version` — version + git commit if available + environment | **PASS** | `test_version.py` in `test_health.py`: version `0.1.0`, environment present, `git_commit` null here (no git repo on this VM) — accepted as null, never an error |
| 3 | Live Cloud Run health check | **BLOCKED** | No GitHub repo exists yet; no billing account linked (user decision pending); nothing deployed to Cloud Run. Cannot be run until the repo + billing blockers clear. |
| 4 | `POST /documents/register` — authenticated, validates input, creates document + durable job, ownership enforced, idempotent | **PASS** | `test_register.py` (9 tests): success creates document+job (201); no/invalid token → 401; validation errors (bad type, >100 MB, >100 pages, missing title) → 422; other user's folder → 403; same idempotency key → same job (200, replay flag); same path without key → same job; same key different user → separate jobs |
| 5 | Live Flutter → backend register flow | **BLOCKED** | No live backend to call (see #3); no Flutter changes made in this phase by design. Needs a deployed service + the Phase 1A app change (upload screen "Server parse" option, not built here). |
| 6 | `GET /jobs/{job_id}` — owner-only (404 for others, never leaks existence) | **PASS** | `test_jobs.py`: owner 200; other user 404; unknown id 404; no auth 401 |
| 7 | `POST /jobs/{job_id}/retry` — owner-only, only failed/cancelled, increments retry count, rate-limited | **PASS** | `test_jobs.py`: queued/done → 409 `job_not_retryable`; failed → 200, status `queued`, retry_count 1; cancelled → 200; other user → 404; 6th retry in a minute → 429 `rate_limited` |
| 8 | Live Supabase flows (migration 015 applied, RLS enforced live, bucket policies live) | **BLOCKED** | Migration `015_documents_jobs.sql` is written but **not applied** — applying needs the owner's go-ahead via the coordinator (VM has no SQL access). RLS/bucket behaviour is therefore file-reviewed only, not live-verified. |
| 9 | No secret leakage in any response | **PASS** | `test_security.py`: planted fake secret values in env, asserted absent from every endpoint response (health, version, register, 404s, validation errors); `.env.example` contains placeholders only (`your-*-key-here`, no `sbp_` / `eyJ`) |
| 10 | All pytest tests pass locally before reporting | **PASS** | 22 passed, 0 failed (see above) |

## What was NOT tested live (honest gaps)

- **Docker image build** — no Docker on this VM. The Dockerfile is
  validated only by the CI workflow file (`.github/workflows/ci.yml`),
  which cannot run until a GitHub repo exists.
- **Real Supabase** — no live calls were made; the fake client covers
  the exact chained calls the repositories use (`table/select/insert/
  update/eq/limit/execute`, `auth.get_user`), but live RLS, the
  `unique(user_id, storage_path)` / `unique(user_id, idempotency_key)`
  constraints, and storage policies are unverified until migration 015
  is applied and smoke-tested.
- **Rate limiting** is in-memory per process (documented in README);
  multi-replica behaviour is untested by design (max-instances=1).
- **OCR / parsing** — explicitly out of scope for Phase 1A (Phase 1B).

## Test files

- `app/tests/conftest.py` — fake Supabase client + TestClient fixture
- `app/tests/test_health.py` — health + version (3 tests)
- `app/tests/test_register.py` — register: auth, validation, ownership, idempotency (9 tests)
- `app/tests/test_jobs.py` — job status, retry state machine, rate limit (8 tests)
- `app/tests/test_security.py` — secret leakage, structured errors, `.env.example` hygiene (2 tests... plus 1 env-example check = 3; total suite 22)
