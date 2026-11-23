# Workstream D — Render Backend Deployment Readiness

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream D subagent (local inspection + local measurements; no Render service created, no live Supabase touched, no money spent)
**Scope:** `render.yaml` (Blueprint), Dockerfile, app startup + health + CORS + worker behaviour under the Render-free profile, the memory-fit question, secrets handling, cold start / sleep, deployment steps, smoke tests, failure modes and rollback.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Every number in §3 comes from a measurement run in this workstream, with the command shown in the appendix. M7/M8 figures quoted for comparison are cited as *reported* (from `docs/benchmarks/BENCHMARK_M7_2026-11-22.md` and `BENCHMARK_M8_2026-11-22.md`), not re-verified beyond the two re-runs in §3. Render free-tier limits are taken from the repo's own verification (ADR-001, web-verified 2026-11-21) and were re-checked against current public sources on 2026-11-23 (§2) — the figures agree. No Render deploy exists yet, so deployment itself is PENDING and nothing in this report claims a live Render check.

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` (Workstream A), `docs/deployment/02-github-ci-report.md` (Workstream B), `docs/deployment/03-supabase-migration-runbook.md` (Workstream C), `docs/phase2/deployment-checklists.md` (§A), `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `docs/deploy-render.md`, `docs/phase2/rollback-runbook.md`, `docs/adr/ADR-001-hosting-baseline.md`, `ADR-005-ocr-engine-evaluation.md`, `ADR-006-deployment-aware-ocr-routing.md`, `ADR-009-in-process-background-worker.md`.

---

## 1. Service configuration (Blueprint) — VERIFIED (file read in full)

File: `render.yaml`. One service, Docker runtime, plan `free`, repo `hasankhan62742-beep/officerpath-pdf-engine`, branch `officerpath-phase2-web` (fixed in M10 — was `officerpath-phase1-engine`), `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health`.

| Env var | Value in `render.yaml` | Purpose / what it proves |
|---|---|---|
| `ENVIRONMENT` | `production` | App runs in production mode |
| `PORT` | `8000` | Render overrides this automatically; the Dockerfile honours `${PORT}` |
| `DEPLOYMENT_PROFILE` | `render-free` | 512 MB memory budget; PaddleOCR excluded by the router (ADR-006) |
| `PADDLEOCR_ENABLED` | `"false"` | Belt-and-braces: the package is not even registered (see §3.4) |
| `WORKER_ENABLED` | `"true"` | In-process background worker runs inside the web container (ADR-009; Background Workers are not free) |
| `WORKER_STAGE_TIMEOUT_SECONDS` | `"1800"` | 30 min per worker stage — the 600 s code default would fail every 7-page job at 0.1 CPU (§3.5) |
| `TESSERACT_TIMEOUT_SECONDS` | `"300"` | Per-page Tesseract timeout (code default, made explicit) |
| `SUPABASE_URL` | `sync: false` | Secret — set in the Render Dashboard, never in the repo (§4) |
| `SUPABASE_ANON_KEY` | `sync: false` | Secret — Dashboard only (§4) |
| `SUPABASE_SERVICE_ROLE_KEY` | `sync: false` | Secret — Dashboard only, server-side only (§4) |
| `DATABASE_URL` | `sync: false` | Secret — Supabase Postgres URL for Alembic tables + the worker (§4) |

The file's own header states it provisions nothing until the owner connects the repo to Render — that is correct. No paid plan is referenced anywhere in the file.

**Dockerfile — VERIFIED (config only, see the caveat):** multi-stage `python:3.12-slim`, venv in the builder, non-root `appuser` in the runtime stage, Tesseract binary + language data installed in the image (`tesseract-ocr`, `eng`, `urd`, `ara`, `osd` — the exact set the M7 suite passes against), `HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3` on `/health`, `CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]`. Alembic migrations ship in the image (`COPY alembic ./alembic`, `alembic.ini`) so `alembic upgrade head` can run at deploy time. **Caveat (unchanged since M1): the Dockerfile has never been built anywhere — no Docker on this VM. The first CI `docker-build` job (Workstream B §4) is the verification; do not treat the image as proven until that job is green.** The Dockerfile itself says the same thing in its header.

---

## 2. What Render free gives — VERIFIED (repo + current public sources)

