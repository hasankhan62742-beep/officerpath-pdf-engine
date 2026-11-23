# Final Deployment Report — OfficerPath AI

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Programme:** Master Execution Prompt — "Phase 1 + Phase 2 Safe Deployment, Live Verification & Phase 3 Preparation" (owner, 2026-11-23)
**Report date:** 2026-11-23 (PKT)
**Repository (local):** `~/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`, head `cbd4bb0`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`, head `461c9a2`
**Author:** Final-report subagent (read-only synthesis of workstreams A–H + the get_test security fix; no file modified except this report; no live system touched; no money spent)

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Scope labels — read every claim with its label:**
- **Locally verified** — checked on this VM (tests, builds, file inspection, local harnesses). Most evidence in this report is in this category.
- **Staging verified** — checked on a staging environment. **Nothing in this report is staging verified: no staging project or staging environment exists.**
- **Production deployed** — running on a live service. **Nothing in this report is production deployed: no Render service and no Vercel project exists yet.**
- **Owner-device verified** — proven on the owner's own phone. **Nothing in this report is owner-device verified: the phone acceptance has not run.**

**Honesty note:** Every figure in this report is cited to the workstream report or document it comes from. Where an earlier document is wrong or stale, this report says so (see the Appendix — discrepancies found). No live check was run for this report; live facts are marked parent-reported and were not re-checked here. No number is invented.

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` (A), `02-github-ci-report.md` (B), `03-supabase-migration-runbook.md` (C), `04-render-backend-deployment.md` (D), `05-vercel-frontend-deployment.md` (E), `06-live-acceptance-report.md` (F), `07-security-and-licensing-report.md` (G), `docs/phase3/PHASE3_MASTER_ARCHITECTURE.md`, `PHASE3_DATABASE_DESIGN.md`, `PHASE3_PAYMENT_WORKFLOW.md`, `PHASE3_SECURITY_PLAN.md`, `PHASE3_TEST_PLAN.md` (H), `docs/phase2/PHASE_2_COMPLETION_REPORT.md` (M10), `docs/phase2/deployment-checklists.md`, `docs/phase2/rollback-runbook.md`, `docs/phase2/migration-runbook.md` (M10 — **superseded by Workstream C**).

---

## 1. Executive summary

**Where the programme stands, in one page.**

**Done (locally verified).** Phase 1 (Python/FastAPI engine, M0–M8) and Phase 2 (Next.js web application, M1–M10) are COMPLETE as local builds — all milestones parent-verified. The master deployment programme ran all eight workstreams A–H to completion: seven audit/readiness reports (`docs/deployment/01`–`07`), five Phase 3 design documents (`docs/phase3/`, 969 lines), and one security fix. The full test suite is green locally at **617 passed / 0 failed** (after the fix). The repository is clean: no secret committed, no deployment-required file missing, full history intact. The GitHub push of the Phase 2 baseline (`461c9a2`) succeeded from the owner's PC on 2026-11-23 ~12:34 PKT.

**Blocked (the hard stops).** Supabase migration 017 **FAILED live** (`ERROR 42703: column "deleted_at" does not exist`) — the live `documents` table was never given the column the engine expects. Its one-column repair (migration 018) is written but **not applied and not committed** and needs the owner's approval. Alembic 0001–0009 have **never run against live Postgres**. No Render service and no Vercel project exists. GitHub CI has **never run**. The live phone acceptance (the STOP CONDITION) has **not run** — nothing is deployed yet for it to run against.

**What the owner must decide (the short list).** Approve or reject the 018 fix; choose the production domain; choose the PyMuPDF licence path (before the paid launch); check the first CI run; run `npm audit` on his machine; delete the unconfirmed M3 test user; create the PR to `main` once CI is green; decide keep-alive; push the 9 local commits from his PC. The full decision table is §11; the ordered owner steps are §12; the recommended sequence to the beta is §15.

**The honest bottom line:** the code is ready and the plan is written, but **nothing is deployed, nothing is production-verified, and nothing is phone-verified**. The programme ends in a fully specified, gated path to the 20–30 student beta — it does not end in a launch.

---

## 2. Repository and GitHub

| Item | State | Status |
|---|---|---|
| Branch | `officerpath-phase2-web` (current); `officerpath-phase1-engine` (`69ca62d`) is a strict subset — merge-base `69ca62d`, Phase 2 is a strict superset (A §1, B §2) | VERIFIED |
| Local head | `cbd4bb0` — "Fix: withhold answer key from GET /tests/{id} while test is in progress" (12 files, +266/−35) | VERIFIED |
| Local commit count | **30 commits** on `officerpath-phase2-web` (21 project commits + 9 deploy-programme commits) | VERIFIED |
| GitHub head | `461c9a2` — Phase 2 M10 (pushed by the owner from his PC 2026-11-23 ~12:34 PKT; parent-verified via the GitHub API: head `461c9a2`, then `7abb28f`, `094b6b6`) | COMPLETED (parent-reported) |
| Local vs GitHub | Local is **9 commits ahead** of GitHub: A `4510a90`, B `a4337af`, C `6c331f2`, D `d221c1b`, E `1a7f868`, F `04318c3`, G `636c337`, H `7bbec41`, fix `cbd4bb0` — **all local-only, none pushed** | PENDING (owner-PC push) |
| Commits Phase 1 head → local head | **19** (10 milestones M1–M10 + 9 deploy-programme commits) | VERIFIED |
| Git remote (local) | None configured — the VM repo cannot push/fetch on its own, by design; pushes go through the owner's PC | VERIFIED |
| Working tree | Clean except the two **untracked 018 migration files** (by design — see §3) | VERIFIED |
| Secrets in git | None live. One JWT-like match in `web/package-lock.json` is a 30-char npm integrity-hash fragment (false positive, A §5). `.env` / `web/.env.local` never committed; `web/.env.local` is mode 0600, gitignored, with a 0600 backup | VERIFIED |
| Deployment-required files | All present: `render.yaml`, `Dockerfile`, `requirements.txt`, `web/package-lock.json`, Supabase migrations 015–018, Alembic 0001–0009, `.github/workflows/ci.yml` (A §6) | VERIFIED |
| Fixtures | Present: PPSC-66 PDF (5,911,945 bytes), Paper 60 photo (3,475,937 bytes), both re-sent table photos (A, appendix) | VERIFIED |

**CI status — PENDING (first run).** The workflow (`.github/workflows/ci.yml`) was inspected in full (B §4): 6 jobs — `web` (Node 24, tsc/lint/build), `lint` (ruff), `typecheck` (mypy), `test` (pytest + Alembic up/down on SQLite), `security` (pip-audit + detect-secrets), `docker-build` (gated on the four code jobs). It does not deploy and does not touch live Supabase. **No CI run has ever existed.** The owner's push of `461c9a2` should have triggered one; the owner must check the GitHub → Actions tab. If no run appears, check that Actions is enabled (Settings → Actions → General). All six jobs must be green before the PR below is merged.

**PR plan — PENDING (prepared, not created).** Target: merge `officerpath-phase2-web` → `main` (B §3). `main` on GitHub currently points at `eaff4cb` ("Initial commit", a GitHub-generated README, 3 objects, 207 bytes) and contains no project code — the PR would bring the entire history onto `main` in one merge, with a **merge commit** (no squash, no rebase). Do not delete `officerpath-phase2-web` until the first deploy from `main` is verified. After the merge, Render and Vercel must be switched to build from `main` (D §12, E §6). **Stale figure to correct:** Workstream B's PR plan says the PR carries **22 commits** — that was true at head `4510a90`. The branch now has **30 commits** (21 project + 9 deploy-programme); the PR would carry 30. (See the Appendix.)

**Discrepancy in the M10 completion report (resolved, non-material):** that report's milestone table cites M10 as commit `c4715fc`, but the pushed head is `461c9a2`. Both carry the same subject and the same parent (`7abb28f`); `461c9a2` is a re-commit 12 seconds later differing by exactly **one line** in the completion report itself (the M10 row's self-citation, changed from "*(this milestone)*" to `c4715fc`). Code-identical. The pushed head `461c9a2` is the deploy baseline. (See the Appendix.)

