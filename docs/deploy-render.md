# Deploy — Render free tier, Stage 1 (M1, ADR-001)

**Status (2026-11-21): NOT deployed.** This document is the procedure
for the owner. No agent provisions or deploys anything; the deploy
happens in the owner's Render account, in his browser, after the
GitHub repo is linked (M1) and migration 015 is applied (Dashboard).

This replaces the old Cloud Run deploy docs. Cloud Run is PARKED:
GCP billing is paused after 3–4 rejected cards, and Cloud Run needs a
billing account even inside the free tier. Do not create any GCP
resource in Phase 1.

## What Render free gives (verified 2026-11-21)

- Docker web service, 512 MB RAM, 0.1 CPU, 750 instance-hours/month
  (covers one service running ~continuously).
- Spins down after 15 min without traffic; ~30–60 s cold start to wake.
- No credit card required for standard free services — with the known
  caveat that some users report being asked for a card at signup (not
  100% guaranteed). **If Render asks for a card, stop and report to
  the owner before entering any payment details.**
- Filesystem is ephemeral: files written to local disk disappear on
  restart/redeploy. Local storage (`var/storage`) is therefore a
  development default only — the durable home for originals is the
  Supabase `pdf-documents` bucket (migration 015).
- Free tier docs say "do not use them for production applications":
  Stage 1 is a staging/proof tier, not production. Stage 2 is the
  Hostinger KVM 1 VPS (ADR-001).

## Consequences for the engine (design constraints)

- 512 MB / 0.1 CPU rules out heavy in-process OCR (PaddleOCR full
  pipeline, Tesseract on large pages) as a routine path — see ADR-002.
  Stage-1 OCR is Gemini-vision (network-bound) when a server key
  exists, PaddleOCR/Tesseract as fallback.
- M3 MEASURED (2026-11-21, VM 4 vCPU / 8 GB — see
  docs/benchmarks/BENCHMARK_M3_2026-11-21.md): PaddleOCR 3.7
  (PP-OCRv5, ONNX engine) peaks at 1.8–3.7 GB RSS per page and
  OOM-kills (exit 137) on 2160×3840 phone photos — it CANNOT run in
  the 512 MB Render free container, full stop. Tesseract 5.3.4 peaks
  at 229 MB and ~13 s/page on the VM (much slower on 0.1 CPU, not
  measured). So on Render free the only viable OCR paths are
  Gemini-vision (needs the server key) and Tesseract; PaddleOCR
  belongs on the Hostinger VPS (Stage 2, 4 GB) or not at all. The
  Docker image still ships the Tesseract binary + language data;
  PaddleOCR stays an optional dependency (requirements.txt note).
- One service only within the quota; Render Background Workers are
  not free. Stage-1 background work must run in-process (a worker
  loop inside the web container) — M7 designs this.
- Performance targets are set against 0.1 CPU / 512 MB, not the dev
  VM (4 vCPU / 8 GB). Benchmarks run on the VM must be labelled so.

## Deploy steps (owner, browser)

1. Push the repo: `officerpath-phase1-engine` branch must exist on
   GitHub (M1 git-link step; exact commands in the M1 report).
2. Render Dashboard → **New → Web Service** → connect the GitHub
   repo `hasankhan62742-beep/officerpath-pdf-engine` → branch
   `officerpath-phase1-engine`. Or **New → Blueprint** and point it
   at `render.yaml` in the repo (same result; the blueprint file is
   the reviewed, committed form of these steps).
3. Confirm the plan is **Free** and the runtime is **Docker**.
4. Set env vars in the Dashboard (never in the repo):
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `DATABASE_URL` (Supabase Postgres URL for Alembic tables),
   `ENVIRONMENT=production`. `PORT` is set by Render automatically;
   the Dockerfile honours `${PORT}`.
5. Deploy. Render builds the Docker image and starts it.
6. Verify:
   ```bash
   curl https://<service-url>/health
   # Expect 200 {"status":"ok", ...} once 015 + env vars are set;
   # "degraded" with supabase: not_configured before the env vars.
   curl https://<service-url>/version
   ```

## Keep-alive decision (ADR-001): DEFERRED

Render free sleeps after 15 min idle. A keep-alive ping (e.g. an
uptime monitor hitting `/health` every few minutes) would prevent
sleep but consumes instance-hours and can mask real outages. **No
keep-alive ping is configured in M1.** The owner decides explicitly
in M6/M7; until then the first request after idle is simply slow
(~30–60 s). This is recorded here so the absence is a decision, not
an oversight.

## Rollback

Every Render deploy keeps the previous image. Dashboard → service →
**Rollback** restores the previous deploy with no rebuild. Rollback
restores code + config, not external state (Supabase data, secrets
changed since). Database rollback is the Alembic/015 down paths in
`docs/migration-015-apply.md` — only after confirming no jobs depend
on them.

## Stage 2 (later, not now)

Hostinger KVM 1 VPS (4 GB RAM, root, Docker, Mumbai DC) when payment
is possible. The same Docker image moves to the VPS with a worker
process and a queue (M7 design must already allow this). No purchase
or provisioning in Phase 1.