| Fact | Source |
|---|---|
| Docker web service, **512 MB RAM, 0.1 CPU** | ADR-001 (web-verified 21 Nov 2026); re-checked 23 Nov 2026 against current public sources (Render's own articles + independent 2026 free-tier comparisons) — all agree |
| **750 instance-hours/month** per workspace (covers one service running ~continuously) | Same as above |
| **Spins down after 15 min without inbound traffic; ~30–60 s cold start** to wake (about a minute per current sources) | Same as above |
| **No credit card required** for standard free web services — with the known caveat that some users report being asked for a card at signup (not 100% guaranteed) | ADR-001; if Render asks for a card, **stop and report to the owner before entering any payment details** |
| Filesystem is **ephemeral** (lost on restart/redeploy) | ADR-001; §5.2 for what this means for uploads |
| Free tier docs say **"do not use them for production applications"** — Stage 1 is a staging/proof tier, not production | ADR-001 |
| Free services **cannot scale past one instance, attach a disk, open a shell, or run one-off jobs**; Render may restart them at any time | Current public sources, 23 Nov 2026 |
| Free-tier **bandwidth is 5 GB/month** (cut from 100 GB in April 2026 per one current source) — the repo does not mention bandwidth; the beta's traffic is far below this, but it is a real limit to know | Current public sources, 23 Nov 2026 |
| Free services **cannot send outbound mail on ports 25/465/587** | Current public sources — no effect on this project: notifications are in-app only, never email (M9) |

No Render Postgres is used (it expires after ~30 days); the database is Supabase (Workstream C).

---

## 3. Memory-fit investigation — the central question

### 3.1 Method (re-run in this workstream)

The M7/M8 method, unchanged: `scripts/m7_tree_rss.py` parses the PPSC-66 fixture (`ppsc_paper_66.pdf`, md5 `0cd49fedff8ee83d620da29c729817d1`) in a **fresh process** and samples the concurrent tree RSS (Python parent + live tesseract children) every 100 ms. Environment for both runs: `DEPLOYMENT_PROFILE=render-free PADDLEOCR_ENABLED=false`, tesseract 5.3.4 (ara/eng/osd/urd), this VM (4 vCPUs visible, 8 GB RAM — shared cell, 1.5 CPUs). Accuracy is part of the measurement: a run that does not reproduce the M7 answers is not a valid memory reading.

### 3.2 Results measured in this workstream

| Run | Time | Questions / answered | Baseline parent RSS | Peak parent RSS | Peak live-children RSS | **Peak tree RSS** | Parent RSS at end | After `gc` + `malloc_trim` |
|---|---|---|---|---|---|---|---|---|
| Single-path | 114.1 s | 41 / 41 | 73 MB | 417 MB | 93 MB | **460 MB** | 369 MB | 290 MB |
| Multi-pass | 353.9 s | 62 / 62 | 73 MB | 373 MB | 96 MB | **464 MB** | 311 MB | 232 MB |

Both runs reproduce the M7 accuracy exactly (41/41 single, 62/62 multi-pass). Largest single tesseract child high-water: 422 MB (single) / 390 MB (multi).

### 3.3 Verdict: MARGINAL — CONFIRMED, not corrected

| Figure | Value |
|---|---|
| Worst tree peak observed (all runs, M7 + M8 + this workstream) | **465 MB** (M8 multi-pass) |
| This workstream's worst | **464 MB** (multi-pass); single-path 460 MB |
| Render free limit | 512 MB |
| **Headroom** | **47 MB** |

The M10 checklist figure (~47 MB headroom) is **correct and reproduced**: my worst run (464 MB) sits 1 MB below the M8 worst (465 MB), and my single-path run (460 MB) is actually *higher* than M8's single-path (441 MB) — the band across runs is 441–465 MB, so the headroom is 47–71 MB depending on the run, and the safe planning number is the worst case: **47 MB**. The verdict stands: **one PPSC-66 parse fits 512 MB, marginally, one parse at a time.** Two concurrent parses, or one parse plus a second heavy operation in the same container, have never been measured and must be assumed to OOM.

### 3.4 What the numbers do NOT prove (limits of this measurement)

- **VM numbers are NOT Render numbers.** The VM has 4 visible vCPUs and 8 GB RAM; Render free has 0.1 CPU and 512 MB. CPU contention changes latency, not memory (M8 §0), so the RSS band is the transferable part — but the container's *total* memory is not just the parse tree: on Render the same 512 MB must also hold the uvicorn process, the in-process worker thread, and any concurrent request handling. My parse-tree runs were fresh standalone processes, **not** inside the server process.
- **The combined server peak was not measured.** I measured the server's idle baseline separately (§6): 152 MB RSS at startup with the render-free profile and the worker running. A parse *inside* that server process would add the parse tree on top of a live server — that combined peak is unmeasured and is the first thing to watch on the live deploy (Render's memory graph + the OOM signature in §12).
- **Only the PPSC-66 fixture was re-measured.** The two acceptance photos (computer table, Paper 60) were measured in M7/M8 (294–370 MB) and are well inside the budget; they were not re-run here because the worst case is the 7-page PPSC-66 parse.
- **Long-lived accumulation was reproduced, not re-measured across parses.** In both my runs the parent never returns to its 73 MB baseline (369 → 290 MB after `gc` + `malloc_trim` single-path; 311 → 232 MB multi-pass) — the same M7 finding (73 → 369 → 289 MB). A long-lived worker therefore accumulates RSS across parses. **No restart policy is wired** — that remains VPS-stage work (M7/M8, unchanged).

