# OfficerPath AI — Phase 1 Milestone 1 Report

- **Date:** 2026-11-21 (PKT, Asia/Karachi)
- **Milestone:** M1 — Project structure, config, DB schema, migrations, ingestion, validation, storage (Ultimate numbering M0–M8)
- **Gate (audit §10):** Upload works end to end (local + staging); malformed files rejected with reasons; migrations up/down pass on a copy of realistic data; `GET /health` healthy against staging Supabase.
- **Evidence labels:** **VERIFIED** (executed and observed) · **ASSUMED** (reasonable, untested) · **UNVERIFIED** (code exists, not run) · **UNKNOWN** (needs research/access).

## 1. Objective

Implement M1 on the approved baseline (ADR-001 Render free Stage 1,
ADR-002 hybrid OCR — both APPROVED by the owner 2026-11-21 17:03 PKT):
link the GitHub repo + create branch `officerpath-phase1-engine`,
build the §14 schema with SQLAlchemy 2.x + Alembic, build ingestion +
validation + storage, reconcile migration 015, add lint/typecheck/
secret-scan/dependency-audit to CI, rewrite deploy docs for Render.
No OCR/extraction logic (M2–M5), no live Supabase changes, no deploys,
no paid services, no Gemini key.

## 2. Implemented (files changed)

New modules (all in `~/workspace/officerpath-pdf-engine`):

- `app/db/models.py` — SQLAlchemy 2.x models for the full §14 schema
  (17 tables: `documents`/`jobs` mirrored from 015 + 15 engine-owned).
- `app/db/session.py` — lazy engine/session factory (small pool:
  pool_size=2, max_overflow=2 — Render 512 MB / Supabase free caps).
- `alembic/` — `alembic.ini`, `env.py` (URL from `DATABASE_URL` env
  only), `script.py.mako`, `versions/0001_m1_engine_tables.py`
  (15 new tables; does NOT create documents/jobs).
- `app/pipeline/interfaces.py` — plugin Protocols (`OCREngine`,
  `LayoutAnalyzer`, `QuestionDetector`, `OptionDetector`,
  `AnswerSourceDetector`, `Matcher`, `ConfidenceScorer`,
  `AIAssistProvider`) + `StageRegistry` + pipeline state machine with
  an allowed-transition table (`can_transition`).
- `app/pipeline/ingestion/validator.py` — extension + magic-byte
  checks, size/page/dimension/pixel limits, PDF structure checks
  (encrypted → rejected, never bypassed; truncation detected),
  image dimension/DPI/rotation parsing (stdlib only), decompression
  guard (absolute pixel cap rejects; high ratio is a warning).
- `app/pipeline/ingestion/classifier.py` — per-page classification
  (digital/scanned/mixed/unknown; byte-heuristic in M1, exact in M2).
- `app/pipeline/ingestion/service.py` — validate → SHA-256 dedup →
  store → register → stage history; batch with per-file results.
- `app/storage/base.py` + `app/storage/local.py` — `StorageBackend`
  protocol + write-once local-disk implementation (safe generated
  names, traversal protection, temp-file + rename).
- `app/api/v1/routes.py` — `POST /documents/upload` (single) and
  `POST /documents/upload/batch` (≤20 files); `FileType` gains
  `webp`/`tiff`/`tif`; `DocumentRegisterRequest` gains `content_hash`.
- `app/database/repositories.py` — `find_by_user_and_sha256` (dedup).
- `app/services/jobs.py` — persists `content_hash` on register.
- `app/config.py` — `database_url`, `storage_backend`/`storage_root`,
  ingestion limits (`max_image_pixels` 25 MP, `max_decompression_ratio`
  warning threshold 100); `request.state.request_id` is now the
  pipeline correlation id (`app/main.py` middleware).
- `docs/adr/ADR-003-persistence.md` — SQLAlchemy + Alembic decision.
- `docs/deploy-render.md` + `render.yaml` — Render free Stage 1
  (keep-alive decision: DEFERRED, recorded explicitly).
- `docs/migration-015-apply.md` — exact Dashboard steps + verification
  queries for 015; `supabase/migrations/015_documents_jobs_down.sql`.
- `.github/workflows/ci.yml` — ruff, mypy, pip-audit, detect-secrets,
  Alembic up/down on SQLite, Docker build; triggers on `main` +
  `officerpath-phase1-engine`. `pyproject.toml` (ruff/mypy config),
  `.secrets.baseline` (0 findings), `.env.example`, `.gitignore`.
