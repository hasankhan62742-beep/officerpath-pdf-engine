# ADR-011: Dual job-store resolution — engine DB is the single access path; vocabulary unified on `done`

- **Status:** ACCEPTED (M3, 2026-11-22)
- **Context:** M1 (doc 01 §2.2) found two job stores: the M1
  register/upload flow writes Supabase `public.jobs` via PostgREST
  with terminal status `done`, while the M6/M7 review + async-jobs
  flow writes the SQLAlchemy engine DB with terminal status
  `completed`. M1 recommended Option A (engine DB as single source
  of truth) and deferred the decision to M3. M3 re-examined the
  code independently and found the split is worse than M1 stated,
  in two ways.
- **Finding 1 — one database, two access paths, one hard conflict.**
  The engine DB is not a second database: `DATABASE_URL` is the
  SQLAlchemy URL for the SAME Postgres Supabase hosts
  (`app/config.py:44-50`), and the SQLAlchemy `Document`/`Job`
  models MIRROR `public.documents`/`public.jobs`
  (`app/db/models.py:54-60` — Alembic 0001 deliberately does NOT
  create them; migration 015 does). In production both access
  paths hit the same rows. The conflict is therefore not only a
  frontend polling inconvenience: the live `public.jobs` table
  carries the 015 check constraint
  `status IN ('queued','uploading','processing','done','failed',
  'cancelled')`, and Postgres enforces it no matter which path
  writes. The engine writes `completed`
  (`app/workers/processor.py:222`, `app/api/v1/review.py:117`),
  which the constraint rejects. Consequences, traced in code
  (never run against live Postgres — no deploy exists — so this
  is code-reading, not a live measurement):
  - Async worker: `process_job` sets `completed` and commits;
    the commit raises `IntegrityError`; the `except Exception`
    handler calls `_fail_job`, whose own commit raises
    `PendingRollbackError` (the session was never rolled back),
    so the job is left stuck in `processing` forever and
    `run_forever` just logs the failure and moves on. Every
    async job would parse fully and then never complete.
  - Sync parse: `_persist_parse` failure is caught, the session
    is rolled back, and the parse returns `persisted: false`
    with a note (`app/api/v1/review.py`). Graceful, but review /
    corrections / reports would find nothing.
  - In short: with the M7 vocabulary, the engine cannot complete
    a single job against the live database. The vocabulary fix
    is not cosmetic; it is a production correctness fix.
- **Finding 2 — live state corrected.** M0/M1 recorded migration
  015 as "written, not applied live". M3 re-verified live on
  2026-11-22 (anon-key PostgREST probes with a 404 control for a
  nonexistent table): `public.documents` and `public.jobs` DO
  exist live (HTTP 200, empty for anon — consistent with the
  owner-only RLS policies), as do all 001–014 tables. But the
  `pdf-documents` bucket does NOT exist
  (`GET /storage/v1/bucket/pdf-documents` → 404 `NoSuchBucket`).
  So 015 was applied partially, or its tables were created
  another way and the bucket step never ran. The bucket is now
  migration 016 (written in M3, NOT applied — owner step).
  RLS on/off could not be proven directly (Management API token
  lacks `database_read`; anon reads return 0 rows everywhere,
  which is consistent with RLS on but also with empty tables).
- **Decision:**
  - The engine DB (SQLAlchemy) is the SINGLE access path for
    documents + jobs. `POST /documents/register`,
    `POST /documents/upload`, `POST /documents/upload/batch`,
    `GET /jobs/{id}`, `POST /jobs/{id}/retry` now read/write
    the engine DB through new SQLAlchemy repositories
    (`app/database/sqlalchemy_repositories.py`) that implement
    the same dict-based interface the PostgREST repositories
    had, so `app/services/jobs.py` and
    `app/pipeline/ingestion/service.py` are unchanged in logic.
    `GET /api/v1/jobs/{id}` and `GET /api/v1/async-jobs/{id}`
    now read the same row from the same table: one job id,
    one status, visible from both endpoints (proven by test).
  - The vocabulary is unified on **`done`** — the term the live
    check constraint, the `JobStatus` enum
    (`app/schemas/documents.py:25-31`), and every processing
    stage status already use. The engine changes: `completed`
    → `done` in `processor.py` (status write, summary,
    metric), `review.py:117`, `app/utils/metrics.py` docstring
    example, and the M7 worker tests. The `PipelineStage.
    COMPLETED` stage NAME is unchanged — it names a stage, not
    a job status (stage rows already carry `status="done"`).
  - `app/database/repositories.py` (PostgREST) is DELETED. The
    Supabase clients stay — auth verification
    (`auth.get_user`) still uses the anon client — but no API
    endpoint writes documents/jobs through PostgREST anymore.
    The conftest fake keeps its auth emulation (all tests use
    it); its table emulation is removed with the module.
  - The engine now REQUIRES `DATABASE_URL` for the
    document/job endpoints (503 `database_unavailable`
    otherwise, the same as async-jobs already did). The
    PostgREST-only degraded mode (engine without a database)
    is RETIRED: every other document/job endpoint already
    required the database, so one endpoint on a different
    path bought complexity, not availability.
  - Register-source jobs are marked at creation
    (`result_summary: {"source": "register"}`) and the worker's
    `claim_next_job` skips them until M4 wires bucket download.
    Register bytes live in the bucket, not on local disk, so
    claiming one would fail it with "no stored bytes"
    (`processor.py`). Upload-source jobs
    (`{"source": "upload"}`, bytes on local disk) ARE claimable
    — that is new behaviour (previously invisible to the
    worker) and intended: an uploaded file can now actually be
    processed. The claim filter is a JSON predicate on
    `result_summary["source"]` (NULL/absent = claimable);
    SQLite behaviour is tested, Postgres behaviour is reasoned
    from the same predicate and must be re-verified before any
    deploy (M10).
  - Supabase migration 016 (`supabase/migrations/
    016_pdf_documents_bucket.sql`, written, NOT applied) creates
    only the missing `pdf-documents` bucket + its three storage
    policies (idempotent guards). It does NOT touch the jobs
    check constraint — no longer needed, the engine now writes
    `done`. The `done` value stays in the constraint for any
    legacy rows.