### 3.5 PaddleOCR is gated three ways — VERIFIED

1. **Profile budget:** `app/pipeline/ocr/deployment.py` — `render-free` budget is 512 MB; `PADDLEOCR_MIN_MEMORY_MB = 4096` (M3 measured peak 1,775–3,667 MB). `paddleocr_allowed` is False on this profile, with a human-readable exclusion reason.
2. **Flag:** `PADDLEOCR_ENABLED=false` in `render.yaml` — the registry never registers it (`app/pipeline/ocr/registry.py`, `service.py`).
3. **Health:** `/health` reports `ocr_paddleocr: "disabled"` under this profile (observed live in §6).

An unknown profile name raises `ValueError` at startup (fail loudly, no silent wrong budget). PaddleOCR cannot run on Render free, full stop — VPS-only (ADR-005).

### 3.6 CPU and time — the 0.1 CPU consequence

M7 measured PPSC-66 single-path at ~128 s on this VM (1.5 CPUs); my re-run took 114.1 s. At Render free's 0.1 CPU the same 7-page OCR stage is **estimated at ~20 min** — an estimate from the VM ratio, **not measured on Render**, labelled as such in `render.yaml` and `docs/deploy-render.md`. That is why `WORKER_STAGE_TIMEOUT_SECONDS` is 1800 s in `render.yaml` (the 600 s code default would fail every long job). Sync `POST /api/v1/documents/parse` calls are not subject to that timeout, but a ~20 min HTTP request is not a sane client pattern — long work belongs in the async job model (`POST /api/v1/async-jobs/parse` → poll). Tesseract is ~93% of the parse time (M7 profile), so the bottleneck is OCR, not the pipeline.

---

## 4. Environment and secrets — VERIFIED

| Secret (`sync: false` in `render.yaml`) | Set by | Used for |
|---|---|---|
| `SUPABASE_URL` | Owner, Render Dashboard | Supabase client (anon + service-role) |
| `SUPABASE_ANON_KEY` | Owner, Render Dashboard | Supabase client |
| `SUPABASE_SERVICE_ROLE_KEY` | Owner, Render Dashboard | Server-side Supabase client only (`app/database/supabase_client.py`) — bucket downloads and admin operations |
| `DATABASE_URL` | Owner, Render Dashboard | SQLAlchemy engine (Alembic tables) + the in-process worker's job polling |

- **No secret value is in the repo.** Workstream A (secrets scan) and Workstream B (detect-secrets, 3 hashed entries — all placeholders/test dummies) both verified this; this workstream re-confirmed the `render.yaml` entries are `sync: false` with no value.
- **The service-role key never reaches the frontend.** In `app/` it appears only in `app/config.py` (the setting), `app/database/supabase_client.py` (server-side client), and `app/main.py:77` — which logs/reports only the **boolean** `service_role_configured`, never the value. In `web/` the only `service_role` matches are inside `node_modules` (third-party Supabase SDK code), not app code; no `.env` file is tracked under `web/`. The web app authenticates with the **anon** key only (`NEXT_PUBLIC_SUPABASE_ANON_KEY`).
- **The service starts without the secrets** and `/health` reports `degraded` until they are set — that is the honest behaviour documented in `render.yaml`, not a failure (§6 observed it live: `supabase: not_configured`, status `degraded`, HTTP 200).
- **`DATABASE_URL` is required for the worker.** Without it the worker logs `worker not started: DATABASE_URL is not configured` and async jobs never run (`app/main.py` lifespan). With it, the worker starts as a lifespan background task (§7).

