# Phase 2 M1 — Deployment Plan

**Date:** 2026-11-22
**Standing rule:** no deploy, no paid provisioning, no charges without
the owner's explicit approval. This doc is a plan, not a deployment.
Nothing in it provisions anything.

## 1. Principles

1. **Frontend and backend deploy independently.** The Next.js app and
   the FastAPI engine are separate services with separate repos paths
   (`web/` vs `app/`), separate build pipelines, and separate env
   config. Either can be redeployed without the other, as long as the
   API contract (doc 02) is honoured.
2. **Keep the Phase 1 decisions unless testing proves a problem**
   (prompt §3): Render free Stage 1 for the backend, Hostinger KVM 1
   VPS Stage 2. The frontend gets its own hosting decision below.
3. **No paid infrastructure in Phase 2.** Every service named here has
   a free tier that covers Phase 2 needs; anything that would charge
   needs the owner's written approval first.
4. **Deploy is a manual, owner-approved step** (as in Phase 1). CI
   builds and tests; it does not deploy.

## 2. Backend — Render free tier, Stage 1 (unchanged, with measured realities)

- **Service:** `officerpath-pdf-engine`, Docker web service, plan
  `free`, `healthCheckPath: /health` (`render.yaml`).
- **Measured realities (M7 clean baseline, M8 contended re-measurement
  — VM numbers, not Render numbers):**
  - PPSC-66 single-path parse ~128 s on the dev VM, ~20 min estimated
    at Render free's 0.1 CPU. `WORKER_STAGE_TIMEOUT_SECONDS=1800`
    (30 min) is set in `render.yaml` for exactly this reason — the
    600 s code default would fail every 7-page job.
  - Worst fresh-process tree peak 465 MB vs 512 MB — **fits, marginally
    (~47 MB headroom)**. One parse at a time. A long-lived worker
    accumulates RSS with **no restart policy wired** (VPS-stage work).
  - Render free sleeps after 15 min idle (~30–60 s wake). Keep-alive
    decision is **DEFERRED** (ADR-001) — no uptime pinger until the
    owner decides explicitly.
- **What must change before the first Phase 2 backend deploy:**
  1. `render.yaml` `branch:` is `officerpath-phase1-engine` — change
     to `officerpath-phase2-web` when the Phase 2 backend ships (or
     deploy the Phase 1 branch first and switch later; M10 decides
     with the owner).
  2. GitHub App install + push (owner step, outstanding since M1).
  3. Migration 015 applied live (owner step) + `alembic upgrade head`
     with `DATABASE_URL` set — until then `/health` reports `degraded`
     and the engine-DB paths return 503.
  4. Dashboard secrets set: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
     `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
     `ENVIRONMENT=production` (all `sync: false` in `render.yaml` —
     never in the repo).
- **Docker image:** never built (no Docker on the VM). The first CI
  build after the push verifies the `Dockerfile` (which installs
  `tesseract-ocr` + `eng`/`urd`/`ara`/`osd` — the deploy must install
  Tesseract in the image, never rely on the VM; M7/M8 incidents).
- **Stage 2 (later, owner-funded):** Hostinger KVM 1 VPS — the worker
  runs as its own process (`python -m app.workers.runner`), PaddleOCR
  becomes available (VPS profile, 4 GB), restart policy and
  per-job subprocess isolation land there. Not a Phase 2 build item.

## 3. Frontend hosting — decision (M2 confirms, M10 executes)

**Recommended: Vercel (free tier)** for the Next.js app.

| Option | Why it fits / why not |
|---|---|
| **Vercel free (recommended)** | Native Next.js hosting (App Router, ISR, edge middleware), free tier covers Phase 2 traffic, preview deployments per PR, zero-config for `web/`. No card required for the free tier. |
| Netlify free | Viable alternative; Next.js support is good but Vercel is the reference implementation. Fallback if Vercel is unavailable to the owner. |
| Render static site / web service | Possible (keeps one provider), but Next.js SSR on Render free sleeps like the backend and is slower to iterate. Only if the owner prefers a single provider. |
| Hostinger VPS (with the backend, Stage 2) | Possible later; not Phase 2 — the VPS does not exist yet and needs payment. |

- **M2 confirms the choice with the owner** (one question, one
  answer) before any account is connected. No account is created in
  M1/M2 without that approval.
- **The frontend must work against the local backend first**
  (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`) and against the Render
  backend later — the URL is env-configured, never hardcoded.
- **Preview deployments** (per PR) point at the staging backend or a
  clearly-labelled "backend not connected" state — a preview must
  never silently talk to production data.

## 4. Environment inventory (dev vs prod)

### Backend (Render Dashboard secrets + `render.yaml` non-secrets)

From `app/config.py` + `.env.example` (complete list — no other env
vars exist):