- **Rejected alternatives:**
  - Option B (read-side union view merging both stores, doc 03
    §5): keeps two writers, two ownership models (RLS vs
    code-level 404s), and two test backends; the union would
    have to reconcile the same row appearing in both stores.
    Rejected — the stores were never two databases, so a union
    solves a problem that does not exist once the access path
    is single.
  - Keep `completed` and alter the live constraint via a new
    migration: leaves production broken until the owner applies
    it, and rewrites the term the schema, the enum, and every
    stage status already use. Rejected — `done` is the
    established vocabulary; the engine was the outlier.
  - Dual-write (write both stores): two truths again, with
    failure modes between the writes. Rejected.
  - Keep the PostgREST path and only fix the vocabulary: the
    vocabulary fix is necessary but not sufficient — the two
    access paths would still diverge in ownership enforcement
    and test backends, and the unification could not be proven
    locally (fake Supabase vs SQLite). Rejected as the final
    state; the single-path move is the same size once the
    repositories share one interface.
- **Evidence (measured, M3):**
  - Live probes 2026-11-22: project `ACTIVE_HEALTHY`,
    `ap-southeast-1`, Postgres 17.12; GoTrue v2.198.0 healthy;
    `documents`/`jobs`/all 001–014 tables HTTP 200 via
    PostgREST (control: nonexistent table → 404 PGRST205);
    `pdf-documents` bucket 404 `NoSuchBucket`; 5 Edge Functions
    ACTIVE. Management API token lacks `auth_config_read`,
    `database_read`, `api_gateway_keys_read` (403s) — auth
    settings and RLS on/off are UNVERIFIED by direct read.
  - Code: `done` as a JOB status occurred in exactly 3 places
    (`schemas/documents.py:29`, `repositories.py:16`,
    `tests/test_jobs.py:68`); every other `"done"` in the codebase
    is a processing-STAGE status and is untouched.
    `completed` as a job status occurred in `processor.py`
    (write + summary + metric), `review.py:117`, and the M7
    worker tests.
  - Tests (M3): register → `GET /jobs/{id}` →
    `GET /async-jobs/{id}` all see the same job id/status;
    claim skips a register-source job and claims an
    upload-source job; full engine gates re-run (numbers in the
    M3 milestone report).
- **Consequences:**
  - `docs/API.md` and `docs/phase2/02-api-integration-map.md`
    updated: register/upload/get/retry are engine-DB endpoints;
    the terminal job status is `done`; GAP-11 is resolved in M3
    (the unified job/document view is the single store, not a
    new endpoint).
  - The Phase 1 completion report's state machine
    (`queued → processing → completed …`) is now stale for the
    terminal value; the report is a historical record and is
    NOT rewritten — this ADR is the correction. M4 docs must
    use `done`.
  - No live client consumed the `completed` value: the Flutter
    toggle calls sync parse/parse-image only, and the web
    frontend does not exist yet. No migration of live data is
    needed: the live `public.jobs` table is (almost certainly)
    empty — the engine was never deployed and no register call
    has ever run against live — and the constraint keeps `done`
    valid for any legacy row.
  - The per-call commit shape of the old repositories is kept
    (a document created without its job on a mid-request crash
    is possible, as before — same as the M1 wart; a single
    transaction across both creates is M4 follow-up, not M3).
  - The SQLAlchemy `Job`/`Document` models still mirror tables
    Alembic does not create; that split is unchanged (015 owns
    the DDL, Alembic owns the rest).