---

## 3. Supabase and database

Supabase project: `officerpath-ai` (`gliebuyyjguxrwdfuakz`), Singapore, **free plan**. Access is via the owner's **original** Supabase account, signed in via **GitHub** (`hasankhan62742-beep`) — the `pzmir62742@gmail.com` email login holds only the separate `petpassport` project and has **no access** to `officerpath-ai` (C §2, parent-reported).

| Item | State | Status |
|---|---|---|
| Migration 015 (tables) | `public.documents` + `public.jobs` live since M3 (2026-11-22) | COMPLETED (parent-reported) |
| Migration 016 (bucket) | **APPLIED + VERIFIED live 2026-11-23:** `pdf-documents` bucket, private, 100 MB limit, 3 storage policies (verified via SQL + Storage UI) | COMPLETED (parent-reported) |
| Migration 017 (partial unique index) | **FAILED live 2026-11-23:** `ERROR 42703: column "deleted_at" does not exist` | FAILED (parent-reported) |
| Root cause of the 017 failure | 015's `CREATE TABLE public.documents` never included `deleted_at`, but the engine `Document` model (`app/db/models.py:100`) and Alembic 0001 (`:169`) / 0006 (`:105`) all expect it. The `jobs` table was checked at the same time and matches 015 exactly — **no second gap** (C §4) | VERIFIED |
| Blast radius of the gap | Without `deleted_at`, the M4 soft-delete path (`DELETE /api/v1/documents/{id}` sets `deleted_at`) would also 500 live — not just 017 (C §4) | VERIFIED |
| Migration 018 (repair) | Written: `alter table public.documents add column if not exists deleted_at timestamptz;` — one nullable column, no rows touched, idempotent. **NOT applied, NOT committed** (untracked files `supabase/migrations/018_documents_deleted_at.sql` + `_down.sql`) | PENDING — REQUIRES OWNER APPROVAL |
| 017's DROP INDEX state | **UNKNOWN** — whether the `DROP INDEX` committed before the `CREATE` failed was never verified (the browser stopped per its stop rule; the verification query was not run) | BLOCKED (needs the Step 0 query, C §5) |
| Alembic 0001–0009 on live Postgres | **NEVER run** (SQLite only, in tests and local harnesses; B re-verified up/down/up on fresh SQLite → `0009_m9_notifications` head) | PENDING |
| Why Alembic cannot repair the gap | 0006's `_create_documents_if_missing()` returns `False` when the table exists — on live the table exists (from 015), so 0006 skips the whole creation block including the column. **Supabase migration 018 is the only repair path** (C §4) | VERIFIED |
| Backups | **NONE exist and none can exist on the free plan** ("LAST BACKUP: No backups"). The M10 runbook's precondition "confirm a recent backup exists" **cannot be met** on the free plan — that assumption was WRONG and is corrected in C §7 | FAILED (precondition unmeetable) |
| Backup options (corrected, C §7) | A. Manual `pg_dump` ($0, recommended before any data-changing step). B. Pro $25/month (daily backups; confirm the current price in the Dashboard before paying). C. Owner waiver — **data-neutral migrations only**, owner must name the migration. The owner waived the precondition for **016/017 only** on 2026-11-23. The waiver does **not** automatically cover 018 — the owner should name it, or take a manual dump first | PENDING |
| Redirect-URL allowlist | **NOT conclusively proven** (localhost callback + production URL). The web app requests `${origin}/auth/callback`; a re-sign-up reached the email-send step (429 rate-limit) rather than a redirect error — consistent with allowed, not proven (C §8.3, M3) | PENDING |
| M3 test user | `officerpath.m3.test@gmail.com` still exists in live Auth, unconfirmed; must be deleted, **not** used for the phone test (A blocker B9, F §2) | PENDING |
| RLS / storage policies | 015: RLS on, users SELECT + INSERT own rows only, no client UPDATE/DELETE on `documents`, cancel-only UPDATE on `jobs`; 016: bucket private, 3 policies. Engine writes job status with the service-role key, which bypasses RLS (C §8, G §3.5) | VERIFIED (files read) |
| `public.is_admin()` | Not defined in any migration file in this repo; existence live is **inferred** (015's admin policies exist live and 016's admin policy was created successfully — Postgres validates function existence at `CREATE POLICY` time). If it ever disappears, admin policies fail at creation, not silently (C §8.2) | PENDING |

**Correct execution order (C §5):** Step 0 — check the live index state first → Step 1 — apply 018, verify the column → Step 2 — re-run 017, verify the indexdef contains `WHERE deleted_at IS NULL` → Step 3 — Alembic 0001–0009 on live Postgres (`alembic_version` = `0009_m9_notifications`, 8 Phase-2 tables) → Step 4 — deploy-time smoke test. **There is no staging Supabase project** — verification is done against the live project, in order, with a verification query after each step (C §6).

---

## 4. Render backend

