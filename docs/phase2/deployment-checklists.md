# Deployment Checklists — OfficerPath AI Phase 2 (M10)

**Status:** checklists executed against the CURRENT code/config at
M10 (commit `7abb28f` + M10 changes). This is doc 06 executed as a
checklist, NOT a deploy. Nothing was deployed while writing this.

**Precondition for every item below:** the GitHub App install +
push (owner step, outstanding since M1) must happen first — Render
and Vercel both build from GitHub, and the repo is still empty on
GitHub.

## A. Backend — Render free tier (Stage 1, ADR-001)

| # | Check | Result at M10 |
|---|---|---|
| A1 | `render.yaml` `branch:` is `officerpath-phase2-web` | ✅ FIXED in M10 (was `officerpath-phase1-engine`) |
| A2 | `render.yaml` service: Docker, plan `free`, `healthCheckPath: /health` | ✅ present (lines 12–20) |
| A3 | `ENVIRONMENT=production`, `PORT=8000` | ✅ present |
| A4 | `DEPLOYMENT_PROFILE=render-free`, `PADDLEOCR_ENABLED=false` | ✅ present (M3 measured PaddleOCR peak 1.8–3.7 GB — must never run on 512 MB) |
| A5 | `WORKER_ENABLED=true` (Background Workers are not free; without it async jobs never run) | ✅ present |
| A6 | `WORKER_STAGE_TIMEOUT_SECONDS=1800` (600 s default would fail every 7-page job at 0.1 CPU) | ✅ present |
| A7 | `TESSERACT_TIMEOUT_SECONDS=300` | ✅ present |
| A8 | Secrets (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`) are `sync: false` — Dashboard secrets, never in the repo | ✅ present; no secret value anywhere in the repo (secrets scan clean, M9) |
| A9 | Dockerfile installs Tesseract in the image (never relies on the VM) | ✅ `tesseract-ocr tesseract-ocr-eng tesseract-ocr-urd tesseract-ocr-ara tesseract-ocr-osd` |
| A10 | Dockerfile: no migration runs automatically on deploy (CMD is uvicorn only; Alembic ships in the image for a manual `alembic upgrade head`) | ✅ verified — CMD is `uvicorn app.main:app ...` only |
| A11 | Dockerfile: non-root user, HEALTHCHECK on `/health` | ✅ `appuser`, HEALTHCHECK 30s/5s/3 retries |
| A12 | Dockerfile itself builds | ⚠️ UNVERIFIED — no Docker on the VM; the first CI build after the push verifies it (known since M1, still true) |
| A13 | Keep-alive pinger | ❌ NOT added — decision DEFERRED (ADR-001); Render free sleeps after 15 min idle, first request after idle is slow (~30–60 s wake). Owner decides explicitly. |
| A14 | Render-free fit | ⚠️ MARGINAL — worst fresh-process tree peak 465 MB vs 512 MB (~47 MB headroom); one parse at a time; long-lived worker RSS accumulates with no restart policy wired (VPS-stage work) |

## B. Frontend — Vercel free tier (recommended, M2 decision confirmed)

| # | Check | Result at M10 |
|---|---|---|
| B1 | Standard Next.js 16 App Router build, no custom server, no Vercel-specific code | ✅ `npm run build` PASS (34 pages, 37 user routes) |
| B2 | API URL env-configured, never hardcoded | ✅ `web/lib/api.ts` reads `NEXT_PUBLIC_API_URL` (dev fallback `http://127.0.0.1:8000` only — localhost, never a production URL) |
| B3 | No service-role key, no DATABASE_URL, no backend secret anywhere in `web/` | ✅ secrets scan clean (M9 + M10 re-check) |
| B4 | Auth guard via `proxy.ts` (edge middleware) | ✅ guards `/dashboard/*` and `/admin/*` |
| B5 | Canonical domain placeholder `https://officerpath.ai` until the owner confirms | ⚠️ OPEN — owner must confirm the production domain; until then canonical/OG/sitemap use the placeholder |
| B6 | Preview deployments never silently talk to production data | ⚠️ MECHANISM IS ENV-ONLY — a preview uses whatever `NEXT_PUBLIC_API_URL` / Supabase values are set on it; the owner must set preview env vars to a staging backend (or leave them unset so the app shows its honest "not connected" state). No code change in M10; recorded here so the deploy step does not miss it. |
| B7 | Vercel account / project connected | ❌ NOT DONE — owner step at deploy time (M10 executes the checklists, not the deploy) |
| B8 | Fallback host (Netlify free) if Vercel is unavailable | ✅ documented in doc 06 §3; the app needs no code change to move |

## C. Database + storage at deploy time

| # | Check | Result at M10 |
|---|---|---|
| C1 | Migration 015 tables live | ✅ verified live 2026-11-22 (M3) |
| C2 | Migration 016 (bucket) applied | ❌ NOT APPLIED — owner step, see `migration-runbook.md` §1 |
| C3 | Migration 017 (partial index) applied | ❌ NOT APPLIED — owner step, see `migration-runbook.md` §1 |
| C4 | Alembic 0001–0009 applied to live Postgres | ❌ NOT APPLIED — owner step, see `migration-runbook.md` §2 (SQLite only, so far) |
| C5 | Production uploads go to the private `pdf-documents` bucket (Render's filesystem is ephemeral) | ⚠️ BLOCKED on C2 — until 016 is applied the bucket does not exist; the register flow's bucket download is wired (M4) but unproven live |
| C6 | Backups confirmed | ⚠️ OWNER VERIFIES in the Dashboard during deploy (free-tier backups are the backup story — doc 06 §5) |

## D. Post-deploy smoke test (run after the first deploy)

From doc 06 §6 + migration runbook §3:

1. `GET /health` → 200 (not `degraded`).
2. `GET /version` shows the deployed commit.
3. Unauthenticated `POST /api/v1/documents/register` → 401.
4. Register → 201; one async job queued → done; review list loads.
5. **STOP CONDITION (live phone verification):** the three
   acceptance files — PPSC-66 PDF, computer table photo, Paper 60
   photo — parse through the WEB upload on the owner's phone and
   the resulting questions match the engine's stored rows.

## E. Known deployment risks (honest list)

1. **Render-free memory is marginal** (A14): a second concurrent
   parse, or a worker that has already served one big parse, can
   OOM. Mitigation in place: one parse at a time; Stage 2 (VPS)
   is the real fix.
2. **Docker image never built** (A12): the first CI build after
   the push is the first proof the Dockerfile works.
3. **Tesseract must come from the image** (A9): the VM wipes it
   on restart (4 times in M8–M10) — the deploy must never rely on
   a host-installed Tesseract.
4. **PPSC-66 at 0.1 CPU takes ~20 min** (M7 estimate): the 1800 s
   stage timeout covers it, but the first live parse will be slow
   and the phone test must allow for it.
5. **No alerting** (doc 06 §6): `/metrics` is read manually; no
   scraper, no thresholds. Post-Phase-2 decision.