---

## 5. Two gaps found in this workstream

### 5.1 NEW — `CORS_ALLOWED_ORIGINS` is missing from `render.yaml` — REQUIRES OWNER APPROVAL

`app/config.py:57` defaults `cors_allowed_origins` to `http://localhost:3000`, and `render.yaml` sets **no** `CORS_ALLOWED_ORIGINS` at all. The web frontend calls the API **from the browser**: the dashboard pages are `"use client"` components importing `web/lib/api.ts`, which fetches `NEXT_PUBLIC_API_URL` directly. `app/main.py` applies `CORSMiddleware` with `allow_credentials=True` and an exact origin list — never `*` (M9 final CORS).

**Consequence:** on Render, the API would accept only `http://localhost:3000` as a cross-origin caller, so the production Vercel frontend would be **blocked by CORS** (browser preflight failure) until the origin is set. This is not a code bug — it is a missing deployment value. The value cannot be written into `render.yaml` yet because the canonical production origin is **unconfirmed** (Workstream E's domain decision; the placeholder `officerpath.ai` is not confirmed owned). **Action (owner step, in the Render Dashboard):** set `CORS_ALLOWED_ORIGINS` to the exact production frontend origin once Workstream E settles it — and to the Vercel preview/production URL in the meantime if the beta uses one. Do not set it to `*` (credentials would break and M9's exact-origin rule would be violated). The deploy steps in §10 include this; `docs/deploy-render.md` step 5 does **not** list it (see §5.3).

### 5.2 Uploads on Render land on ephemeral disk — operational caveat (not a blocker)

The web upload endpoints (`POST /api/v1/documents/upload`, `/batch`) store bytes via `LocalDiskStorage(settings.storage_root)` — `var/storage` on the container's ephemeral filesystem (`app/api/v1/routes.py`, `app/api/v1/documents.py`; `storage_backend` defaults to `local` and any other value returns 503 `storage_unavailable`). The Supabase `pdf-documents` bucket is the durable home only for **register-source** documents: the worker downloads them once into local storage as a write-once cache before parsing (`app/workers/processor.py`).

**Consequence:** a web-uploaded file's stored bytes are lost on a Render restart/redeploy. The parsed results (questions, answers, test sessions) live in Supabase Postgres and survive; only the stored original bytes (and re-parseability without re-upload) are lost. For the 20–30 student beta this is acceptable, but it must be stated: **Render free is not a durable file store for web uploads.** The durable-originals work (upload-to-bucket from the web app) is a later improvement, not part of this deploy. The deployment-checklist item C5 ("Production uploads go to the private `pdf-documents` bucket") describes the register flow, not the web upload endpoint — do not read it as covering both.

### 5.3 `docs/deploy-render.md` steps 1 and 3 still name the old branch — minor doc staleness