| Item | State | Status |
|---|---|---|
| Blueprint (`render.yaml`) | One service, Docker runtime, plan `free`, repo `hasankhan62742-beep/officerpath-pdf-engine`, branch `officerpath-phase2-web` (fixed in M10), `healthCheckPath: /health`. `DEPLOYMENT_PROFILE=render-free`, `PADDLEOCR_ENABLED=false`, `WORKER_ENABLED=true`, stage timeout 1800 s, Tesseract timeout 300 s. Four secrets `sync: false` (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`) — Dashboard secrets, never in the repo | VERIFIED |
| Service | **Does not exist** — no service created, no deploy | PENDING |
| Memory fit | **MARGINAL — CONFIRMED, not corrected.** Worst tree peak across all runs (M7 + M8 + D) is **465 MB vs 512 MB = 47 MB headroom**. D re-measured: single-path **460 MB**, multi-pass **464 MB** (PPSC-66, render-free profile). Server idle baseline separately measured at **152 MB RSS**. The **combined server-plus-parse peak is unmeasured** — the first thing to watch on the live deploy (D §3) | VERIFIED (locally) |
| What the fit means | One PPSC-66 parse fits 512 MB, **one parse at a time**. Two concurrent parses, or one parse plus a second heavy operation in the same container, have never been measured and must be assumed to OOM (D §3.3) | VERIFIED |
| `CORS_ALLOWED_ORIGINS` | **Missing from `render.yaml`** — the API defaults to `http://localhost:3000` only, so the production Vercel frontend would be **blocked by CORS** (browser preflight failure) until the origin is set in the Dashboard. The value cannot be written yet: it depends on the domain decision (§5). Never set it to `*` (D §5.1) | PENDING — blocked on the domain decision |
| Web uploads | Land on **ephemeral disk** (`var/storage`) — a web-uploaded file's stored bytes are lost on a Render restart/redeploy. Parsed results (questions, answers, test sessions) live in Supabase Postgres and survive. Only register-source originals live durably in the `pdf-documents` bucket. Acceptable for the beta, stated plainly (D §5.2) | VERIFIED |
| Cold start / sleep | Free tier spins down after 15 min without inbound traffic; first request after idle takes **~30–60 s** to wake. The in-process worker does **not** keep the service awake (it polls the database, not inbound HTTP), so a queued job waits until something wakes the service (D §9) | VERIFIED |
| Keep-alive | **DEFERRED** (ADR-001, owner decision pending). No keep-alive ping is configured and none is to be added until the owner decides explicitly (D §9) | REQUIRES OWNER APPROVAL |
| PaddleOCR | Gated three ways: profile budget 512 MB < 4096 MB minimum; `PADDLEOCR_ENABLED=false`; `/health` reports `"disabled"`. Cannot run on Render free, full stop — VPS-only (ADR-005, D §3.5) | VERIFIED |
| Health contract | `/health` returns 200 `degraded` (honest) when a dependency is unconfigured, 503 when a configured dependency is unreachable; no secret ever in a health response. Verified on a live local run: 200 `degraded`, `supabase: not_configured`, `ocr_tesseract: available`, `ocr_paddleocr: disabled` (D §6) | VERIFIED (locally) |
| Gemini | Disabled by default (`gemini_advisory_enabled: False`, `gemini_max_calls_per_day: 0`, no key). No paid AI dependency in the core workflow; no Gemini API call has ever been made (D §8) | VERIFIED |
| Dockerfile | Multi-stage, non-root `appuser`, Tesseract eng/urd/ara/osd in the image, HEALTHCHECK on `/health`. **Never built anywhere** — no Docker on the VM. The first CI `docker-build` job is the verification (D §1, B §4) | PENDING (first CI run) |
| Deploy steps | D §10 (Blueprint → Free plan + Docker → four secrets → CORS → deploy → verify `/health` → `/version` → `/metrics` → Alembic → smoke test). **Do not follow** `docs/deploy-render.md` steps 1/3 — they still name the old branch `officerpath-phase1-engine` (stale, D §5.3) | PENDING |

---

## 5. Vercel frontend

| Item | State | Status |
|---|---|---|
| Project | **Does not exist** — no project created, no deploy | PENDING |
| Build (local) | `npm run build` → **exit 0**, **37 routes** (34 `page.tsx` + `/auth/callback` route handler + `/icon.svg` + `/manifest.webmanifest`) — matches M10's "34 pages, 37 user routes" exactly. `npx tsc --noEmit` exit 0; `npm run lint` exit 0 (E §2, B §5) | VERIFIED (locally) |
| Configuration | Next.js 16.4.6, React 19.3.0, no `vercel.json` (zero-config), no Vercel-specific code, no `"use server"` actions. **Root Directory must be `web/`** — the repo root is a Python project; left at the root, Vercel would try to build it and fail (E §1) | VERIFIED |
| Environment variables | **Exactly four, all `NEXT_PUBLIC_`** (names only — values come from the owner's records, never invented): `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`. No service-role key, no `DATABASE_URL` anywhere in `web/` app code. Both Supabase clients throw an explicit "Supabase is not configured" error when missing — loud, never silent (E §3) | VERIFIED |
| Build-time inlining | `NEXT_PUBLIC_*` values are baked into the bundle at build time — changing any of the four has **no effect until redeploy**. A build **passes with missing Supabase variables** (fallbacks exist), so build success is not env-var proof; the smoke test must check the live values (E §2–§3) | VERIFIED |
| Canonical domain | Placeholder **`https://officerpath.ai` is NOT confirmed as owned** — and it propagates into live SEO metadata (canonical, OG, JSON-LD, sitemap) via `SITE_URL`. Options: (a) Vercel default `<project>.vercel.app` (free, immediate); (b) custom domain if owned + DNS. **The placeholder must not survive into the production deploy** (E §4) | REQUIRES OWNER APPROVAL |
| Domain dependency chain | The chosen origin is also (1) the `CORS_ALLOWED_ORIGINS` value Render needs (§4) and (2) the production callback URL for Supabase's redirect allowlist (§3). A domain change is a **three-system change** (Vercel → `NEXT_PUBLIC_SITE_URL` → redeploy → Render CORS → Supabase allowlist), not a Vercel-only one (E §4) | BLOCKED (on the domain decision) |
| Hobby tier | **Non-commercial use only.** The free 20–30 student beta fits Hobby; the **paid Phase 3 launch cannot stay on Hobby** — Pro ($20/seat/month) or another host before commercial launch (E §7). Hobby limits (2026-11-23 public sources): 100 GB transfer, 1M edge requests, 1M invocations, 6,000 build minutes/month. Function duration disagrees across sources (10 s vs 60 s vs 300 s) — recorded as a disagreement, not settled; it does not constrain this app (only the fast auth callback runs here) | VERIFIED |
| Preview deployments | Mechanism is **env-only**: leave Preview-scope variables **unset** (recommended — honest "not connected" state) and **never** copy Production values into Preview scope, or a preview talks to production data. No preview deployment has ever run (E §6) | PENDING |
| Auth guard | `web/proxy.ts` refreshes the Supabase session and redirects `/dashboard/*` and `/admin/*` without a session to `/login`; the dashboard/admin layouts re-check server-side — the proxy is a convenience gate, never the only check (E §6) | VERIFIED |
| Deploy steps | E §8 (import repo → Root Directory `web` → confirm Next.js preset + Node ≥ 20.9 → set the four Production-scope variables → deploy → then CORS on Render + redirect allowlist in Supabase → smoke test §9) | PENDING |
| Branch switch | Build from `officerpath-phase2-web` now; after the PR merges (§2), switch the Production Branch to `main` in the Vercel Dashboard — owner step, only after the first deploy from `officerpath-phase2-web` is verified (E §6) | PENDING |

---

## 6. Live acceptance and the STOP CONDITION

**The STOP CONDITION (unchanged since Phase 1): no fix is "done" until the owner's own phone proves it on the three acceptance files, through the live web upload UI, and the stored rows match the expected values.** Local test suites, local E2E harnesses, and local builds do not satisfy it. No agent may mark it complete on the owner's behalf, and no partial result ("two of three files passed") counts as acceptance (F §1).

| Item | State | Status |
|---|---|---|
| Live phone acceptance | **Not run — nothing is deployed yet** | BLOCKED |
| Acceptance plan | Written and ready to execute (`docs/deployment/06-live-acceptance-report.md`); every result cell is PENDING; no live test was run or claimed (F) | COMPLETED |
| The three files + M10 local baselines (VERIFIED locally — the numbers the live test must reproduce) | `ppsc_paper_66.pdf` — **41 / 41 / 27** (68 `extracted_questions` rows, exactly M5's 68); `table-computer-q67-81-resent-20261121.jpg` — **0 / 0 / 2** (table questions, no options); `paper60-photo.jpg` — **4 / 4 / 9**. Other M10 baselines: API sweep **17/17**, browser E2E **37/37**, walkthroughs 0 px overflow (desktop 15 pages, mobile 360 px 9 pages) (F §3) | VERIFIED (locally) |

**The 11 prerequisites — all must be COMPLETED before the phone test starts** (F §4):

| # | Prerequisite | Status |
|---|---|---|
| P1 | Supabase migration 018 applied + column verified | PENDING |
| P2 | Supabase migration 017 re-applied + indexdef verified (`WHERE deleted_at IS NULL`) | BLOCKED (needs P1) |
| P3 | Alembic 0001–0009 on live Postgres, `alembic_version` = `0009_m9_notifications`, 8 Phase-2 tables | PENDING |
| P4 | Render backend deployed, `GET /health` → 200 `ok` | PENDING |
| P5 | Vercel frontend deployed from `officerpath-phase2-web`, Root Directory `web`, four `NEXT_PUBLIC_*` variables set | PENDING |
| P6 | Canonical domain decided, `NEXT_PUBLIC_SITE_URL` set to the real production origin | REQUIRES OWNER APPROVAL |
| P7 | Render `CORS_ALLOWED_ORIGINS` set to the exact production frontend origin | PENDING (needs P6) |
| P8 | Supabase redirect allowlist includes the production callback URL **and** `http://localhost:3000/auth/callback` | PENDING |
| P9 | Test account ready (real registered account, email confirmed); the M3 test user must be deleted, not used | PENDING |
| P10 | CI first run checked (all six jobs green) | PENDING |
| P11 | The three fixture files on the phone (exact files, transferred without recompression) | PENDING |

**Phone procedure (F §5, one screen at a time):** open the live site → log in → upload each file (JobTracker poll; never wait on a sync call) → record the detail-page counts → screenshots at each step → 12 smoke checks in the same session (login/logout redirect, real dashboard values, test creation + exam submit, results + mistakes, notifications, no overflow, forgot-password, CORS from the production origin) — all PENDING. **Two timings must not be mistaken for failures:** Render cold start ~30–60 s after 15 min idle, and PPSC-66 parse ~20 min at 0.1 CPU (async job model). **Re-upload rule:** uploading the same file again returns the original job (`idempotent_replay: true`) — a re-test must first delete the document, then re-upload. On any mismatch: do not mark complete; record the actual numbers and investigate (wrong file version, dedup replay, live-only OOM/timeout, migration not applied).

**Beta rollout criteria (F §9):** the 20–30 student free beta may begin **only after** all three files PASS, all smoke checks PASS (or any failure is recorded with its cause and an explicit owner decision to proceed), no prerequisite remains PENDING or BLOCKED, and the domain decision is settled. **Until then the site stays unannounced.**

---

## 7. Security

| Item | State | Status |
|---|---|---|
| **The `get_test` answer-key fix — DONE** | Commit **`cbd4bb0`** (12 files, +266/−35; local only, not pushed). **Rule: `correct_index` + `answer_source` are returned ONLY when the session status is `submitted`; otherwise both are null and `is_unknown` is sent** (mirrors the M9 exam shape). Applied in `create_test` (always withheld), `get_test` (by status), `retry` / `from-mistakes` (new session created). `get_test_result` needed no change (404s until a result exists). Schema: `SnapshotItem.correct_index` is now `int \| None` + new `is_unknown` field; the frontend shows "Answer hidden" before submission. **4 new regression tests** (withheld while `created`, withheld while `in_progress`, revealed after submit with exact keys, retry withholds until its own submit); other-user 404 already covered. Existing tests updated to the new rule. **Notable:** M9's `test_exam_session_withholds_answer_key` previously asserted the LEAKY behaviour ("creator's preview DOES show the key") — rewritten to assert withheld/revealed correctly. Parent-verified: commit + fix code read (`_key_visible` returns `status == 'submitted'`; `_snapshot_dict` include-key gating; `get_test` line 846, `create_test` 812, `results.py` 642); affected files re-run by the parent: **78 passed**; ruff clean; format 229 files; mypy gate 68 files clean. Full suite subagent-measured **617/0** (613 + 4 new). tsc 0, lint 0, build 0 (subagent). | COMPLETED (locally verified) |
| What the fix resolves | Workstream G §3.4's **FAILED** finding (residual answer-key exposure via `GET /tests/{test_id}` — the M9 session fix was real, but `get_test` returned the full key to the test owner with no status guard; a cheating hole, not a data breach) and Phase 3 security plan §2.1's prerequisite ("MUST be fixed before the beta"). The fix is implemented and tested **locally**; it reaches `main` only via the PR (§2) — the beta must not start from an unmerged branch | COMPLETED (locally) |
| Auth | Supabase Auth email+password; confirm-email gate works (M3 verified: login before confirming → 400 "Email not confirmed"; `mailer_autoconfirm = false`). JWT verified **server-side** by asking Supabase Auth (`auth.get_user`) — never decoded locally, never logged, never stored. Invalid/expired → 401; Auth unreachable/unconfigured → 503 (G §3.1) | VERIFIED |
| Admin | Every admin route behind `require_admin` (6 routes); the admin claim comes **only** from the verified JWT's `app_metadata.is_admin`; non-admins get **404** (route existence not confirmed). A middleware logs any `is_admin` / `role` / `plan` field appearing in a request body (ignored by handlers). Admin users list has **no email field** — known limitation, not a bug: the engine DB stores no student email (G §3.2) | VERIFIED |
| Exam-key handling (after the fix) | `SessionSnapshotItem` carries no key; `get_test` withholds the key while `in_progress` and reveals it only after submit (post-submit review showing the key is intended). The exam-take UI calls only `getExamSession` during the exam (G §3.3 + fix commit) | VERIFIED |
| RLS / storage | Policies match the intended access (§3). The engine writes job status with the service-role key, which bypasses RLS — client policies are intentionally narrow so no client can forge a job outcome (G §3.5) | VERIFIED |
| Secrets | Tree clean except the untracked 018 files; `web/.env.local` mode 0600, gitignored, never committed; no service-role key in the frontend; `render.yaml` secrets all `sync: false`; `.dockerignore` excludes `.env`, `.git`, `.venv`; Dockerfile runs as non-root `appuser` (G §3.6, A §5) | VERIFIED |
| Security headers | Backend (every response) and frontend (`next.config.ts`): `nosniff`, `DENY`, `Referrer-Policy`, `Permissions-Policy`; `X-Robots-Tag: noindex, nofollow` on every private route. No CSP on the frontend (a strict CSP breaks Next.js' own inline runtime scripts — recorded, not hidden) (G §3.8) | VERIFIED |
| Upload validation | Magic-byte validation (not filename/MIME), **100 MB cap**, batch max 20 files, list endpoints capped at 100 rows (G §3.10) | VERIFIED |
| Rate limiting | **Partial — an open gap.** In-memory sliding-window limiter (single-process by design) is applied per-user on the expensive endpoints (async-parse register 10/min, job retry 5/min, review, batch, `/me`). **Not** applied to 8 routers, including exam answer-save and submit — an unthrottled submit loop is possible. Low severity on a single free instance; the build phase should extend the limiter to the exam endpoints alongside Phase 3, since paid tests raise the abuse incentive (G §3.10, Phase 3 security plan §7) | PENDING |
| Dependency audits | `pip-audit`: **no known vulnerabilities found** (B re-ran it). `npm audit`: **BLOCKED on this VM** — re-run in G: `403 Forbidden … policy_denied` (`zz_managed_internal_spaces_package_registries`). Owner-machine step: `cd web && npm audit` (G §3.9, B §6) | BLOCKED (VM policy) |
| What was NOT checked | No live penetration test; no live Supabase Auth re-check (M3 cited); no staging environment; the first CI run (including `docker-build` and detect-secrets) has not happened (G §3.11) | PENDING |

---

## 8. Licensing

| Item | State | Status |
|---|---|---|
| PyMuPDF | **1.26.3**, installed and pinned. Licence: **"Dual Licensed — GNU AFFERO GPL 3.0 or Artifex Commercial License"** (installed metadata). Imported as `fitz` in **6 non-test files**, for two roles that any replacement must cover: **(a) text extraction with layout** (`get_text("dict")` spans/fonts, `get_drawings`, `get_images`) and **(b) page rendering** (`get_pixmap` at 200 DPI — the input to Tesseract for scanned pages). Rendering is not optional (G §1.1) | VERIFIED |
| What AGPLv3 requires | AGPLv3 §13 (remote network interaction) is narrowly written (modified version offered over a network), but **Artifex's own position is stricter**: server-based/SaaS use requires disclosing the application's full source under AGPL, or a commercial licence. Artifex is the copyright holder — its interpretation is the one that would be enforced. **This report is research, not legal advice and not legal clearance** (G §1.2) | VERIFIED |
| The licence-file gap | **There is no `LICENSE` file in this repo** (verified: `ls LICENSE*` → none). A public repo without a licence is "all rights reserved" by default — public visibility is **not** the same as an AGPL licence grant. ADR-004's "already compliant because the repo is public" claim is shaky until an AGPLv3 `LICENSE` file + a source offer exist (G §1.2) | FAILED |
| Decision — four options | **A) Keep PyMuPDF + close the licence gap** — add an AGPLv3 `LICENSE` file + a source offer link in the app, accept the service is AGPL-licensed (source stays public). Cost: $0; cheapest honest path for the free beta. **B) Buy a commercial licence** — ask Artifex for a quote first (Artifex publishes **no prices**, quote-based; third-party five-figure annual ranges are unverified and not claimed). No code change. **C) Replace with pypdfium2** (BSD-3-Clause/Apache-2.0, 5.15.2) — the **only** single-library candidate covering both roles (text + rendering); caveats: different API (no `get_text("dict")`, no `get_drawings`/`get_images`), bundles third-party PDFium binaries, needs a benchmark on the acceptance fixtures — candidate only, **not** evaluated in code. **D) Defer** — allowed **only** while the service stays free and public. No silent replacement (G §1.4–1.5) | REQUIRES OWNER APPROVAL |
| What the decision gates | The **paid launch is blocked** until A, B, or C is chosen. The free beta may proceed once the LICENSE file exists (option A). Any closed-source commercial distribution — including the engine as a closed-source binary/APK bundle — is blocked until decided (G §1.3, §1.5) | BLOCKED (paid launch) |
| Other licences | Backend: all permissive (MIT/Apache/BSD) **except psycopg LGPLv3** (weak copyleft, used unmodified as a dynamically linked library — does not require the application to be open-sourced under normal use, but recorded here rather than hidden). Frontend: all MIT except TypeScript/Playwright (Apache-2.0). Dev dependencies are not installed by the Dockerfile, so dev-only licences do not reach the deployed image (G §2) | VERIFIED |