- `README.md`, `Dockerfile`, `CHANGELOG.md` updated (Render, M1 scope).

Changed pre-existing files (small, reviewed): `requirements.txt`
(FastAPI 0.165.0, python-multipart 0.0.34 — pip-audit-driven),
`requirements-dev.txt` (pytest 9.0.3, ruff, mypy, pip-audit),
`supabase/migrations/015_documents_jobs.sql` (webp/tiff, content_hash
+ unique index, bucket MIME types — still unapplied, safe to edit),
`app/security/rate_limit.py` + `app/main.py` (Cloud Run → Render
comments), `app/integrations/supabase_auth.py` (`raise ... from err`),
`app/utils/logging.py` + `app/database/repositories.py` (type
annotations for mypy), `app/tests/test_security.py` (context manager).

Tests added (47 new): `test_ingestion.py` (validator + classifier),
`test_storage.py`, `test_schema.py` (models + Alembic up/down on
SQLite + state machine), `test_upload.py` (upload/batch API).

## 3. Verified (commands + results, all executed 2026-11-21)

- **Baseline first:** `.venv/bin/python -m pytest -q` → **22 passed**
  before any M1 change (reproduces M0).
- **Full suite after M1:** `pytest -q` → **69 passed, 0 failed**
  (22 pre-existing + 47 new), 5 warnings (pre-existing Starlette/
  gotrue deprecations + Alembic path_separator note).
- **Ruff:** `ruff check .` → All checks passed; `ruff format --check .`
  → 50 files already formatted. (Adoption found + fixed 30 issues:
  19 line-length, imports, unused imports, `datetime.UTC`, B904,
  SIM115 — including 6 in pre-existing files.)
- **Mypy:** `mypy app/db app/pipeline app/storage` → **no issues found
  in 12 source files**.
- **pip-audit:** first run found **14 vulnerabilities** in 3 packages
  (starlette 0.41.3 ×8, python-multipart 0.0.20 ×6, pytest 8.3.4 ×1).
  Upgraded FastAPI 0.115.6 → 0.165.0, python-multipart → 0.0.34,
  pytest → 9.0.3; suite stayed green; re-audit → **No known
  vulnerabilities found**.
- **Alembic (CLI, SQLite):** `alembic upgrade head` → `0001_m1_engine_tables
  (head)`; `alembic downgrade base`; `upgrade head` again → head;
  18 tables present (17 models + `alembic_version`). Same up/down is
  covered by `test_schema.py`.
- **Boot smoke (uvicorn, port 8125, no Supabase env):** `GET /health`
  → 200 `{"status":"degraded","checks":{"config":"ok","supabase":
  "not_configured"}}` (honest, expected); `GET /version` → 200;
  `GET /docs` → 200; unauthenticated `POST /documents/upload` → 401.
  Cold start took ~13 s on this VM (import time — noted for Render).
- **Secret scan:** `detect-secrets` baseline + scoped scan →
  **0 findings**; secret-pattern grep (`sbp_`/`sk-`/`AIza`/`eyJ…`) →
  **0 matches**; no `.env` file exists; no files under `var/`.
- **GitHub checks (live, public API, no auth):**
  - `officerpath-pdf-engine`: public, size 0, default branch `main`,
    created 2026-11-20, **still empty** (rechecked immediately before
    the push attempt; pushed_at unchanged).
  - `officerpath-ai` `admin/` listing contains `config.example.js`
    but NOT `config.js` → the M0 audit §8.2 finding is **RESOLVED**:
    `config.js` is NOT tracked on GitHub. Local `admin/.gitignore`
    also lists `config.js` (the M0 audit had read only the root
    `.gitignore`). No push to `officerpath-ai` was made or needed.
  - GitHub App identity verified (`get_me`): hasankhan62742-beep /
    Muhammad Abdul Qadeer.

## 4. Not verified / limitations

- **GitHub push FAILED (blocking, see §5).** The code is committed
  LOCALLY on branch `officerpath-phase1-engine` (commit `9a584f0`)
  but the remote repo is still empty. CI has therefore never run
  (no repo content → no Actions runs); the Docker build step is
  verified by CI config only, NOT RUN locally (no Docker on the VM).
- **Migration 015 NOT applied live** (needs the owner's separate
  go-ahead; the VM has no SQL access). Live RLS/bucket behaviour is
  unverified; only the Dashboard queries in
  `docs/migration-015-apply.md` verify it after applying.
