# ADR-009: Background jobs — in-process worker, jobs table as the queue

- **Status:** ACCEPTED (M7, 2026-11-22)
- **Context:** M7 needed an async job pipeline (queued →
  processing → done/failed, stage progress, retry, cancel,
  timeouts) on the existing M1 schema. The Stage-1 deploy target
  is Render free: ONE instance, 0.1 CPU, 512 MB RAM, no
  persistent service beyond the web process itself. Any design
  that needs a second paid service (Redis, a managed queue, a
  second dyno) contradicts ADR-001's Stage-1 shape.
- **Decision:** the jobs table IS the queue; the worker is
  in-process.
  - `app/workers/processor.py`: `claim_next_job` claims atomically
    (`UPDATE … WHERE status='queued'` — the loser gets nothing,
    so two workers can never process the same job);
    `process_job` loads stored bytes, runs the parse with an
    `on_stage` hook per phase boundary, records a stage row per
    phase with its duration, and persists the matched document.
  - `app/workers/runner.py`: `run_once` / `run_forever` / CLI
    (`python -m app.workers.runner [--once]`) — a separate worker
    process for the VPS stage.
  - The API starts the worker as an `asyncio.to_thread` task in
    lifespan ONLY when `worker_enabled=true` (default False — an
    API-only deploy runs no worker unless opted in).
  - Per-stage timeout: `worker_stage_timeout_seconds` (default
    600 s, cumulative per stage). A job that exceeds it fails
    with the stage named (`StageTimeout`), never left hanging.
    Tesseract gets its own per-page timeout
    (`tesseract_timeout_seconds`, default 300 s), so a hung page
    fails per-page instead of hanging a job.
  - Cancel: a cancel request sets
    `Job.result_summary["cancel_requested"]` — the flag lives in
    JSON because the jobs table is owned by migration 015, not
    Alembic, so no column can be added. The worker checks the
    flag at every stage boundary; a cancelled job is recorded
    `cancelled`, never `failed`.
  - Failure isolation extends the M2 principle from pages to
    stages: one bad stage fails that job with a recorded reason;
    a failed job is retryable (re-queue, `retry_count` +1).
- **Evidence (measured, M7 benchmark):** the job-pipeline proof
  runs the real HTTP + worker path on CA40: queued → done with
  stage timings; a corrupt PDF fails with the reason recorded,
  retry with good bytes completes the same job (40 questions);
  cancel of a queued job records `cancelled` (second cancel
  409); cancel of a processing job records `cancelled` at the
  first stage boundary. Full numbers in
  `docs/benchmarks/m7-benchmark-2026-11-22.json` (`job_pipeline`).
- **Rationale:** no new dependency, no new service, no new cost
  — the design fits the one-instance Stage-1 shape exactly. The
  atomic claim is the only concurrency primitive needed, and the
  database already provides it. The timeout/cancel semantics are
  deliberately boring: a named failure beats a hung job, and a
  cancel is not a failure.
- **Consequences:**
  - The in-process worker shares the API process's CPU and RAM.
    A scanned-book parse is ~120 s of Tesseract on this VM
    (1.5 CPUs) and ~10× that on Render free's 0.1 CPU — during
    it the API stays responsive (worker runs in a thread) but
    CPU-starved. One parse at a time is the realistic Render-free
    shape; the API never blocks on a parse.
  - `worker_stage_timeout_seconds` (600 s) is TOO SHORT for a
    7-page OCR stage on Render free: the OCR stage alone is
    ~120 s on this VM and would be ~20 min at 0.1 CPU. Deploying
    to Render free MUST raise the timeout (or accept failed
    jobs). This is a deployment-config note, not a code default
    change — 600 s is right for the VM and the VPS.
  - A long-lived worker process retains RSS across parses
    (measured: a fresh process is 73 MB at baseline, 369 MB at
    the end of one PPSC-66 parse, 289 MB after gc + malloc_trim).
    No restart policy or per-job subprocess isolation is wired
    in M7 — that is VPS-stage work (see the M7 report).
  - `/metrics` is unauthenticated BY DESIGN (aggregate counters
    only, no user content). If any future metric ever carries
    user content, it must gain auth first.
- **Alternatives considered:**
  - Redis / Celery / a managed queue: rejected — a new paid
    dependency and a second service to operate, for a queue the
    database already implements. Revisit only if the worker
    ever needs to scale past one instance.
  - Separate worker process as the ONLY mode: rejected for
    Stage 1 (Render free runs one process); kept as the VPS
    option via the runner CLI.
  - Thread-per-job: rejected — unbounded threads on 512 MB.
  - Adding a `cancel_requested` column: rejected — the jobs
    table is owned by migration 015 (live Supabase), not
    Alembic; a JSON flag in `result_summary` needs no migration.