---

## 9. Phase 3 architecture

**Status: design only — NOT STARTED (implementation).** Five documents, **969 lines total**, commit `7bbec41` ("Phase 3 architecture (Workstream H, docs only)", local only, not pushed): `PHASE3_MASTER_ARCHITECTURE.md` (247), `PHASE3_DATABASE_DESIGN.md` (306), `PHASE3_PAYMENT_WORKFLOW.md` (149), `PHASE3_SECURITY_PLAN.md` (128), `PHASE3_TEST_PLAN.md` (139). Nothing in them exists in code, and nothing was tested. (H, parent-verified: commit + file counts.)

**Plans (the authority — do not invent others):**

| Plan | Price | Test limit | Duration |
|---|---|---|---|
| Free | Rs 0 | 3 tests (lifetime) | No expiry |
| Monthly | Rs 600 | 20 tests | 30 days from activation |
| Two Months | Rs 1,200 | 50 tests | 60 days from activation |
| Yearly | Rs 6,000 | Unlimited tests | 365 days from activation |

Money is stored in **paisa (integer)**, never floats. Plans are data rows (seeded by migration), not code constants; each subscription **snapshots** the plan's name, price, and test limit at activation, so later plan edits never rewrite history. Durations count from **activation**, never from purchase. Limits are enforced **server-side only**, atomically: the check and the test creation happen in the same transaction (row lock on the subscription/usage row); a limit breach returns 402 and creates nothing. One created session = one test consumed (creation is the billable action; abandoned tests are not refunded). A retry or from-mistakes test is a new session and counts. Expiry is enforced at creation only — a session `in_progress` when its subscription expires submits normally (grace rule). Buying while a plan is active is rejected. **Free = no subscription row** — Free is the absence of an active paid subscription; free users' past tests are **not** counted retroactively (no backfill — the limit applies to tests created after the Phase 3 deploy).