| Var | Dev | Prod (Render) |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` |
| `PORT` | `8000` | `8000` (Render sets `PORT`; the Dockerfile honours it) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | dev project values (owner) | same project (single Supabase project in Phase 2) |
| `SUPABASE_SERVICE_ROLE_KEY` | server-side only | Dashboard secret, never in repo/frontend |
| `DATABASE_URL` | `sqlite:///./var/dev.db` (tests) or local Postgres | Supabase Postgres (`postgresql+psycopg://...`), Dashboard secret |
| `STORAGE_BACKEND` / `STORAGE_ROOT` | `local` / `var/storage` | `local` is a dev default — Render's filesystem is ephemeral; production persistence is the `pdf-documents` bucket (see §5) |
| `DEPLOYMENT_PROFILE` | `local` | `render-free` |
| `PADDLEOCR_ENABLED` | `true` | `false` |
| `WORKER_ENABLED` | `false` | `true` |
| `WORKER_STAGE_TIMEOUT_SECONDS` | `600` | `1800` |
| `TESSERACT_TIMEOUT_SECONDS` | `300` | `300` |
| `GEMINI_*` | all defaults (disabled) | unchanged — key deferred by the owner |
| Rate limits / file limits | defaults | defaults (raise only with measured cause) |

### Frontend (`web/.env.example`, M2)

| Var | Dev | Prod |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Render backend URL |
| `NEXT_PUBLIC_SUPABASE_URL` | dev project URL | same project |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon key (publishable) | same |
| (no service-role key, no DATABASE_URL, no secrets) | — | — |

## 5. CORS, storage, database, migrations at deploy time

- **CORS:** the backend allows exactly the configured frontend
  origins (dev `http://localhost:3000`; prod the deployed frontend
  domain). Implemented in M2/M3 when the first browser call is made;
  `*` is never used with credentials in production. (Phase 1 has no
  CORS middleware yet — the web app is the first browser client, so
  M2 adds it deliberately rather than discovering it by accident.)
- **Storage:** production uploads go to the private `pdf-documents`
  bucket (migration 015). Local-disk storage (`var/storage`) is dev
  only — Render's filesystem is ephemeral and must not be treated as
  persistence. The register flow (client → bucket → register) is the
  production path; the direct-upload path stores via the backend's
  storage abstraction, which must be pointed at the bucket before
  prod (M4 decision, recorded then).
- **Database:** one Postgres (Supabase-hosted). Two writers exist
  today (PostgREST for register/jobs, SQLAlchemy for engine tables) —
  see doc 01 §2.2 and doc 03 §5. Migrations: 015 via Dashboard (once,
  owner), Alembic 0001/0002 + Phase 2 revisions via `alembic upgrade
  head` from a machine with `DATABASE_URL`. **No migration runs
  automatically on deploy** until M10 decides the deploy-time step.
- **Backups:** Supabase free-tier backups are the project's backup
  story in Phase 2 (owner verifies the plan in the Dashboard during
  M10). Engine-DB tables live in the same Postgres, so they share
  that backup. No separate backup system is built in Phase 2.

## 6. Monitoring, rollback, runbook

- **Monitoring:** `/health` (Render health check + manual check),
  `/metrics` (Prometheus-style; scraped only if/when a scraper
  exists — in Phase 2 it is read manually during verification, not
  wired to an alerting system), JSON logs in Render. Alerting
  thresholds are a post-Phase-2 decision, not a build item.
- **Rollback (backend):** Render Dashboard → service → Rollback
  restores the previous deploy (README "Deploy" section, verified
  in M8). Database rollback is the Alembic `downgrade()` of the
  revision being reverted — only after confirming the affected
  tables hold no unrecoverable user data (doc 03 §6 rule).
- **Rollback (frontend):** Vercel/Netlify instant rollback to the
  previous deployment; the frontend never migrates data, so its
  rollback is data-safe by construction.
- **Smoke test after every deploy (M10 checklist):** `/health` 200,
  `/version` shows the deployed commit, unauthenticated parse → 401,
  register → 201 against staging data, one async job queued → done,
  review list loads. The Phase 1 STOP CONDITION (live phone
  verification on the three acceptance files) still applies to the
  engine and extends to the web upload flow in M10.

## 7. M2 decision note (2026-11-22) — Vercel free CONFIRMED

**Decision: Vercel free tier is confirmed as the frontend hosting
recommendation.** Reasons, measured against the M2 build rather than
assumed:

- The M2 app is a standard Next.js 16 App Router build (Turbopack,
  static public pages, no custom server, no Node-only runtime code
  outside the framework). It builds cleanly with `npm run build` and
  needs nothing Vercel-specific — the same output deploys on any
  Next.js host, so the choice is reversible.
- Vercel is the reference Next.js host: App Router, ISR, edge
  middleware (needed in M3 for the auth guard via `proxy.ts`) and
  preview deployments per PR work with zero configuration.
- The free tier requires no card and covers Phase 2 traffic; nothing
  in Phase 2 needs a paid Vercel feature.
- Alternatives reconsidered: Netlify free remains the fallback (good
  Next.js support, second choice); Render for the frontend is rejected
  for now because Next.js SSR on Render free would sleep after 15 min
  idle like the backend, and iteration is slower; the Hostinger VPS
  does not exist yet (owner-funded, Stage 2).

**What this decision does NOT do:** no Vercel account was created, no
project was connected, nothing was deployed, and no charge was incurred
in M2. The owner still confirms the choice before any account is
connected (M10 executes the deploy, with the owner's explicit
approval). If the owner prefers Netlify or a single provider, the app
moves without code changes — the only Vercel-specific surface is the
hosting configuration, not the application.
