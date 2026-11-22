# Deploy — Render free tier, Stage 1 (M8, ADR-001)

**Status (2026-11-22, M8): NOT deployed.** This document is the
procedure for the owner. No agent provisions or deploys anything;
the deploy happens in the owner's Render account, in his browser,
after the GitHub repo is linked and migration 015 is applied
(Dashboard). The guide was verified against the actual M8 code:
every env var below exists in `app/config.py`, the start command
is the Dockerfile `CMD`, the health path is `render.yaml`'s
`healthCheckPath`, and the memory numbers are the M7/M8
measurements (VM numbers, labelled so).

Cloud Run is PARKED: GCP billing is paused after 3–4 rejected
cards, and Cloud Run needs a billing account even inside the
free tier. Do not create any GCP resource in Phase 1.

## What Render free gives (verified 2026-11-21)

- Docker web service, 512 MB RAM, 0.1 CPU, 750
  instance-hours/month (covers one service running
  ~continuously).
- Spins down after 15 min without traffic; ~30–60 s cold start
  to wake.
- No credit card required for standard free services — with the
  known caveat that some users report being asked for a card at
  signup (not 100% guaranteed). **If Render asks for a card,
  stop and report to the owner before entering any payment
  details.**
- Filesystem is ephemeral: files written to local disk disappear
  on restart/redeploy. Local storage (`var/storage`) is
  therefore a development default only — the durable home for
  originals is the Supabase `pdf-documents` bucket (migration
  015).
- Free tier docs say "do not use them for production
  applications": Stage 1 is a staging/proof tier, not
  production. Stage 2 is the Hostinger KVM 1 VPS (ADR-001).

## What actually runs on Render free (measured, M7/M8)

- **OCR path:** digital text first; scanned pages go through
  **Tesseract 5.3.4 (eng+urd, 200 DPI, PSM 3)** — the only OCR
  engine that fits 512 MB. PaddleOCR is gated off on this
  profile (ADR-006; M3 measured peak 1,775–3,667 MB — it OOMs
  in this container, full stop). There is **no Gemini-vision
  OCR adapter** in Phase 1: Gemini is advisory-only, disabled
  by default, and no server key is provisioned (the owner's
  decision, "baad ki bat"). Do not expect a Gemini OCR path on
  Render until Phase 2 provisions one.
- **Memory (M7 measured, M8 re-measured):** a single PPSC-66
  parse peaks at 398–461 MB tree RSS — it **fits 512 MB with
  ~50 MB headroom (marginal)**. One parse at a time on Render
  free. A long-lived worker accumulates RSS across parses (73
  MB baseline → 369 MB after one parse; `gc` + `malloc_trim`
  returns ~79 MB, never back to baseline) — **no restart
  policy is wired in Phase 1**; a worker restart policy is
  VPS-stage work.
- **Time (M7 measured):** PPSC-66 single-path ~128 s on the
  dev VM (1.5 CPUs); Tesseract is ~93% of that. At Render
  free's 0.1 CPU the same 7-page OCR stage is estimated at
  ~20 min (not measured on Render — an estimate, labelled so).
  That is why `WORKER_STAGE_TIMEOUT_SECONDS` is 1800 s in
  `render.yaml` (the 600 s code default would fail every long
  job). Sync `POST /api/v1/documents/parse` calls are not
  subject to that timeout, but a ~20 min HTTP request is not a
  sane client pattern — long work belongs in the async job
  model (`POST /api/v1/async-jobs/parse` → poll).
- **Background work:** the in-process worker (M7, ADR-009)
  runs inside the web container when `WORKER_ENABLED=true`
  (set in `render.yaml`). Render Background Workers are not
  free — there is no separate worker service in Stage 1.
- **Docker:** the image was verified by config only — **no
  Docker on the dev VM, so no image was ever built or run
  here**. The first CI Docker build after the push verifies
  it. The Dockerfile installs the Tesseract binary + language
  data (`tesseract-ocr`, `eng`, `urd`, `ara`, `osd`) — the
  exact set the M7 suite passes against — because system
  packages are VM-ephemeral (M7 incident: a runtime restart
  wiped tesseract from the VM; the deploy must install it in
  the image, never rely on the host).

## Deploy steps (owner, browser)