**Manual payment flow (Easypaisa / JazzCash — money never touches the server):** plan select → `POST /payments` creates a pending transaction with a unique reference (`OP-XXXXXXXX`) → student pays in the wallet app → student submits TID + amount + date + proof (screenshot/PDF, max 10 MB) → admin reviews the queue and verifies **in the owner's own wallet app** against the 6-point checklist (TID exists; amount matches exactly; date is plausible and within the 72-hour window; method matches; TID not already used; receiving account is ours) → approve (subscription activates atomically, notification + audit row) / reject (reason required, terminal) / info-needed (student resubmits). Pending transactions expire after **72 hours** without proof (daily sweep). A rejected payment is never re-approved. Full history is retained; mistakes are corrected by a separate action (deactivate + audit + notification), never by editing history. **Never claimed:** no automated screenshot verification, no wallet API, no scraping, no instant activation ("usually within 24 hours"), no payment ever taken by the website. Receiving accounts (owner-confirmed): **Easypaisa 03427717288, JazzCash 03060853742**.

**Activation codes:** format `OP-XXXX-XXXX-XXXX` (16 chars from an unambiguous alphabet, ~80 bits, CSPRNG); only the **SHA-256 hash** is stored — the plaintext is shown once at generation and then unrecoverable; plan-linked, single-use (partial unique index on redeemed codes), expiring (default 90 days), transaction-associated, server-side validation, rate limiting (5 failed / 15 min per user, 10 / hour per code), attempt logging, atomic redemption, generic error messages (no code-existence oracle).

**Admin modules:** students, subscriptions, payment approvals/rejections, code generation, plans, usage analytics, transactions, expiry monitoring, notifications, admin roles, audit logs. Roles are a **layer on top of** `require_admin`, never a replacement: owner / finance / support; an admin with no role row is treated as support (least privilege); role assignment is owner-only; an admin cannot approve their own payment (self-approval ban).

**Schema decisions (existing schema reviewed first, `app/db/models.py` — 28 tables):** 10 new tables — `plans`, `subscriptions`, `payment_transactions`, `payment_proofs`, `activation_codes`, `activation_redemptions`, `subscription_usage`, `admin_roles`, `admin_users`, `admin_audit_logs`. **No duplicates:** `notifications` is **reused and extended** (CHECK constraint widened with 8 payment types), not duplicated; `audit_log` stays the document/pipeline trail and `admin_audit_logs` is new with distinct fields (admin identity, role at the time, before/after); `student_profiles` is reused for the Students module; Flutter `profiles` is untouched and never merged. Provisional Alembic revisions **0010–0013**, additive only, running **after** the Phase 2 chain is live. A new private `payment-proofs` bucket follows the 016 pattern. No Phase 3 migration has been written or applied.

**Open decisions (8, all REQUIRES OWNER APPROVAL):** D1 Free limit — lifetime 3 (design default) vs 3/month; D2 buying while a plan is active — rejected (default) vs queued; D3 pending-transaction expiry — 72 hours (default) vs 24/48/none; D4 code default expiry — 90 days (default) vs 30/180/none; D5 receiving accounts (as above, changeable only by the owner in the admin panel); D6 PyMuPDF licence path (§8); D7 paid-launch hosting — Vercel Pro or another host (Hobby is not permitted for commercial use); D8 account sharing — accepted limitation in v1 (no device/session limits; the test limit is per account, so sharing splits the same tests).

**Dependencies on the deployment programme (H master architecture §9):** the `get_test` fix is now **DONE locally** (was a beta blocker — §7); the PyMuPDF decision blocks the **paid launch**; Vercel Hobby blocks the **paid launch**; the domain decision is open; 017/018 + Alembic are pending; CI is pending; phone acceptance is pending. **Recommended rollout:** free beta first (after phone acceptance, the `get_test` fix, and the domain decision) → paid plans open (after the PyMuPDF decision, the paid-launch hosting decision, and a full phone end-to-end of the manual payment flow) → activation codes (after the payment flow has run live for at least one real approval).

---

## 10. Test evidence

**Scope key:** every number below is **locally verified** unless labelled otherwise. Nothing is staging verified (no staging exists), nothing is production deployed, nothing is owner-device verified.