- **Alembic tested on SQLite only** (no local Postgres/Docker).
  Postgres-only behaviour (RLS, `gen_random_uuid()`, bucket,
  CHECK-constraint rewrites) is NOT verified locally — labelled in
  the migration doc and in `test_schema.py`.
- **M1 gate "healthy against staging Supabase" is NOT met** — it
  needs 015 applied + env vars + a deployed service; all three are
  owner steps (see §7).
- Per-page classification is a **byte heuristic** in M1 (compressed
  PDF streams yield `unknown`, recorded honestly); exact
  classification is M2 (PyMuPDF). Skew/blur/noise/contrast are
  recorded as not-measured in M1 (need OpenCV, M2).
- Upload reads the whole file into memory (100 MB cap); streaming
  upload is M7 work. `var/storage` is ephemeral on Render — the
  durable home for originals is the Supabase bucket.
- Pre-existing cosmetic wart (not changed): the 401 message literally
  reads "A valid Bearer <redacted> is required." (Phase 1A copy).
- FastAPI was upgraded 0.115.6 → 0.165.0 for the pip-audit fix; the
  suite + boot smoke pass, but it is a larger jump than a patch bump
  — CI's first run should be watched for regressions.

## 5. Risks and decisions

- **Push failure — exact error (VERIFIED):** `github push-files`
  (owner-approved at call time) returned:
  `failed to initialize repository: failed to create initial file:
  PUT https://api.github.com/repos/hasankhan62742-beep/officerpath-pdf-engine/contents/README.md:
  403 Resource not accessible by integration`.
  Cause: the Muse GitHub App is not installed on
  `officerpath-pdf-engine` (it covers `officerpath-ai` only — same
  scoping as the earlier PAT). **No workaround was attempted** (no new
  credentials, no `gh auth login`, no PAT in git commands), per the
  M1 task constraints. The repo was rechecked afterwards: still empty
  (size 0), no partial push.
- **Fix (owner step):** open
  `https://github.com/apps/meta-muse-ai/installations/new` and add
  `officerpath-pdf-engine` to the Muse GitHub App installation (or
  install the app on that repo). Then re-run the push — exact
  commands for the owner are in §7. The local commit already exists,
  so the push is a plain `git push` once access is granted; no code
  needs re-doing.
- **Decisions owed by the owner:** (1) add the repo to the GitHub App
  installation (or push from his own machine); (2) separate go-ahead
  to apply migration 015 live (Dashboard); (3) Render deploy steps
  in his browser (after 1 + 2). The Gemini server key stays deferred
  — nothing in M1 needs it.
- **Risk:** two migration systems now exist (Supabase SQL 015 +
  Alembic 0001). Deliberate split, documented in ADR-003; apply order
  (015 first) is enforced by FKs + docs. Consolidation is a
  post-Phase-1 cleanup, not M1 work.

## 6. Existing app status

Unaffected — **VERIFIED**: no file under `~/workspace/officerpath-ai`
was modified in M1 (only read: `admin/.gitignore` + the public GitHub
API listing for the config.js check). No live Supabase data, tables,
or buckets were touched; no GCP resources; no paid services; no
Gemini key. The Flutter app's 22 pre-existing engine tests still
pass, plus 47 new ones.

## 7. Next step (one clear action)

**Owner: add `officerpath-pdf-engine` to the Muse GitHub App
installation** at `https://github.com/apps/meta-muse-ai/installations/new`,
then run (from the repo directory, branch already checked out):

```bash
cd ~/workspace/officerpath-pdf-engine
git remote add origin https://github.com/hasankhan62742-beep/officerpath-pdf-engine.git
git push -u origin officerpath-phase1-engine
```

(If he prefers to push from his own machine instead: copy the repo
directory, then the same two commands.) After the push, CI runs
automatically; then the owner applies migration 015 via
`docs/migration-015-apply.md` and follows `docs/deploy-render.md`.
That sequence unblocks M2.

## M1 gate verdict: PARTIALLY MET

- **Met:** project structure, SQLAlchemy + Alembic §14 schema,
  ingestion + validation + storage, upload works end to end
  **locally** (69 tests, live boot smoke), malformed files rejected
  with machine-readable reasons, migrations up/down pass locally
  (SQLite), CI gates defined + green locally, deploy docs rewritten.
- **Not met:** "healthy against staging Supabase" — needs migration
  015 applied live + a deployed service, both owner steps; and the
  GitHub push is blocked on the App-installation fix above, so CI
  has never run on GitHub. These are access/approval blockers, not
  code failures: no M1 code needs re-doing once they clear.