1. **GitHub App install** (owner step, M1): add the repo at
   https://github.com/apps/meta-muse-ai/installations/new,
   then push from the VM:
   `git push -u origin officerpath-phase1-engine` (from
   `~/workspace/officerpath-pdf-engine`). Until then the repo
   on GitHub is empty and CI has never run.
2. **Migration 015** (owner step, M1): apply
   `supabase/migrations/015_documents_jobs.sql` via the
   Supabase Dashboard → SQL Editor — exact steps + verification
   queries in `docs/migration-015-apply.md`. Then, with
   `DATABASE_URL` set, `alembic upgrade head` (the Alembic
   revisions ship in the Docker image). Until 015 is applied,
   `/health` truthfully reports `database: not_configured`
   and status `degraded`.
3. Render Dashboard → **New → Web Service** → connect the
   GitHub repo `hasankhan62742-beep/officerpath-pdf-engine` →
   branch `officerpath-phase1-engine`. Or **New → Blueprint**
   and point it at `render.yaml` in the repo (same result; the
   blueprint file is the reviewed, committed form of these
   steps, including `WORKER_ENABLED=true` and
   `WORKER_STAGE_TIMEOUT_SECONDS=1800`).
4. Confirm the plan is **Free** and the runtime is **Docker**.
5. Set env vars in the Dashboard (never in the repo):
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (Supabase
   Postgres URL for Alembic tables), `ENVIRONMENT=production`.
   `PORT` is set by Render automatically; the Dockerfile
   honours `${PORT}`. The remaining vars already have their
   Render values in `render.yaml` (`DEPLOYMENT_PROFILE=
   render-free`, `PADDLEOCR_ENABLED=false`,
   `WORKER_ENABLED=true`, `WORKER_STAGE_TIMEOUT_SECONDS=1800`,
   `TESSERACT_TIMEOUT_SECONDS=300`).
6. Deploy. Render builds the Docker image and starts it with
   `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}`.
7. Verify:
   ```bash
   curl https://<service-url>/health
   # Expect 200 {"status":"ok", ...} once 015 + env vars are set;
   # "degraded" with database: not_configured before that (honest,
   # not a failure). ocr_tesseract must read "available".
   curl https://<service-url>/version
   # Expect {"version":"0.1.0", "git_commit":"<sha>", ...}
   curl https://<service-url>/metrics
   # Prometheus text; counters appear on first event.
   ```
8. **Smoke test (owner, his phone — the STOP CONDITION):**
   upload the PPSC-66 PDF and the two acceptance photos
   through the Flutter "Server parse" toggle (M6/M7,
   prepare-only, default OFF) or `curl` the parse endpoints
   (`docs/API.md`). Expect: PPSC-66 41 questions / 41
   answered, table photo 0 questions / 2 pending, Paper 60
   4 questions / 4 answered. These are the M7/M8 VM numbers;
   the phone test is the live verification Phase 1 still
   lacks.

## Keep-alive decision (ADR-001): STILL DEFERRED (M8)

Render free sleeps after 15 min idle. A keep-alive ping (e.g.
an uptime monitor hitting `/health` every few minutes) would
prevent sleep but consumes instance-hours and can mask real
outages. **No keep-alive ping is configured.** M6/M7 did not
decide this; it is still deferred to the owner. Until then the
first request after idle is simply slow (~30–60 s). This is
recorded here so the absence is a decision, not an oversight.

## Rollback

Every Render deploy keeps the previous image. Dashboard →
service → **Rollback** restores the previous deploy with no
rebuild. Rollback restores code + config, not external state
(Supabase data, secrets changed since). Database rollback is
the Alembic/015 down paths in `docs/migration-015-apply.md` —
only after confirming no jobs depend on them.

## Stage 2 (later, not now)

Hostinger KVM 1 VPS (4 GB RAM, root, Docker, Mumbai DC) when
payment is possible. The same Docker image moves to the VPS
with a separate worker process (`python -m
app.workers.runner`) and the queue it already supports (M7
design). On the VPS: PaddleOCR becomes usable (4 GB budget),
the worker restart policy and per-job subprocess isolation
(unbuilt in Phase 1) get wired, and the rate limiter needs a
distributed replacement before running more than one replica.
No purchase or provisioning in Phase 1.