| Evidence | Result | Scope | Source |
|---|---|---|---|
| pytest (full suite, after the fix) | **617 passed, 0 failed** (613 + 4 new regression tests) | Locally verified (subagent-measured; parent re-ran the affected files: 78 passed) | Fix commit (parent, MEMORY 2026-11-23); M10: 613/0 |
| pytest (M10 baseline) | **613 passed, 0 failed** in 299.88 s (M10 report); B re-ran **613/0 in 307.66 s** — same count, different runtime (VM variance, not a discrepancy) | Locally verified | M10 report §3; B §5 |
| ruff check / format | Clean / clean (229 files) | Locally verified | B §5; parent re-ran after the fix |
| mypy (CI gate) | SUCCESS, no issues in 68 source files | Locally verified | B §5; parent re-ran after the fix |
| TypeScript typecheck | Exit 0, no errors | Locally verified | B §5; E §2; fix (subagent) |
| ESLint | 0 problems | Locally verified | B §5; E §2; fix (subagent) |
| Production build (`npm run build`) | PASS — 34 pages / 37 user routes | Locally verified | M10 report §3; B §5; E §2 |
| OpenAPI paths | 49 | Locally verified | M10 report §3 |
| pip-audit | **No known vulnerabilities found** | Locally verified | B §5 (reported by B, not re-run in G) |
| detect-secrets | Exit 0; 3 hashed entries — all placeholders/test dummies, none live. (The scan rewrites the baseline file in place; B restored it with `git checkout` — tree clean. The committed baseline is stale, generated 2026-11-21 — housekeeping, not a gate failure.) | Locally verified | B §5 |
| Alembic up/down/up | Fresh SQLite → `0009_m9_notifications` (head); all revisions 0001–0009 applied and downgraded cleanly | Locally verified — **SQLite only**; Postgres behaviour unproven until the live run | B §5 |
| API regression sweep | **17/17** steps PASS | Locally verified (M10 harness) | M10 report §3; F §3 |
| Browser E2E (acceptance + walkthroughs) | **37/37** steps PASS; 0 px overflow (desktop 15 pages, mobile 360 px 9 pages) | Locally verified (M10 harness) | M10 report §3; F §3 |
| Acceptance files via the WEB UI | PPSC-66 **41/41/27** (68 rows); table photo **0/0/2**; Paper 60 **4/4/9** — UI == stored rows | Locally verified (M10 harness) | M10 report §3; F §3 |
| Server-clock timer | Browser clock +1 h → timer decayed exactly 10 s; submit 4.5/9.0 = 50.0% hand-checked; double submit idempotent (M7) | Locally verified | M10 report §2 |
| Scoring | Result == stored row exactly (3.25/9.0 = 36.11% in M8; 5.0/5.0 = 100.0% in M10) | Locally verified | M10 report §2–§3 |
| Render memory (parse tree) | Worst **465 MB vs 512 MB = 47 MB headroom** (D re-measured 460/464; server baseline 152 MB; combined peak unmeasured) | Locally verified (VM, not Render) | D §3 |
| `/health` contract | 200 `degraded` with honest per-check reporting (no Supabase env); `ocr_paddleocr: disabled` | Locally verified (live local run) | D §6 |

**Lighthouse — honesty note (the correction).** The M10 completion report's table labels its "M10 after" figures as the **median of 2 runs**: Home 75, Features 79. That label is wrong. The raw JSONs show the after-runs were Home **68 + 75** and Features **75 + 79** — so 75 and 79 are the **better of the two runs, not medians**. The true medians are **Home 71.5 / Features 77**. The conclusion is unchanged: the Providers-split effect is inside the harness noise floor (identical builds swing ±300 ms TBT and ±2.3 s LCP run to run) — no reliable gain demonstrated, no regression. These are **localhost-harness numbers, not production numbers**; production numbers can only come from the deployed site. (M10 report §3; parent-found correction, recorded in the M10 presentation.)

**What no evidence proves:** Postgres-only behaviour (RLS enforcement, `gen_random_uuid()`, storage policies, partial unique indexes) is proven only by the live Dashboard verification queries in C §5 — none of which have run yet. The Docker image has never been built. iPhone Safari / real-device behaviour is unverified. Urdu preservation is not E2E-proven. The first CI run has not happened.

---

## 11. Open owner decisions

Every decision that needs the owner, in one table, each with what it unblocks. **Nothing here is decided by this report.**

