# Workstream E — Vercel Frontend Deployment Readiness

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream E subagent (local inspection + local build runs; no Vercel project created, no deploy, no live Supabase or Render touched, no money spent)
**Scope:** `web/` (Next.js 16 App Router) build verification, project configuration, environment variables, canonical domain, Supabase redirect dependency, branch strategy, preview deployments, Vercel Hobby free-tier limits, deployment steps, smoke tests, failure modes and rollback.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Every number in §2 comes from a build run in this workstream, with the exact command shown in the appendix. Exit codes were read unpiped (no `| tail` between the tool and the exit code — the Workstream B self-correction is applied here). Vercel Hobby limits in §7 were sourced from current public sources on 2026-11-23 and are labelled as such; where sources disagree, the disagreement is stated, not smoothed over. No Vercel project exists yet, so deployment itself is PENDING and nothing in this report claims a live Vercel check.

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` (Workstream A), `docs/deployment/02-github-ci-report.md` (Workstream B), `docs/deployment/03-supabase-migration-runbook.md` (Workstream C), `docs/deployment/04-render-backend-deployment.md` (Workstream D), `docs/phase2/06-deployment-plan.md` (§3, §7 — Vercel decision), `docs/phase2/deployment-checklists.md` (§B), `docs/phase2/rollback-runbook.md` (§1), `docs/phase2/04-frontend-architecture.md`.

---

## 1. Project configuration — VERIFIED (files read in full)

| Item | Finding |
|---|---|
| Framework | Next.js **16.4.6**, React **19.3.0**, TypeScript, Tailwind CSS 4.3.3, App Router, Turbopack (`web/package.json`) |
| `vercel.json` | **Does not exist** — Vercel zero-config; the framework preset is auto-detected as Next.js. There is nothing Vercel-specific to configure in the repo. |
| Vercel-specific code | **None.** `grep -rni "vercel" web/app web/components web/lib web/proxy.ts web/next.config.ts web/package.json` returns nothing. The app needs no code change to move to another Next.js host (doc 06 §3, §7). |
| Build command | `npm run build` (`next build`); `npm run lint` is `eslint`; `npm run start` is `next start`. No custom server. |
| `next.config.ts` | `reactStrictMode: true`, `cacheComponents: true`, `partialPrefetching: true`; security headers on every path (X-Content-Type-Options `nosniff`, X-Frame-Options `DENY`, Referrer-Policy, Permissions-Policy); **no CSP** — deliberate (M9: a strict CSP breaks Next.js' own inline runtime scripts); X-Robots-Tag `noindex, nofollow` on every private route (`/dashboard`, `/admin`, `/login`, `/register`, `/forgot-password`, `/auth/*`) plus `robots noindex` metadata in the dashboard/admin layouts as a second layer. Turbopack rule for `@tailwindcss/turbopack`. No `NEXT_PUBLIC_*` value is hardcoded here — the API base URL is env-configured (see §3). |
| Root directory (critical) | The repo root is a **Python project**. Vercel must be pointed at **`web/`** as the Root Directory (§8 step 3). Left at the repo root, Vercel would try to build the Python project and fail. |
| Server surface (what actually runs on Vercel) | **Small.** One route handler (`web/app/auth/callback/route.ts` — Supabase auth callback), one edge middleware (`web/proxy.ts` — Supabase session refresh + auth guard for `/dashboard/*` and `/admin/*`, see §6), and partial-prerender dashboard pages. **No `"use server"` server actions anywhere** in `web/app` or `web/lib`. No cron, no background jobs, no image pipeline in the app. The heavy work (OCR, parsing) lives on Render, not here. |
| Build output | `.next/` is gitignored (root `.gitignore:26`, `web/.gitignore:17`); the build in §2 left the working tree clean apart from the two pre-existing untracked 018 files. |
| Node version (local) | Node **v24.22.1**, npm **10.9.4** (this workstream). Vercel's build machine version is set at project creation — the owner must confirm it satisfies Next.js 16's minimum (Node 20.9+) in §8 step 4; this report does not assert Vercel's default. |

## 2. Build verification — VERIFIED (runs in this workstream, unpiped)

Environment: repo at `/home/hatch/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`, head `d221c1b`. `web/.env.local` present, mode **0600** (values never printed).

| Gate | Command run | Result | Status |
|---|---|---|---|
| Production build | `cd web && npm run build` (output to a log file; exit code read directly, not through a pipe) | **Exit 0**; 37 routes in the build output | VERIFIED |
| TypeScript typecheck | `npx tsc --noEmit` | Exit **0**, no errors | VERIFIED |
| ESLint | `npm run lint` | Exit **0**, no errors | VERIFIED |
| Page count | `find web/app -name 'page.tsx' \| wc -l` | **34** `page.tsx` files | VERIFIED |

The 37 build-output routes reconcile with the 34 pages: 34 pages + the `/auth/callback` route handler + `/icon.svg` + `/manifest.webmanifest`. This matches M10's reported "34 pages, 37 user routes" exactly. The first build in this workstream was read through a `| tail` pipe (the pipe's exit code, not the build's); it was re-run unpiped to a log file so the exit code above is the build's own.

**What a passing build does NOT prove:** `NEXT_PUBLIC_*` variables are inlined at build time, and two of the four have fallbacks (`NEXT_PUBLIC_API_URL` → `http://127.0.0.1:8000`, `NEXT_PUBLIC_SITE_URL` → `https://officerpath.ai`). A build therefore **passes with missing Supabase variables** — the failure appears only at request time, when both Supabase clients throw an explicit "Supabase is not configured" error (§3). Build success is not env-var proof; the smoke test in §9 must check the live values.

## 3. Environment variables — VERIFIED (code-grepped, names only)

The app reads **exactly four** environment variables, all `NEXT_PUBLIC_`. No other variable is read anywhere in `web/app`, `web/components`, `web/lib`, `web/proxy.ts`, or `web/next.config.ts`.

| Variable | Read at | Fallback if unset | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `web/lib/api.ts:9` | `http://127.0.0.1:8000` | FastAPI engine base URL. Dev: local engine. Prod: the Render backend URL (Workstream D). Never hardcoded. |
| `NEXT_PUBLIC_SITE_URL` | `web/lib/site.ts:14` | `https://officerpath.ai` (placeholder — §4) | Canonical public URL: `metadataBase`, canonical link, Open Graph URL, and JSON-LD `@id`/`url` (`web/app/layout.tsx`, `web/app/page.tsx`). |
| `NEXT_PUBLIC_SUPABASE_URL` | `web/lib/supabase/client.ts:11`, `server.ts:12`, `proxy.ts:26` | **None — throws** | Supabase project URL (public identifier). |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `web/lib/supabase/client.ts:12`, `server.ts:13`, `proxy.ts:27` | **None — throws** | Publishable anon key (safe to expose to the browser). |

**Secrets check — VERIFIED:** `grep -rn "SERVICE_ROLE\|service_role\|DATABASE_URL"` over `web/app web/components web/lib web/proxy.ts web/next.config.ts web/public` returns **nothing**. No service-role key, no database URL, no backend secret exists anywhere in the frontend code. Both Supabase clients throw an explicit error when the URL or anon key is missing ("Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in web/.env.local") — the failure is loud, never silent. `.env.example` contains placeholders only (`your-supabase-anon-key`); `.env.local` holds the real values, mode 0600, gitignored (Workstream A verified it is not in git history; a 0600 backup exists at `~/workspace/user/officerpath-web-env-backup.txt`).

**Build-time inlining — the fact that governs §8 and §10:** `NEXT_PUBLIC_*` values are baked into the JavaScript bundle at build time. Changing any of the four after a deploy has **no effect until the project is redeployed**. A domain change (§4) or an API-URL change is therefore a redeploy, not a settings edit.

## 4. Canonical domain — REQUIRES OWNER APPROVAL

The placeholder **`https://officerpath.ai`** is used in five places and is **not confirmed as owned by the user** (deployment-checklist B5, still OPEN):

| Place | How the placeholder appears |
|---|---|
| `web/.env.example` | `NEXT_PUBLIC_SITE_URL=https://officerpath.ai` — labelled "Placeholder until the owner confirms the production domain." |
| `web/lib/site.ts:14` | `SITE_URL` fallback when the env var is unset. |
| `web/public/robots.txt:13` | `Sitemap: https://officerpath.ai/sitemap.xml` |
| `web/public/sitemap.xml` | Every `<loc>` is `https://officerpath.ai/...`; the file's own comment says the domain "is a placeholder until the owner confirms the [domain]". |
| `web/app/layout.tsx` + `web/app/page.tsx` | `metadataBase`, canonical, OG URL, and JSON-LD all derive from `SITE_URL` — so the placeholder propagates into live SEO metadata, not just a config file. |

**Options (owner decision, no default taken here):**

| Option | What it means | Cost / effort |
|---|---|---|
| (a) Vercel default subdomain (`<project>.vercel.app`) | Free, works immediately, no DNS work. The project name is chosen at creation; a sensible name is `officerpath-ai` (not yet reserved — first creation wins). | $0 |
| (b) Custom domain (e.g. `officerpath.ai`, if owned) | Owner confirms ownership, then adds the domain in Vercel (Project → Settings → Domains) and points DNS at Vercel (A/CNAME records Vercel shows). Vercel issues the certificate automatically. | $0 on Vercel's side; the domain itself is the owner's existing registration (no new purchase is assumed). |

**Dependency chain (why this decision blocks two other workstreams):** the chosen origin is also (1) the `CORS_ALLOWED_ORIGINS` value the Render backend needs (Workstream D §5.1 — the value is missing from `render.yaml` and the production frontend would be blocked by CORS until it is set in the Render Dashboard), and (2) the production callback URL that must be added to Supabase's redirect allowlist (§5). Until the domain is settled, all three stay pending. If the site ships on the Vercel subdomain first and a custom domain is added later, **all three places must be updated together** (Vercel domain → `NEXT_PUBLIC_SITE_URL` → redeploy → Render CORS → Supabase allowlist) — a domain change is a three-system change, not a Vercel-only one.

**What happens if the site ships with the placeholder still set:** the app works, but every canonical link, OG URL, and sitemap entry points at `officerpath.ai` — a domain the project may not own. Search engines would index the wrong canonical. The placeholder must not survive into the production deploy; at minimum `NEXT_PUBLIC_SITE_URL` must be set to the real production origin before the first production deploy (§8 step 5).

## 5. Supabase Auth redirect dependency — PENDING

The auth flow builds its redirect from the live origin, so it works on any domain **only if that domain's callback URL is allowlisted in Supabase**:

- Register: `emailRedirectTo: \`${window.location.origin}/auth/callback\`` (`web/app/register/page.tsx:52`).
- Forgot password: `redirectTo: \`${window.location.origin}/auth/callback?type=recovery\`` (`web/app/forgot-password/page.tsx:36`).
- Callback handler: `web/app/auth/callback/route.ts` exchanges the code for a session and redirects to `next` (or `/dashboard/profile`).

**Allowlist status — NOT conclusively proven (M3, unchanged).** The Management API returned 403 for the auth config read, so the allowlist was never directly read. The only evidence is that a re-sign-up with `redirect_to` `http://localhost:3000/auth/callback` reached the email-send step (429 rate-limit, twice) rather than a redirect error — consistent with it being allowed, but the rate limit stopped it before a 200. **Owner step after the domain decision (§8 step 7):** Supabase Dashboard → Authentication → URL Configuration → Redirect URLs must include the production callback URL (`https://<production-domain>/auth/callback`) **in addition to** the local-dev one. Until that entry exists, email confirmation and password recovery will fail on the production domain even though everything else works. This is a post-deploy verification item (§9 S8), not a done item.

## 6. Branch strategy and preview deployments — PENDING

**Production branch — PENDING (owner step, after the PR).** The Vercel project should build from **`officerpath-phase2-web`** now (the branch on GitHub, head `461c9a2`, and the branch this report is committed on). After the Workstream B PR merges `officerpath-phase2-web` → `main`, the project must be switched to **`main`** (Vercel Dashboard → Project → Settings → Git → Production Branch) and `render.yaml`'s `branch:` updated to `main` in a follow-up commit (Workstream D §12). Do **not** delete `officerpath-phase2-web` until the first deploy from `main` is verified (Workstream B §3). The switch is an owner step, only after the first deploy from `officerpath-phase2-web` is verified.

**Preview deployments — PENDING (mechanism is env-only).** Vercel creates a preview deployment for every pull request by default. Environment variables are scoped per environment (Production / Preview / Development), and the mechanism is **env-only** (deployment-checklist B6): a preview uses whatever `NEXT_PUBLIC_API_URL` / Supabase values are set on its Preview scope. There is no code-level guard separating preview from production data. Safe options, in order:

1. **Leave Preview-scope variables unset.** The preview then falls back to `http://127.0.0.1:8000` for the API and throws the explicit "Supabase is not configured" error on any auth page — an honest "not connected" state, and no production data is ever touched. (This is the recommended default until a staging backend exists.)
2. Point Preview-scope variables at a **staging backend** — none exists, so this is not available today.
3. **Do NOT** copy the Production-scope values into Preview scope: a preview built with production values would talk to production Supabase and the production Render backend, and a test account created there would be real data.

**No preview deployment has ever run** (no Vercel project exists). The first preview will appear with the first PR after the project is connected — the owner must check its Preview-scope variables before sharing its URL.

**Auth guard — VERIFIED (code):** `web/proxy.ts` (Next.js 16 renamed `middleware` to `proxy`) refreshes the Supabase session on every matched request and redirects `/dashboard/*` and `/admin/*` without a session to `/login?next=<path>`, and `/login`/`/register` with a session to `/dashboard/profile`. The dashboard/admin layouts re-check the session server-side as well — the proxy is a convenience gate, never the only check (the file's own comment says so). Matcher: `/dashboard/:path*`, `/admin/:path*`, `/login`, `/register`, `/forgot-password`, `/auth/reset-password`. The matcher is an edge-middleware surface on Vercel (see §7).

## 7. Vercel Hobby free-tier limits — what matters for this app

Sourced from current public sources on 2026-11-23 (Vercel's own pricing/docs as summarised by multiple independent 2026 comparisons). Limits change; these are a snapshot, not a contract — the owner should confirm them on Vercel's pricing page at project creation.

| Limit (Hobby, $0) | Value | Relevance to OfficerPath |
|---|---|---|
| Permitted use | **Personal, non-commercial projects only** | **The most important limit.** Phase 3 is a paid product (subscriptions, Easypaisa/JazzCash) — a commercial launch **cannot stay on Hobby**; it needs Pro ($20/seat/month) or another host. The 20–30 student free beta is non-commercial and fits Hobby. This must be decided before the commercial launch, not after it. |
| Fast Data Transfer | 100 GB/month | Far above the beta's traffic. |
| Edge Requests | 1M/month | Far above the beta's traffic. |
| Function invocations | 1M/month | The app's server surface is one route handler + edge middleware + partial-prerender pages (§1) — invocations will be low. |
| Build execution | 6,000 minutes/month; 1 concurrent build; 100 deployments/day | The local build takes ~16 s; 6,000 minutes is ample. One concurrent build means rapid successive pushes queue — not a problem at this pace. |
| Function duration | **Sources disagree:** 10 s (older 2026 sources) vs 60 s (newer 2026 sources); one Nov 2026 source cites 300 s, which appears to describe Fluid/Pro behaviour. | **Not the constraint for this app:** the only function is the auth callback (a fast code exchange) and the middleware (session refresh). The long work (OCR, ~20 min at Render free's 0.1 CPU) runs on Render, never here. Recorded as a disagreement rather than a settled number. |
| No overage purchase | Hitting a Hobby limit can pause that feature until the next 30-day period | A limit hit is a pause, not a bill — but it is also not self-healing within the month. Watch the usage dashboard during the beta. |

No card is required for the Hobby tier (doc 06 §3, §7). If Vercel asks for a card at signup, **stop and report to the owner** before entering any payment details (same rule as Render, Workstream D §2).

## 8. Deployment steps (owner, Dashboard, in order)

Prerequisites (must already be true — see the other workstreams): GitHub push done (head `461c9a2`, 2026-11-23); Render backend deployed first, because `NEXT_PUBLIC_API_URL` needs the Render service URL (Workstream D §10); Supabase migrations per Workstream C (015 live, 016 DONE, 018 → 017 re-run → Alembic 0001–0009 still pending); domain decision made (§4); CI first run checked (Workstream B).

1. **Vercel Dashboard → Add New → Project → Import Git Repository** → `hasankhan62742-beep/officerpath-pdf-engine` (public repo). Vercel needs its own GitHub connection — the owner authorises it in the import flow. (The GitHub App used for the push is a different integration; it does not connect Vercel.)
2. **Set Root Directory to `web`** (§1 — the single most likely mistake; the repo root is Python).
3. Confirm the Framework Preset is **Next.js** (auto-detected), Build Command `npm run build`, Install Command `npm install`, Output Directory default. No `vercel.json` is needed.
4. Confirm the build Node version satisfies Next.js 16's minimum (Node 20.9+); the repo builds locally on Node v24.22.1.
5. **Set the four Production-scope environment variables** (names only — values come from the owner's records, never from this report):
   - `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL (public identifier).
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` — anon key from Supabase Dashboard → Project Settings → API (publishable).
   - `NEXT_PUBLIC_API_URL` — the Render backend service URL from Workstream D step 7.
   - `NEXT_PUBLIC_SITE_URL` — the production origin chosen in §4 (must be the real origin, not the placeholder).
   
   Leave **Preview-scope** variables unset (§6) unless a staging backend exists. Do not put any other variable here — the frontend must never receive a service-role key or a database URL (§3).
6. **Deploy.** The first build is the first proof the Vercel build works (the local build in §2 is not that proof — Vercel's machine, cache, and Node version are different).
7. **After the first deploy, before announcing the URL:**
   a. Render Dashboard → set `CORS_ALLOWED_ORIGINS` to the exact production origin (Workstream D §5.1 — until then the frontend's API calls are blocked by CORS).
   b. Supabase Dashboard → Authentication → URL Configuration → Redirect URLs → add `https://<production-domain>/auth/callback` (§5).
   c. Confirm the deployed site's `NEXT_PUBLIC_SITE_URL` matches the origin actually served (canonical/OG/sitemap derive from it — §4).
8. **Run the smoke test in §9** (owner, his phone for the upload flow — the STOP CONDITION, Workstream F).

## 9. Smoke-test checklist after deploy

| # | Check | Expect |
|---|---|---|
| S1 | Home page loads at the production URL | 200, tagline "Prepare Smarter. Practice Better. Become Exam Ready.", no console errors |
| S2 | `/login`, `/register`, `/pricing`, `/features` load | 200, `X-Robots-Tag: noindex, nofollow` present on `/login` and `/register` |
| S3 | `/dashboard` while logged out | 307 → `/login?next=/dashboard` |
| S4 | Register a real account → confirmation email → click link | Lands on `/auth/callback` and then `/dashboard/profile` (proves §5's allowlist entry works) |
| S5 | Dashboard loads after login | Real values from the database (no invented numbers); upload page reachable |
| S6 | Upload PPSC-66 through the web upload (owner phone) | Job queued → done; 41 questions / 41 answered (STOP CONDITION evidence — Workstream F; note Render's ~30–60 s cold start and ~20 min OCR at 0.1 CPU — use the async job model and poll) |
| S7 | API call from the production origin | Succeeds (proves §8 step 7a CORS is set); a CORS preflight failure here means the Render value is missing, not a frontend bug |
| S8 | Forgot-password flow | Email arrives; reset link lands on `/auth/callback?type=recovery` and the reset page works (proves the recovery redirect entry) |
| S9 | Canonical/OG/sitemap | `curl` the home page: `canonical` and `og:url` show the real production origin, not `officerpath.ai`; `/sitemap.xml` lists the real origin |
| S10 | Vercel usage dashboard | Bandwidth, invocations, and build minutes all near zero after the smoke test (baseline for the beta) |

## 10. Failure modes and rollback

| Failure | Signature | Response |
|---|---|---|
| **Wrong Root Directory** | Build fails immediately (Vercel tries to build the Python repo root: no `package.json` at root) | Project → Settings → General → Root Directory → `web`; redeploy. |
| **Missing env vars** | Build **passes** (§2) but auth pages throw "Supabase is not configured" at request time, and API calls go to `http://127.0.0.1:8000` | Set the four Production-scope variables (§8 step 5) and redeploy — a settings edit alone does nothing, because `NEXT_PUBLIC_*` is inlined at build time (§3). |
| **CORS failure** | Browser preflight rejected from the production origin | `CORS_ALLOWED_ORIGINS` not set on Render (Workstream D §5.1) — set it in the Render Dashboard; not a frontend bug. |
| **Auth redirect failure** | Confirmation/reset link lands on a Supabase error page ("redirect URL not allowed" or similar) | Production callback URL missing from Supabase's allowlist (§5) — add it in the Supabase Dashboard. |
| **Placeholder domain live** | Canonical/OG/sitemap show `officerpath.ai` | `NEXT_PUBLIC_SITE_URL` was left as the placeholder — set it to the real origin and redeploy (§4). |
| **Hobby limit hit** | Vercel pauses the affected feature until the next 30-day period (§7) | Reduce usage or move to Pro; there is no pay-to-continue on Hobby. |
| **Preview touched production data** | Test rows appear in the production database | Preview-scope variables were set to production values — clear them (§6) and delete the test rows; previews must stay unset until a staging backend exists. |

**Rollback:** Vercel Dashboard → project → Deployments → pick the previous GOOD deployment → **⋯ → Promote to Production** (instant rollback; the previous build is re-served, no rebuild). Verify after rollback: home loads, login page loads, `/dashboard` (logged out) → 307 `/login?next=%2Fdashboard`, `X-Robots-Tag: noindex, nofollow` present on `/login`. **No data step** — the frontend never migrates data, so its rollback is data-safe by construction (rollback-runbook §1). If the frontend was never deployed, there is nothing to roll back — the "rollback" is simply not deploying.

## 11. Open owner decisions — PENDING / REQUIRES OWNER APPROVAL

| # | Decision | Status | Who |
|---|---|---|---|
| E1 | Deploy the Vercel project at all (import, root directory, env vars, first deploy) | PENDING | Owner (Dashboard) |
| E2 | Canonical domain: Vercel subdomain vs custom domain (`officerpath.ai` or another) | REQUIRES OWNER APPROVAL | Owner — blocks Render CORS + Supabase allowlist (§4) |
| E3 | Branch switch to `main` after the PR merges | PENDING — only after the first deploy from `officerpath-phase2-web` is verified | Owner |
| E4 | Preview-scope env vars: leave unset (recommended) vs staging backend (none exists) | PENDING | Owner |
| E5 | Commercial launch hosting: Hobby forbids commercial use (§7) — Pro ($20/seat/month) or another host before Phase 3 launch | REQUIRES OWNER APPROVAL — Phase 3 decision, not a beta blocker | Owner |
| E6 | `npm audit` (owner machine) and the first CI run | PENDING — Workstream B §7 | Owner |

---

## Appendix — evidence (commands run in this workstream)

- `git log --oneline -3` → head `d221c1b` (Workstream D), branch `officerpath-phase2-web`; `git status --short` → only the two untracked 018 files (by design, Workstream C)
- `web/next.config.ts` read in full (security headers, no CSP, X-Robots-Tag on private routes, Turbopack Tailwind rule); `web/package.json` read in full (Next 16.4.6, React 19.3.0, scripts dev/build/start/lint); `ls web/` → no `vercel.json`
- `cat web/.env.example` → exactly the four `NEXT_PUBLIC_*` names, placeholders only; `ls -l web/.env.local` → mode 0600 (values never printed)
- `grep -rn "process.env"` over `web/app web/components web/lib web/proxy.ts web/next.config.ts` → exactly 4 variables, all `NEXT_PUBLIC_` (`lib/site.ts:14`, `lib/supabase/server.ts:12-13`, `lib/supabase/client.ts:11-12`, `lib/api.ts:9`, `proxy.ts:26-27`)
- `grep -rn "SERVICE_ROLE\|service_role\|DATABASE_URL"` over `web/app web/components web/lib web/proxy.ts web/next.config.ts web/public` → **no matches** (exit 1)
- `grep -rni "vercel"` over `web/app web/components web/lib web/proxy.ts web/next.config.ts web/package.json` → **no matches** (exit 1)
- `grep -rln '"use server"' web/app web/lib` → **no matches** (exit 1)
- `find web/app -name 'page.tsx' | wc -l` → **34**; `find web/app -name 'route.ts'` → `app/auth/callback/route.ts` only
- `grep -rn "NEXT_PUBLIC_SITE_URL\|officerpath.ai" web/app web/components web/lib web/proxy.ts web/public` → placeholder in `lib/site.ts:14` (fallback), `public/robots.txt:13`, `public/sitemap.xml` (all `<loc>` + own comment), `web/app/layout.tsx` + `web/app/page.tsx` (metadataBase/canonical/OG/JSON-LD via `SITE_URL`)
- `web/proxy.ts` read in full (guard rules, matcher, session refresh; `NEXT_PUBLIC_SUPABASE_URL`/`ANON_KEY` only)
- `web/lib/supabase/client.ts` + `server.ts` read in full (explicit throw when URL/anon key missing; service-role key never appears)
- `web/lib/api.ts` read (browser calls the engine directly; `NEXT_PUBLIC_API_URL` fallback `http://127.0.0.1:8000`)
- `npm run build` (first run, output piped through `tail` — exit code not relied on) then re-run unpiped to `/tmp/e-build.log`: `npm run build > /tmp/e-build.log 2>&1; echo BUILD_EXIT=$?` → **BUILD_EXIT=0**; 37 routes in the output (`grep -c "^├\|^└" /tmp/e-build.log` → 37); Node v24.22.1, npm 10.9.4
- `npx tsc --noEmit` → **TSC_EXIT=0** (unpiped); `npm run lint` → **LINT_EXIT=0** (unpiped)
- `git status --short` after the build → only the two untracked 018 files (`.next/` gitignored: root `.gitignore:26`, `web/.gitignore:17`)
- Deployment-checklist §B read in full (B1 build PASS, B5 domain OPEN, B6 preview env-only, B7 Vercel project NOT DONE, B8 Netlify fallback documented); rollback-runbook §1 read (Promote to Production)
- M3 report redirect-allowlist section read (allowlist not conclusively proven; Management API 403 for auth config read)
- Vercel Hobby limits (web search, 2026-11-23): 100 GB Fast Data Transfer, 1M Edge Requests, 1M function invocations, 6,000 build minutes, 100 deployments/day, 1 concurrent build, 200 projects, personal non-commercial use only, no overage purchase — agreed across multiple 2026 sources; function duration disagrees across sources (10 s vs 60 s vs 300 s) and is recorded as such in §7

**Workstream E conclusion:** the frontend is a standard, portable Next.js 16 App Router build — it builds cleanly locally (exit 0, tsc 0, lint 0, 34 pages / 37 routes), reads exactly four `NEXT_PUBLIC_*` variables, contains no service-role key, no database URL, and no Vercel-specific code. It is ready to deploy the moment the owner acts. What is **not** ready is everything around it: no Vercel project exists; the canonical domain is an unconfirmed placeholder that also blocks Render's CORS value and Supabase's redirect allowlist; the redirect allowlist itself is unproven; and the Hobby tier's **non-commercial** term means the paid Phase 3 launch cannot stay on it. Deployment itself remains PENDING.