`docs/deploy-render.md` step 1 says `git push -u origin officerpath-phase1-engine` and step 3 says connect branch `officerpath-phase1-engine`. The push has already happened (to `officerpath-phase2-web`, 2026-11-23, head `461c9a2`) and `render.yaml` was fixed in M10 to `officerpath-phase2-web`. The owner must follow **§10 of this report**, not those two stale steps. (This report does not edit `deploy-render.md` — that file is out of this workstream's scope; the correction is recorded here so it is not followed by mistake.)

---

## 6. Health checks — VERIFIED (live local run)

`/health` contract (`app/api/health.py`): HTTP 200 when healthy; **503 when a CONFIGURED dependency (Supabase, database) is unreachable**; unconfigured dependencies report `not_configured` and the app is `degraded` (HTTP 200), never faking `ok`. Checks: `config`, `supabase` (a real `select id limit 1` on `documents`), `database` (`SELECT 1`), `ocr_tesseract` (binary on PATH), `ocr_paddleocr` (flag + profile gate), `disk` (free space under the storage root, low below 100 MB). No secret is ever included in a health response. `/version` returns service, version `0.1.0`, git commit, environment. `/metrics` returns real Prometheus counters (M8 re-verified).

**Live local run in this workstream** (uvicorn, render-free profile, `WORKER_ENABLED=true`, temp SQLite `DATABASE_URL`, no Supabase env — the exact Render shape minus Supabase):

```
$ curl http://127.0.0.1:8001/health
{"status":"degraded","service":"officerpath-pdf-engine","version":"0.1.0",
 "environment":"production",
 "checks":{"config":"ok","supabase":"not_configured","database":"ok",
 "ocr_tesseract":"available","ocr_paddleocr":"disabled","disk":"ok"}}
```

- `supabase: not_configured` is honest (no env vars set) — the same response Render will give until the secrets are set.
- `ocr_paddleocr: "disabled"` confirms the §3.5 gate end-to-end.
- The worker started in the same process (`"worker runner started", "poll_seconds": 5.0` in the log).
- **Startup RSS (uvicorn process, render-free profile, worker running): 152 MB** (`VmRSS 155,308 kB`, measured after startup + one `/health` call). That is the idle server baseline the parse tree sits on top of (§3.4).

Dockerfile `HEALTHCHECK` (30 s interval, 5 s timeout, 10 s start period, 3 retries) and `render.yaml` `healthCheckPath: /health` agree on the same endpoint.

---

## 7. Worker behaviour — VERIFIED (code + live local run)

- **In-process (ADR-009):** `WORKER_ENABLED=true` starts the worker as a lifespan background task inside the API process (`app/main.py` → `asyncio.to_thread(_run_worker_forever)` → `app/workers/runner.py:run_forever`). It polls the `jobs` table every 5 s (`worker_poll_seconds`), claims **one job at a time** (Render free is 0.1 CPU — parallelism would only thrash), and processes it synchronously in a thread, never on the event loop.
- **Standalone mode exists** for the VPS stage: `python -m app.workers.runner [--once]` — its own process, one job per run with `--once`. Not used on Render free (a second service is not free).
- **Failure handling:** each `run_once` opens a fresh session; a crashed worker leaves at most one `processing` job behind, re-claimable only by an explicit retry — never silently re-run, so a job is never processed twice by accident. A hung stage fails with the stage named (1800 s timeout); a hung Tesseract page fails per-page (300 s) instead of hanging the job.
- **OOM exposure:** the worker shares the web process's 512 MB. A parse peak inside the server process competes with the API itself — there is no separate memory budget, no restart policy, and no per-job subprocess isolation (all VPS-stage work). If the worker OOMs, the whole web service dies and Render restarts it (§12).
- **Live confirmation:** in the §6 local run the worker started and polled against the temp SQLite database; with no `DATABASE_URL` it logs `worker not started` and async jobs never run — the failure is visible in the log, not silent.

---

## 8. Gemini — disabled by default — VERIFIED

`app/config.py`: `gemini_advisory_enabled: bool = False`, `gemini_max_calls_per_day: int = 0` (0 = advisory disabled entirely), `gemini_api_key: str | None = None`. Enabling also needs a server key in the environment (`GEMINI_API_KEY` — never in code); with no key the provider reports disabled. There is no Gemini-vision OCR adapter in Phase 1: Gemini is advisory-only, suggestions only, never a verified answer. **No paid AI dependency exists in the core workflow**, and no Gemini key is provisioned (owner's decision, "baad ki bat"). Nothing in the Render deploy changes this.

---

## 9. Cold start, sleep, and keep-alive — VERIFIED

- Render free **spins down after 15 min without inbound traffic**; the next request takes **~30–60 s** to wake (repo) / about a minute (current sources, §2). The first request after idle is simply slow — and a slow first request can also look like a timeout to a browser client that is not expecting it (the web upload flow should surface this honestly, not silently retry).
- **Keep-alive: DEFERRED (ADR-001, owner decision pending).** A keep-alive ping (e.g. an uptime monitor hitting `/health` every few minutes) would prevent sleep but consumes instance-hours and can mask real outages. **No keep-alive ping is configured, and none is to be added** until the owner decides explicitly. The absence is a decision, not an oversight — recorded in `render.yaml`, ADR-001, and `docs/deploy-render.md` alike.
- **750 instance-hours/month covers one service running continuously**, so the hours budget is not the constraint — the sleep is.
- The in-process worker does **not** keep the service awake: it polls the database, which is not inbound HTTP traffic, so the service still sleeps after 15 min of no requests. A queued job therefore waits until the next inbound request wakes the service (or the owner adds keep-alive). This is a real operational consequence of the deferred decision: **async jobs submitted while the service sleeps do not start until something wakes it.**

---

## 10. Deployment steps (owner, Dashboard, in order)

Prerequisites (must already be true — see the other workstreams): GitHub push done (head `461c9a2`, 2026-11-23); Supabase migrations per Workstream C (015 live, 016 DONE, **018 → 017 re-run → Alembic 0001–0009** still pending); CI first run checked (Workstream B).

1. **Render Dashboard → New → Blueprint** and point it at `render.yaml` in the repo (preferred — the reviewed, committed form of these steps), or **New → Web Service** → connect repo `hasankhan62742-beep/officerpath-pdf-engine` → branch `officerpath-phase2-web`. (Do NOT use the stale branch name in `docs/deploy-render.md` steps 1/3 — §5.3.)
2. Confirm the plan is **Free** and the runtime is **Docker**. If Render asks for a card at signup, **stop and report to the owner** before entering any payment details (§2).
3. Set the four secrets in the Dashboard (never in the repo): `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (Supabase Postgres URL — the pooled/transaction URL the engine uses for Alembic tables; see Workstream C for which value).
4. **Set `CORS_ALLOWED_ORIGINS`** in the Dashboard to the exact production frontend origin once Workstream E settles it (§5.1). Until then the API will only accept `http://localhost:3000`.
5. Confirm the remaining vars already have their Render values in `render.yaml` (`DEPLOYMENT_PROFILE=render-free`, `PADDLEOCR_ENABLED=false`, `WORKER_ENABLED=true`, `WORKER_STAGE_TIMEOUT_SECONDS=1800`, `TESSERACT_TIMEOUT_SECONDS=300`, `ENVIRONMENT=production`).
6. Deploy. Render builds the Docker image and starts it with `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}`. **Watch the first CI `docker-build` job** — it is the first proof the Dockerfile actually builds (§1).
7. Verify (from the owner's machine):
   ```bash
   curl https://<service-url>/health
   # Expect 200 {"status":"ok", ...} once 015/016/017/018 + Alembic + env vars are set;
   # "degraded" with database/supabase: not_configured before that (honest, not a failure).
   # ocr_tesseract must read "available"; ocr_paddleocr must read "disabled".
   curl https://<service-url>/version
   # Expect {"version":"0.1.0", "git_commit":"<sha>", ...}
   curl https://<service-url>/metrics
   # Prometheus text; counters appear on first event.
   ```
8. **Run Alembic** (the revisions ship in the image; the CMD does not run them — checklist A10): from a machine with the live `DATABASE_URL`, `alembic upgrade head`, then verify `alembic_version` = 0009 (Workstream C §5). Until Alembic runs, the engine-owned tables do not exist and the worker cannot claim jobs.
9. **Smoke test (owner, his phone — the STOP CONDITION, Workstream F):** upload the PPSC-66 PDF and the two acceptance photos through the web upload. Expect the M7/M8 VM numbers (PPSC-66 41 questions / 41 answered; table photo 0 questions / 2 pending; Paper 60 4 questions / 4 answered). **Expect the first request after idle to take ~30–60 s** (cold start, §9) — and a 7-page OCR job to take on the order of ~20 min at 0.1 CPU (§3.6); use the async job model and poll, do not wait on a sync call.

---

## 11. Smoke-test checklist after deploy

| # | Check | Expect |
|---|---|---|
| S1 | `GET /health` | 200, `status: "ok"`, `ocr_tesseract: "available"`, `ocr_paddleocr: "disabled"` (once secrets + migrations are set) |
| S2 | `GET /version` | `0.1.0`, `git_commit` = the deployed commit (`461c9a2` or later) |
| S3 | `GET /metrics` | Prometheus text; counters appear on first event |
| S4 | Unauthenticated parse | 401 (M8 security proof, re-check live) |
| S5 | Oversize upload | 422 `file_too_large` |
| S6 | One async job (CA40 or a small PDF) | queued → done; stages visible; result matches the VM numbers |
| S7 | PPSC-66 through the web upload (owner phone) | 41 questions / 41 answered (STOP CONDITION evidence — Workstream F) |
| S8 | CORS from the production frontend origin | Browser preflight succeeds (only after §10 step 4 is done) |
| S9 | Render memory graph during S7 | No OOM kill; peak stays under 512 MB (watch §3.4's combined-peak caveat) |

---

## 12. Failure modes and rollback

| Failure | Signature | Response |
|---|---|---|
| **OOM kill (parse peak + server > 512 MB)** | Render log shows exit 137 / `Killed`; service restarts; the in-flight job stays `processing` until an explicit retry | Re-run the job; check the Render memory graph against §3.4. Do not raise the parse load — one parse at a time. If OOMs recur, the honest fix is the VPS stage (Stage 2), not tuning the free tier. |
| **Cold-start timeout** | First request after 15 min idle takes ~30–60 s; a browser client may time out first | Retry once after the wake; use the async job model for long work. Keep-alive is a separate owner decision (§9). |
| **Service asleep, job queued** | Job stays `queued` with no worker activity | Any inbound request wakes the service; the worker then claims the job. |
| **`degraded` health** | `supabase`/`database: not_configured` or `unreachable` | Not a failure before the secrets/migrations are set; after they are set, `unreachable` means the configured dependency is down (503). |
| **CORS failure** | Browser preflight rejected from the production origin | `CORS_ALLOWED_ORIGINS` not set (§5.1) — set it in the Dashboard. |
| **Docker build failure** | CI `docker-build` job red, or Render build log error | Fix the Dockerfile/requirements; the image has never been built before (§1). |

**Rollback:** Render Dashboard → service `officerpath-pdf-engine` → **Rollback** restores the previous deploy (previous Docker image + the env vars as they were at that deploy; free services keep rollbacks to the last two deploys per current sources). Verify after rollback: `GET /health` → 200, `GET /version` shows the PREVIOUS commit, unauthenticated parse → 401, one async job queued → done (rollback-runbook §2). The engine deploy is stateless (the database lives in Supabase, not on Render), so rolling back the service does NOT roll back any data — whether the database also needs rolling back is a separate decision (rollback-runbook §3; Alembic downgrades 0003–0009 exist, and 015/016/017/018 have down files).

**Branch switch after the PR:** `render.yaml` points at `officerpath-phase2-web`. After the Workstream B PR merges `officerpath-phase2-web` → `main`, the Render service's branch must be switched to `main` (Dashboard → service → Settings → Branch) and `render.yaml`'s `branch:` updated to `main` in a follow-up commit — **owner step, only after the first deploy from `officerpath-phase2-web` is verified.** Do not delete the `officerpath-phase2-web` branch until that first deploy from `main` is verified (Workstream B §3).

---

## 13. Open owner decisions — PENDING / REQUIRES OWNER APPROVAL

| # | Decision | Status | Who |
|---|---|---|---|
| D1 | Deploy the Render service at all (Blueprint, secrets, first deploy) | PENDING | Owner (Dashboard) |
| D2 | `CORS_ALLOWED_ORIGINS` value (depends on Workstream E's domain decision) | REQUIRES OWNER APPROVAL | Owner |
| D3 | Keep-alive pinger (yes/no) | REQUIRES OWNER APPROVAL — DEFERRED since ADR-001; no pinger until explicitly decided | Owner |
| D4 | Branch switch to `main` after the PR merges | PENDING — only after the first deploy from `officerpath-phase2-web` is verified | Owner |
| D5 | Worker restart policy / per-job subprocess isolation | PENDING — VPS-stage work (M7/M8); no policy is wired on Render free | Later (Stage 2) |
| D6 | Durable originals for web uploads (upload-to-bucket) | PENDING — later improvement; §5.2 caveat stands for the beta | Later |
| D7 | `npm audit` (owner machine) and the first CI run | PENDING — Workstream B §7; the CI `docker-build` job is also the first Dockerfile proof | Owner |

---

## Appendix — evidence (commands run in this workstream)

- `git log --oneline -3` → head `6c331f2` (Workstream C), branch `officerpath-phase2-web`; `git status --short` → only the two untracked 018 files (by design, Workstream C)
- `render.yaml` read in full (11 env vars incl. 4 `sync: false` secrets); `Dockerfile` read in full (multi-stage, `appuser`, Tesseract eng/urd/ara/osd, HEALTHCHECK on `/health`, CMD uvicorn)
- `grep -rn "CORS_ALLOWED_ORIGINS"` → only `app/config.py:57` (default `http://localhost:3000`), `app/main.py:253` (comment), M3/M9 reports — **not in `render.yaml`**
- `grep -rn "service_role" app/` (non-test) → `app/config.py:23,168-169`, `app/database/supabase_client.py:25,27`, `app/main.py:77` (boolean only); `web/` matches only inside `node_modules`
- `grep -rn "storage_backend"` → default `local` (`app/config.py:62`); non-local → 503 `storage_unavailable` (`app/api/v1/routes.py:54-59`, `documents.py:41-46`, `async_jobs.py:67-72`); bucket download only for register-source jobs (`app/workers/processor.py:228`)
- `app/pipeline/ocr/deployment.py` read in full: `PADDLEOCR_MIN_MEMORY_MB = 4096`, `PROFILE_MEMORY_BUDGET_MB = {"render-free": 512, "vps": 4096, "local": 8192}`, unknown profile raises `ValueError`
- `app/api/health.py` read in full: 200 degraded vs 503 contract, honest per-check reporting, no secrets in responses
- `app/main.py` lifespan + `app/workers/runner.py` read: in-process worker, one job at a time, poll 5 s, fresh session per job, explicit-retry only
- `app/config.py` read in full: Gemini disabled by default (`gemini_advisory_enabled: False`, `gemini_max_calls_per_day: 0`, `gemini_api_key: None`)
- Render free-tier re-check (web search, 2026-11-23): 512 MB / 0.1 CPU / 750 instance-hours / 15-min spin-down / ~1-min wake — agrees with ADR-001; bandwidth now 5 GB/month; free services cannot scale past one instance, attach a disk, open a shell, run one-off jobs, or send outbound mail on ports 25/465/587
- Temp SQLite DB for the server run: `DATABASE_URL="sqlite:////tmp/d-render-test.db" .venv/bin/alembic upgrade head` → lands on 0009; file removed after the run
- Server run (render-free profile): `ENVIRONMENT=production DEPLOYMENT_PROFILE=render-free PADDLEOCR_ENABLED=false WORKER_ENABLED=true WORKER_STAGE_TIMEOUT_SECONDS=1800 TESSERACT_TIMEOUT_SECONDS=300 DATABASE_URL="sqlite:////tmp/d-render-test.db" PORT=8001 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001` → `curl /health` → 200 `degraded` (`supabase: not_configured`, `database: ok`, `ocr_tesseract: available`, `ocr_paddleocr: disabled`, `disk: ok`); log shows `"worker runner started", "poll_seconds": 5.0`; uvicorn VmRSS **155,308 kB (≈152 MB)**; server stopped and temp files removed afterwards
- Tree-RSS single-path: `DEPLOYMENT_PROFILE=render-free PADDLEOCR_ENABLED=false .venv/bin/python scripts/m7_tree_rss.py` → baseline 73 MB; seconds=114.1; matched=41 answered=41; peak parent 417 MB; peak live-children 93 MB; **peak tree 460 MB**; largest child high-water 422 MB; parent at end 369 MB; after gc+malloc_trim 290 MB; ru_maxrss 422 MB
- Tree-RSS multi-pass: same command with `--multi-pass` → seconds=353.9; matched=62 answered=62; peak parent 373 MB; peak live-children 96 MB; **peak tree 464 MB**; largest child high-water 390 MB; parent at end 311 MB; after gc+malloc_trim 232 MB; ru_maxrss 390 MB
- Fixture: `~/workspace/officerpath-ai/test-fixtures/ppsc66/ppsc_paper_66.pdf`, md5 `0cd49fedff8ee83d620da29c729817d1`; tesseract 5.3.4, langs ara/eng/osd/urd

**Workstream D conclusion:** the Blueprint is sound and the PaddleOCR gate, health contract, worker design, and secrets handling all check out on inspection and on a live local run — but the Render-free fit is **confirmed MARGINAL (worst 465 MB vs 512 MB, 47 MB headroom)**, the Dockerfile has never been built, the service does not exist yet, and two gaps need owner action: **`CORS_ALLOWED_ORIGINS` is missing from `render.yaml`** (the production frontend would be blocked until it is set in the Dashboard) and **web uploads land on ephemeral disk** (register-source originals are safe in the bucket; web-uploaded bytes are not). Deployment itself remains PENDING.