| # | Decision | Status | What it unblocks |
|---|---|---|---|
| D-01 | **Approve the 018 fix** (commit the two 018 files, then apply: Step 0 index check → 018 → re-run 017 → verify). The 016/017 backup waiver does **not** automatically cover 018 — the owner should name it, or take a manual `pg_dump` first (C §7.4, §11) | REQUIRES OWNER APPROVAL | 017 re-run → Alembic live → deploy → phone acceptance |
| D-02 | **Canonical domain** — Vercel default `<project>.vercel.app` (free, immediate) vs custom domain (`officerpath.ai` or another, if owned + DNS) (E §4) | REQUIRES OWNER APPROVAL | Render `CORS_ALLOWED_ORIGINS`, Supabase redirect allowlist, `NEXT_PUBLIC_SITE_URL` (a three-system change) |
| D-03 | **PyMuPDF licence path** — A keep + LICENSE file ($0) / B commercial licence (quote first) / C replace with pypdfium2 (migration + benchmark) / D defer (free + public only) (§8) | REQUIRES OWNER APPROVAL | The **paid launch** (and the beta's licence gap, via A) |
| D-04 | **Check the first CI run** (GitHub → Actions tab; all six jobs green) — and act on the result if any job is red | REQUIRES OWNER APPROVAL | The PR to `main` (§2) |
| D-05 | **Run `npm audit` on the owner's machine** (`cd web && npm audit`) and record the result — the only dependency check the VM cannot do (VM registry 403) | PENDING (owner step) | Dependency assurance before launch |
| D-06 | **Delete the unconfirmed M3 test user** `officerpath.m3.test@gmail.com` (Dashboard → Authentication → Users) | PENDING (owner step) | Live Auth hygiene; the phone test must use a real account, not this one |
| D-07 | **Create the PR** `officerpath-phase2-web` → `main` (merge commit) — only after CI is green (§2) | REQUIRES OWNER APPROVAL | `main` becomes the production branch; Render/Vercel switch to `main` |
| D-08 | **Keep-alive pinger** — yes or no (Render free sleeps after 15 min idle; async jobs submitted while asleep do not start until something wakes the service) (D §9) | REQUIRES OWNER APPROVAL — DEFERRED since ADR-001 | Async-job responsiveness on the free tier |
| D-09 | **Push the 9 local commits** from the owner's PC (A–G reports + H docs + the fix). The PC clone is at `461c9a2`; the VM branch is 9 ahead — the commits must first reach the PC (new bundle or another transfer the parent arranges), then `git push` | PENDING (owner step) | GitHub matches local; CI runs on the new commits; the PR carries the full history |
| D-10 | **Free-limit policy (Phase 3 D1)** — lifetime 3 per account (design default) vs 3 per calendar month | REQUIRES OWNER APPROVAL | The Phase 3 build (before it starts) |
| D-11 | **Paid-launch hosting** — Vercel Pro ($20/seat/month) or another host (Hobby forbids commercial use) (§5) | REQUIRES OWNER APPROVAL | The paid launch (not the free beta) |
| D-12 | **Backup story before public launch** — Pro ($25/month, daily backups) or a standing manual `pg_dump` routine (the free plan will never back the project up) (C §7) | PENDING | Data safety once real student data exists |

---

## 12. Open owner steps

Every action only the owner can do, in dependency order. (Parent/agent steps — e.g. committing 018 once approved — are noted where they belong.)

1. **Decide 018 + the domain** (D-01, D-02) — these two decisions unblock everything downstream. Nothing else in this list can proceed in full without them.
2. **Push the 9 local commits** (D-09) — get the commits onto the PC, then push `officerpath-phase2-web`. (The VM repo has no remote and cannot push on its own.)
3. **Check the first CI run** (D-04) — GitHub → Actions tab; all six jobs must be green. If no run appears, check Actions is enabled (Settings → Actions → General).
4. **Create the PR** `officerpath-phase2-web` → `main` (D-07) — only after CI is green; merge commit; do not delete `officerpath-phase2-web` until the first deploy from `main` is verified.
5. **Supabase — Step 0 index check** (C §5): `select indexname, indexdef from pg_indexes where tablename = 'documents' and indexname = 'documents_user_hash_idx';` — record which of the three states the index is in.
6. **Apply 018, verify the column** (C §5 Step 1): `select column_name, data_type from information_schema.columns … and column_name = 'deleted_at';` — expect one row, `timestamp with time zone`.
7. **Re-run 017, verify the indexdef** (C §5 Step 2): the indexdef **must** contain `WHERE deleted_at IS NULL`. Then the behaviour check: upload a file → delete the document → re-upload the SAME file — the second upload must succeed with a NEW document id (not a 500).
8. **Alembic 0001–0009 on live Postgres** (C §5 Step 3) — from a machine with the live `DATABASE_URL`: `alembic upgrade head`, then verify `alembic_version` = `0009_m9_notifications` and 8 Phase-2 tables. **Take a manual `pg_dump` first** (Option A) — this is the first step that creates tables holding user data, so the waiver rule does not apply.
9. **Render deploy** (D §10) — Blueprint from `render.yaml`, plan Free, Docker; set the four `sync: false` secrets in the Dashboard; set `CORS_ALLOWED_ORIGINS` once the domain is decided; verify `/health` → 200 `ok`, `/version` shows the deployed commit. (If Render asks for a card at signup, **stop and report** before entering any payment details.)
10. **Vercel deploy** (E §8) — import the repo, **Root Directory `web`**, confirm the Next.js preset and Node ≥ 20.9, set the four Production-scope `NEXT_PUBLIC_*` variables (values from the owner's records), deploy. Leave Preview-scope variables unset.
11. **Confirm the redirect-URL allowlist** (C §8.3, E §5) — Supabase Dashboard → Authentication → URL Configuration → Redirect URLs must include `http://localhost:3000/auth/callback` **and** `https://<production-domain>/auth/callback`.
12. **Delete the M3 test user** (D-06) — Dashboard → Authentication → Users.
13. **Live phone acceptance — the STOP CONDITION** (§6) — the three files on his real Android phone through the live web upload; record the UI counts and screenshots; the parent verifies the stored rows. No fix is "done" until this passes.
14. **`npm audit` on the owner's machine** (D-05) — `cd web && npm audit`; record the result.
15. **`flutter analyze`** on the toggle files (M10 completion report §8 item 10) — no SDK on the VM; owner step.
16. **Gemini server key** — **deferred by the owner** ("baad ki bat"). Do not keep asking for it. The advisory adapter stays disabled; no key is provisioned and no Gemini API call has ever been made.

---

## 13. Risks and limitations

The honest list. None of these is hidden in an earlier report; all are stated here so the owner decides with open eyes.

1. **Render memory margin (47 MB).** Worst parse-tree peak 465 MB vs 512 MB; the combined server-plus-parse peak is unmeasured; two concurrent parses are unmeasured and must be assumed to OOM. The long-lived worker's RSS accumulates across parses (73 MB baseline → 369 MB after one parse) with **no restart policy wired** — that is VPS-stage work (D §3, M10 checklists E1). If OOMs recur live, the honest fix is the Stage 2 VPS, not tuning the free tier.
2. **Ephemeral web uploads.** A web-uploaded file's stored bytes are lost on a Render restart/redeploy (parsed results survive in Postgres). The durable-originals work (upload-to-bucket from the web app) is a later improvement (D §5.2).
3. **No staging project.** Every verification is done against the live project, in order, with a verification query after each step. Postgres-only behaviour is proven only by those live queries (C §6).
4. **No live backups on the free plan.** The only $0 backup is a manual `pg_dump`; Pro is $25/month; PITR is a Pro add-on quoted at $100/month (C §7). A backup waiver is valid only for data-neutral migrations the owner names.
5. **Docker never built.** The first CI `docker-build` job is the first proof the Dockerfile works (D §1, B §4).
6. **CI has never run.** The workflow is inspected and sound, but no run result exists; the PR must not merge while CI has never run (B §3–§4).
7. **Phone acceptance outstanding.** Nothing is owner-device verified; the beta stays unannounced until the STOP CONDITION is met (§6).
8. **iPhone Safari / real device unverified; Urdu preservation not E2E-proven;** inferred-flag + Q&A-pair rendering unit-test-only; invalid-token → 401 unit-test-only; no email in the admin users list (M10 report §7).
9. **`npm audit` never run;** no systematic outdated-dependency check (VM registry 403 blocks both) (B §6, G §3.9).
10. **`public.is_admin()` existence is inferred, not directly verified** (§3).
11. **Rate limiting is partial** — 8 routers, including exam save/submit, have none; the limiter is in-memory and single-process (G §3.10).
12. **Phase 3 v1 accepted limitations** (H security plan §8): account sharing is not prevented; manual review is the bottleneck ("usually within 24 hours", no SLA); no automated fraud detection; the in-memory rate limiter does not survive a restart or span replicas.
13. **Environment fragility (not a code defect):** the VM wipes system Tesseract on runtime restarts (6 times in this project's history) and can hit disk-quota errors despite free space shown by `df`. The deploy must never rely on a host-installed Tesseract — it comes from the Docker image (B §5, D §1, M10 checklists E3).
14. **First-request latency.** Render cold start ~30–60 s after 15 min idle; PPSC-66 parse ~20 min at 0.1 CPU. Both are expected behaviour, not failures — but the phone test and the beta must allow for them (§6, D §3.6/§9).

---

## 14. Rollback and recovery

Full procedures: `docs/phase2/rollback-runbook.md` (M10). Summary here, plus the two new items (018 and the `get_test` fix) that postdate that runbook.

**Web (Vercel) rollback — data-safe by construction.** Vercel Dashboard → project → Deployments → pick the previous GOOD deployment → **⋯ → Promote to Production** (instant; the previous build is re-served, no rebuild). Verify: home loads, login page loads, `/dashboard` (logged out) → 307 `/login?next=%2Fdashboard`, `X-Robots-Tag: noindex, nofollow` on `/login`. No data step — the frontend never migrates data. If the bad deploy was caused by a bad env var, fix the env var first — rolling back the code will not help. If the frontend was never deployed, there is nothing to roll back.

**Engine (Render) rollback.** Render Dashboard → service `officerpath-pdf-engine` → **Rollback** (restores the previous deploy — previous Docker image + the env vars as they were at that deploy; free services keep rollbacks to the last two deploys). Verify: `GET /health` → 200, `GET /version` shows the PREVIOUS commit, unauthenticated parse → 401, one async job queued → done. The engine deploy is stateless (the database lives in Supabase), so rolling back the service does **not** roll back any data — whether the database also needs rolling back is a separate decision (below).

**Database (Alembic downgrades 0003–0009).** One revision at a time, newest first (`alembic downgrade -1`, repeat). Each downgrade **refuses** (raises) if its table holds ANY rows — 0009 `notifications`, 0008 collections, 0007 `student_responses`/`test_results`, 0006 test tables, 0005 `question_subjects` user assignments, 0003 `student_profiles`; 0004 never refuses (no data dropped). **If a downgrade refuses, STOP** — the correct move is almost always to leave the schema in place and roll back only the service; the old code must be able to run against the newer schema, or the rollback is not safe. **Never downgrade on live:** 0001 (drops ALL 17 engine tables, no refusal guard) and 0002 (drops the `layout_applied` column and its values, no refusal).

**Supabase migrations.** 016 down: drops the 3 storage policies + the bucket row — **fails while objects remain** (empty the bucket first). 017 down: drops the partial index, restores the plain unique index — **fails while a live row and a deleted row share a user + hash**, and re-introduces the M6 bug (delete-then-re-upload 500s); only run after the `group by` check in C §5 Step 2 returns no rows. 015 down: drops the `jobs` + `documents` tables — **destructive and irreversible without a backup**; never run on live without the owner explicitly approving it with a verified backup in hand.

**018 rollback (new — postdates the M10 runbook).** `018_documents_deleted_at_down.sql`: drops the partial index, then drops the `deleted_at` column. **Only safe while zero rows are soft-deleted** — check `select count(*) from public.documents where deleted_at is not null;` (must be 0) or the soft-delete markers are lost. Re-create the plain unique index afterwards if dedup enforcement is still wanted (C §10).

**`get_test` fix rollback (new — postdates the M10 runbook).** Revert commit `cbd4bb0`. **Warning: reverting re-introduces the answer-key exposure** (Workstream G §3.4) — do not roll it back without a replacement fix in place. The fix is a security control, not a feature; its rollback is a security decision, not a routine one.

**Recovery if a migration goes wrong (C §7.5).** STOP — do not run the next migration, do not re-run blindly, do not hand-edit `alembic_version`. Read the exact error and record it. Check the actual state with the verification queries for that step before deciding anything. If the failed step is idempotent (016/017/018), fix the cause and re-run the same file. If Alembic failed midway, it resumes from the last applied revision on re-run. If rows were lost or corrupted (not expected from 016/017/018), restore from the manual `pg_dump` or Pro backup **into a fresh database**, verify row counts, then re-point the app — never restore over the live database in place. After any rollback, re-run the deploy-time smoke test and check the admin overview counts against the pre-rollback numbers; record the rollback and its reason in `CHANGELOG.md`.

---

## 15. Recommended sequence forward

The ordered next steps from today to the 20–30 student beta, with the gate that must pass at each step. Nothing here authorises a step that needs the owner's approval — each gate names who opens it.

| Step | Action | Gate that must pass | Owner / agent |
|---|---|---|---|
| 1 | **Decide 018 + the domain** (D-01, D-02) | Owner says yes/no to 018 (and names it in the waiver, or takes a manual dump) and picks the domain | Owner |
| 2 | **Push the 9 local commits** (D-09) | GitHub `officerpath-phase2-web` head matches local `cbd4bb0` | Owner (PC) |
| 3 | **First CI run green** (D-04) | All six jobs green on the Actions tab | Owner checks; agent records |
| 4 | **Create the PR, merge to `main`** (D-07) | CI green (step 3); merge commit; branch kept until the first deploy from `main` is verified | Owner |
| 5 | **Supabase: Step 0 → 018 → 017 → Alembic** (§3, C §5) | Verification queries V0–V7 all pass (indexdef contains `WHERE deleted_at IS NULL`; `alembic_version` = `0009_m9_notifications`; 8 Phase-2 tables) | Owner (Dashboard + machine) |
| 6 | **Render deploy** (D §10) | `/health` → 200 `ok`; `/version` shows the deployed commit; `ocr_tesseract: available`, `ocr_paddleocr: disabled` | Owner (Dashboard) |
| 7 | **Vercel deploy** (E §8) | Home loads at the production URL; the four env vars are the live values (smoke S1–S10) | Owner (Dashboard) |
| 8 | **CORS + redirect allowlist + delete M3 test user** (D-02, D-06, §3) | API call from the production origin succeeds; register → confirmation email → `/dashboard/profile` works on production | Owner (Dashboards) |
| 9 | **Live phone acceptance — the STOP CONDITION** (§6) | All three files PASS exactly (PPSC-66 41/41/27 with 68 rows; table photo 0/0/2; Paper 60 4/4/9) + 12 smoke checks PASS | Owner (phone); parent verifies stored rows |
| 10 | **Beta announcement** (20–30 students, Free plan only) | All §6 beta criteria true: acceptance PASS, smoke PASS, no prerequisite PENDING/BLOCKED, domain settled | Owner |
| 11 | **After the beta — Phase 3 build** (H test plan AC1–AC9) | PyMuPDF decision (D-03) + paid-launch hosting decision (D-11) made; all scenarios pass on Postgres; CI green on the Phase 3 branch; `get_test` fix already merged (it is, via step 4); phone verification of the paid flow (§9 of the Phase 3 test plan) passes | Owner + build phase |
| 12 | **Paid launch** | Phase 3 acceptance criteria AC1–AC9 all filled in with real results; the owner pays himself Rs 600 and approves it on his phone; no Phase 3 feature claimed done without evidence | Owner |

**What happens if a gate fails:** stop at that step. Record the actual numbers, keep the evidence, and fix the cause — do not skip the gate, do not waive it by an agent, and do not announce the beta (or the launch) on a hope. A failed gate is a finding, not something to hide by retrying.

---

## Appendix — discrepancies found while cross-checking the earlier reports

Found by comparing the workstream reports, the M10 completion report, the Phase 3 docs, and the git history against each other. None of them changes a conclusion; all of them are recorded so the next reader does not trip over them.

| # | Discrepancy | Resolution |
|---|---|---|
| 1 | **pytest 613 vs 617.** M10 and Workstream B both report **613/0**. The fix commit reports **617/0**. | **Not a discrepancy.** 617 = 613 + the 4 new regression tests from the `get_test` fix. The parent re-ran the affected files (78 passed) and the subagent measured the full 617/0. |
| 2 | **PR commit count: 22 vs 30.** Workstream B's PR plan says the PR carries 22 commits. The branch now has 30. | **Stale figure.** True at head `4510a90` (21 project + 1 audit). The branch has since gained 8 more deploy-programme commits (B–H reports + the fix). The PR would now carry **30 commits** (21 project + 9 deploy-programme). §2 uses 30. |
| 3 | **M10 commit: `c4715fc` vs `461c9a2`.** The M10 completion report cites M10 as `c4715fc`; the pushed head is `461c9a2`. | **Re-commit, code-identical.** Same parent (`7abb28f`), same subject, 12 seconds apart; the diff is exactly one line in the completion report (the M10 row's self-citation). The pushed head `461c9a2` is the deploy baseline. |
| 4 | **"No GitHub push" (M10 report §7).** The M10 completion report says no GitHub push happened and the GitHub App is not installed. | **Stale.** The owner pushed `461c9a2` on 2026-11-23 ~12:34 PKT (Workstream A §4, parent-verified via the GitHub API); the App was already installed. The M10 report predates the push. |
| 5 | **"Apply 016 + 017" (M10 report §8 item 2).** The M10 owner-steps list says to apply both. | **Superseded.** 016 is DONE (verified live 2026-11-23); 017 FAILED live (ERROR 42703); 018 is the new required step (C §1–§5). |
| 6 | **M10 runbook backup assumption.** The M10 runbook says "confirm a recent backup exists (free-tier backups are the project's backup story)". | **Wrong.** The free plan has no backups at all (C §1 C1, §7). Corrected procedure: manual `pg_dump`, Pro, or a named waiver for data-neutral migrations only. |
| 7 | **M10 runbook migration order.** 015 → 016 → 017 → Alembic. | **Superseded.** Correct order is now 015 live → 016 DONE → **018** → **017 (re-run)** → Alembic (C §1 C2, §5). |
| 8 | **Lighthouse "median" figures.** The M10 report labels its "M10 after" figures as the median of 2 runs (Home 75, Features 79). | **Wrong label.** The raw runs were Home 68 + 75 and Features 75 + 79 — the reported figures are the **better of the two runs**; the true medians are **Home 71.5 / Features 77**. Conclusion unchanged (effect inside the harness noise floor). See §10. |
| 9 | **pytest runtime: 299.88 s vs 307.66 s.** M10 reports 613/0 in 299.88 s; Workstream B re-ran 613/0 in 307.66 s. | **Not a discrepancy.** Same pass count; different runtime under VM contention. |
| 10 | **Phase 3 security plan §2.1 / test plan AC5 list the `get_test` fix as PENDING.** | **Now DONE locally** (commit `cbd4bb0`, §7). The prerequisite is implemented and tested; it reaches `main` only via the PR (§2). AC5's "merged" wording therefore still depends on step 4 of §15. |
| 11 | **Workstream A said the local head was `461c9a2`.** | **Expected progression.** The branch has since gained 9 commits (A–G reports, H docs, the fix) and now stands at `cbd4bb0` — 30 commits total, 9 ahead of GitHub. |
| 12 | **M10 report §3 says "613 passed (299.88 s)" and B says the same suite took 307.66 s; the fix reports 617/0 with no runtime quoted.** | Recorded as measured. The fix's full-suite runtime was not quoted in the parent's verification record; the count (617/0) is what is claimed, not a runtime. |

**Final statement.** The master deployment programme is COMPLETE as a programme of audits, plans, and one security fix — Workstreams A–H done, the `get_test` fix done, this report written. What remains is entirely owner action and live verification: the 018 decision, the domain decision, the push, the first CI run, the migrations, the two deploys, and the phone acceptance. Nothing in this report is production deployed or owner-device verified, and nothing here claims otherwise. The next step is the owner's: step 1 of §15.
