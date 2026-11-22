# Milestone 3 Report — Authentication + Profiles + Dual Job-Store Resolution

**Branch:** `officerpath-phase2-web` (local only — no push, no deploy, no paid services)
**Date:** 2026-11-22
**Status:** DELIVERED with one honest blocker (see §6) — the confirm→login→profile loop
could not be completed from the VM because the confirmation email went to a
test mailbox nobody can read, and no service-role key exists to confirm the
test user any other way. Everything else in the M3 scope is built, gated and
proven below. Nothing in this report is claimed beyond what was measured.

## 1. Live Supabase verification (Part A — done FIRST, before auth code)

Project `officerpath-ai`, ref `gliebuyyjguxrwdfuakz`. Verified via the Supabase
Management API (registered `custom.supabase` connector; token scoped to this
project only, Project Settings Read + Edge Functions Read/Write) and anon-key
PostgREST / GoTrue probes.

| What was checked | How | Result |
|---|---|---|
| Project status / region / Postgres | Management API `GET /v1/projects/{ref}` | **ACTIVE_HEALTHY**, `ap-southeast-1` (Singapore), Postgres 17.12, created 2026-11-19 |
| Auth service health | `GET /auth/v1/health` with anon key | HTTP 200, GoTrue v2.198.0 (401 without key is expected — gateway requires apikey) |
| Migration 015 tables live? | PostgREST `GET /rest/v1/{table}?select=id&limit=1` with anon key for 9 tables | **YES — 015's tables ARE live** (correction to the M0/M1 record). `profiles`, `documents`, `jobs`, `test_results`, `activation_codes`, `payments`, `waitlist`, `sent_notifications`, `redeem_attempts` all return HTTP 200 `[]`. Control probe of a nonexistent table returns 404 PGRST205, so the 200s mean the tables really exist. Anon reads return 0 rows everywhere — consistent with owner-only RLS, but also with empty tables: **RLS on/off NOT directly proven** |
| Storage bucket `pdf-documents` | `GET /storage/v1/bucket` + `/bucket/pdf-documents` | **MISSING.** Bucket list is `[]`; direct GET → 404 `NoSuchBucket`. 015 was applied partially (tables yes, bucket no) |
| Auth settings: sign-up allowed? | `GET /auth/v1/settings` (public GoTrue settings) | `disable_signup = false` → sign-up ALLOWED |
| Auth settings: email confirmation? | Same | `mailer_autoconfirm = false` → confirmation **REQUIRED** (no session until the user confirms) |
| Auth settings: full config read | Management API `GET /config/auth` | **BLOCKED — 403, token lacks `auth_config_read`.** SMTP provider, email templates, redirect-URL allowlist NOT directly readable |
| SQL access | Management API `POST /database/query` | **BLOCKED — 403, token lacks `database_read`.** No SQL access at all |
| Service-role key | Management API `GET /api-keys` | **BLOCKED — 403, token lacks `api_gateway_keys_read`.** No service-role key obtainable — admin-confirm and admin-delete of a test account are impossible from the VM |
| Edge Functions | Management API `GET /v1/projects/{ref}/functions` | 5 ACTIVE: `issue-code` v3, `send-notification` v3, `redeem-code` v3, `payment-alert` v2 (verify_jwt=False), `delete-account` v2 (verify_jwt=True) |
| Anon key source | — | Extracted (by a script that never prints it) from the local Flutter repo `~/workspace/officerpath-ai/admin/config.js`; written to `web/.env.local` (0600, gitignored). Publishable by design; never printed, never committed. No service-role key was ever read or written |

**Not done live (forbidden by the brief / not approved):** migration 015 was NOT
re-applied; no live data was deleted or modified; no live auth setting was
changed. Migration 016 (bucket only) is written, NOT applied — owner step via
Dashboard. The two test leads in the CRM project (`abdulqadeerml-crm`) were not
touched — different project.

## 2. What was built

### 2.1 Authentication (real Supabase Auth, no fakes)
- Installed `@supabase/ssr@0.12.7` + `@supabase/supabase-js@2.119.2`.
- `web/lib/supabase/client.ts` (browser) + `web/lib/supabase/server.ts`
  (server, cookie-based, same session both sides). Env vars only; the
  service-role key is forbidden anywhere in `web/` (see §8).
- `web/app/login/page.tsx`: real `signInWithPassword`, `?next=` return URL,
  Supabase's own error messages shown as-is ("Invalid login credentials",
  "Email not confirmed" + a plain-language hint for the latter).
- `web/app/register/page.tsx`: real `signUp` with `emailRedirectTo` =
  current origin + `/auth/callback`, and profile fields in `options.data`
  (full_name, phone, preferred_exam, education_level). Success state is
  "Check your email" — no session is faked. "User already registered" and
  other Supabase errors surface verbatim.
- `web/app/forgot-password/page.tsx`: real `resetPasswordForEmail`
  (redirect to `/auth/callback?type=recovery`). Neutral sent state (does not
  reveal whether the email exists).
- `web/app/auth/reset-password/page.tsx` (new): real `updateUser`
  with the recovery session; honest error when the link expired.
- `web/app/auth/callback/route.ts` (new): exchanges the email-link code for
  a session; `type=recovery` → reset-password page; otherwise creates the
  engine profile from the sign-up metadata (best effort — a failure is logged
  server-side and the profile page creates it on first visit instead).
  Missing/invalid code → `/login?error=...`, never a crash.
- `web/proxy.ts` (new, Next 16 — NOT deprecated `middleware.ts`): refreshes
  the session on every matched request; `/dashboard/*` without a session →
  `/login?next=<path>`; `/login` or `/register` with a session →
  `/dashboard/profile`. Matcher: `/dashboard/:path*`, `/login`, `/register`,
  `/forgot-password`, `/auth/reset-password`.
- Header session state (`web/components/layout/auth-section.tsx`): signed-in
  shows the user's email + Profile link + real Log out; signed-out shows
  Log in / Start Your Preparation; synced via `onAuthStateChange`.
- All M2 "not connected" copy is gone from login/register/forgot-password.
  (The contact page's honest "not connected to a backend yet" label remains —
  the contact form is out of M3 scope.)

### 2.2 Profiles (doc 03 §2.1)
- Engine: `StudentProfile` model + Alembic `0003_m3_student_profiles`
  (creates `student_profiles`, unique `user_id`, index `(user_id, created_at)`;
  downgrade REFUSES when rows exist — verified by test).
- `GET/POST 201/PATCH /api/v1/me` (`app/api/v1/me.py`, `app/services/profiles.py`,
  `app/schemas/me.py`): JWT user id only, per-user 404s, 409 `profile_exists`
  on duplicate create. 8 tests, all passing.
- **Profile creation, decided:** explicit insert, not a DB trigger. Doc 03
  allowed either; a trigger needs a live SQL change the owner has not
  approved and the Management API token has no database-write scope, so it
  cannot be applied from here. The flow is: (1) `/auth/callback` creates the
  profile from sign-up metadata on confirmation; (2) `/dashboard/profile`
  creates it (prefilled from metadata) if it does not exist yet. Both paths
  write the same engine endpoint.
- `web/app/dashboard/profile/page.tsx`: real protected page — loads the
  profile from the engine with the session Bearer token, edits persist via
  POST/PATCH, reload re-reads from the database. Engine unreachable → honest
  error, no fake values.
- `web/app/dashboard/layout.tsx`: server-side session re-check (defence in
  depth — the proxy is never the only check). `/dashboard` itself redirects
  to `/dashboard/profile` — no dead placeholder page. Full dashboard (stats,
  documents) is M4.

### 2.3 Dual job-store resolution (ADR-011)
- `docs/adr/ADR-011-dual-job-store-resolution.md` (ACCEPTED): evaluated
  independently against the code — the split was worse than M1 stated.
  **Finding:** one database, two access paths, one hard conflict. The engine
  DB is the same Postgres Supabase hosts; the live `public.jobs` check
  constraint allows only
  `queued/uploading/processing/done/failed/cancelled`, but the engine wrote
  `completed` (`processor.py:222`, `review.py:117`). Traced consequence
  (code-reading): async worker `process_job` sets `completed` → IntegrityError
  → `_fail_job` raises PendingRollbackError (session never rolled back) → job
  stuck in `processing` forever. **With the M7 vocabulary, the engine could
  not complete a single job against the live database.**
- **Decision:** (1) engine DB (SQLAlchemy) is the SINGLE access path for
  documents + jobs; PostgREST repositories deleted (`app/database/repositories.py`
  removed; Supabase clients stay for Auth verification only); (2) vocabulary
  unified on **`done`** (the live constraint, the `JobStatus` enum and every
  stage status already use it; `PipelineStage.COMPLETED` is a stage NAME,
  unchanged); (3) register-source jobs marked at creation
  (`result_summary: {"source": "register"}`) and skipped by the worker's
  `claim_next_job` until M4 wires bucket download; upload-source jobs
  (`{"source": "upload"}`) ARE claimable; (4) migration 016 creates only the
  missing bucket. Rejected: union view (never two databases), keep
  `completed` + alter the live constraint (leaves production broken until the
  owner applies it), dual-write, PostgREST-path-only fix.
- **Consequences recorded in ADR-011:** engine now REQUIRES `DATABASE_URL`
  for document/job/profile endpoints (503 `database_unavailable` otherwise;
  PostgREST-only degraded mode retired); the Phase 1 completion report's
  state machine (`queued → processing → completed`) is now stale for the
  terminal value — the report is a historical record, NOT rewritten, ADR-011
  is the correction; no live client consumed `completed` (Flutter toggle
  calls sync parse/parse-image only; web frontend did not exist yet).
- **Measured subtlety:** `result_summary["source"].is_(None)` does NOT work
  in SQLAlchemy — it renders `JSON_QUOTE(JSON_EXTRACT(...)) IS NULL`, false
  even for NULL summaries (proven by a debug script against SQLite). The
  claim filter uses the null-safe coalesce form instead.
- Tests reworked + new: `test_job_store_unification.py` (6),
  `test_profiles.py` (8), `test_cors.py` (4); `test_jobs`/`test_register`/
  `test_upload`/`test_security` rewritten onto the engine DB. Two real bugs
  found by the rework and fixed: `GET /jobs/does-not-exist` raised ValueError
  → 500 (now 404 via `_as_uuid`); `/health` 503 in tests without the minimal
  table-probe stub (verified against pristine M2 commit).

### 2.4 CORS (deferred from M2)
- FastAPI `CORSMiddleware` in `app/main.py`: origins from
  `CORS_ALLOWED_ORIGINS` env (default `http://localhost:3000`),
  `allow_credentials=True`, methods GET/POST/PATCH/PUT/DELETE/OPTIONS,
  headers Authorization + Content-Type. Never `"*"`. Documented in
  `.env.example`.

## 3. Gate results (all measured in this run)

| Gate | Result |
|---|---|
| Web `npm run build` | **PASS** — 19 routes; `ƒ Proxy (Middleware)` detected; `/dashboard` + `/dashboard/profile` partial prerender (session check) |
| Web `npm run lint` | **PASS — 0 problems** |
| Web `npx tsc --noEmit` | **PASS — exit 0** |
| Engine pytest (full) | **510 passed, 12 warnings, 307.22s** (492 M7 baseline + 18 new M3 tests: 6 unification + 8 profiles + 4 CORS) |
| Engine ruff check + format | **PASS — 193 files clean** |
| Engine mypy CI gate (`mypy app/db app/pipeline app/storage`) | **PASS — 68 files** |
| Alembic 0003 | upgrade head → downgrade −1 → upgrade head OK on SQLite; `student_profiles` columns verified; downgrade refuses with rows present |

## 4. End-to-end auth proof (local, against REAL live Supabase)

Test addresses: `officerpath-m3-test@example.com` (reserved domain — see
below) and `officerpath.m3.test@gmail.com` (routable test address; the owner's
real email was NOT used).

| Step | Actual result |
|---|---|
| Sign-up `officerpath-m3-test@example.com` | **HTTP 500 `unexpected_failure`: "Error sending confirmation email"** (error_id `01a202bf-15f6-7b0a-923c-30c69dd7ea9c`). Retried — same 500. The user was NOT created (a retry did not say "already registered"). Cause: `example.com` is a reserved domain with no MX — the mailer cannot deliver to it. This is domain-specific, NOT a project-wide mailer failure (proven by the next row) |
| Sign-up `officerpath.m3.test@gmail.com` | **HTTP 200, no error** — user created, confirmation email dispatched. Dispatch proven independently: a re-send minutes later returned **HTTP 429 `over_email_send_rate_limit`** ("only request this after 46 seconds") and login was rejected as below |
| Login BEFORE confirming (gmail test user) | **HTTP 400 "Email not confirmed"** — the confirmation gate works exactly as designed (`mailer_autoconfirm=false`) |
| Confirm the email | **BLOCKED.** The confirmation link went to `officerpath.m3.test@gmail.com`, a mailbox nobody can read. No service-role key exists (Management API 403, §1), so admin-confirm via API is impossible and there is no SQL access to flip the flag. The confirm→login→profile loop could NOT be completed from the VM |
| Protected page, no session | **PROVEN.** `GET /dashboard/profile` → **307 → `/login?next=%2Fdashboard%2Fprofile`**; `GET /dashboard` → **307 → `/login?next=%2Fdashboard`**; `GET /login` → 200 |
| Callback without code | **PROVEN.** `GET /auth/callback` → **307 → `/login?error=missing_code`** |
| Login / protected page / logout AFTER confirming | **NOT PROVEN — blocked by the confirmation step above.** The code paths are built, typechecked and built successfully; the live run is the remaining proof |
| Redirect-URL allowlist (`http://localhost:3000/auth/callback`) | **NOT conclusively proven.** Re-sign-up with that `redirect_to` reached the send step (429 rate-limit, twice) rather than a redirect error, which is consistent with it being allowed — but the rate limit stopped it before a 200. Owner check: Dashboard → Authentication → URL Configuration → Redirect URLs must include `http://localhost:3000/auth/callback` (local dev) and the production callback URL |

**Test account left in live Auth:** `officerpath.m3.test@gmail.com` exists
UNCONFIRMED. It cannot be deleted from the VM (no service key; the
`delete-account` Edge Function needs the user's own JWT, which needs
confirmation — circular). **Owner step: Dashboard → Authentication → Users →
`officerpath.m3.test@gmail.com` → Delete.** The `example.com` address was
never created, so nothing to delete there.

## 5. Profile round-trip proof

- **Engine side — PROVEN by tests:** `test_profiles.py` 8/8 — create→get
  round-trip, duplicate POST 409, PATCH round-trip (unchanged fields persist),
  PATCH without profile 404, per-user isolation (user B gets 404 on A's
  profile), validation 422s, auth-required 401s.
- **Browser side — NOT PROVEN — blocked by the confirmation step (§4).**
  No session token is obtainable for the test user, so the profile page's
  live fetch could not run. The page code is typechecked and built; the
  callback-creation path and the create-on-404 fallback are both implemented.
  This is the same single blocker as §4, not a second one.

## 6. Job-store proof

- **Tests — PROVEN:** `test_job_store_unification.py` 6/6 — a register job is
  visible from BOTH `GET /api/v1/jobs/{id}` and `GET /api/v1/async-jobs/{id}`
  (same id/status) and vice versa; terminal status is `done` from both
  endpoints; the worker claims an upload job but skips a register job
  (register stays `queued` with `{"source": "register"}`); source markers
  correct for register/upload.
- **Live engine (local run, SQLite DB, real Supabase env) — PROVEN:**
  `/health` 200 `{"status":"ok","supabase":"ok","database":"ok",...}`;
  OpenAPI lists both `/api/v1/jobs/{job_id}` and `/api/v1/async-jobs/{job_id}`;
  both return **401 without a token** (auth enforced identically).
- **Before/after:** before M3, `GET /api/v1/jobs/{id}` read Supabase
  PostgREST (`public.jobs`, vocabulary `done`) while the async-jobs path read
  the engine DB (vocabulary `completed`) — two different rows for the same
  job, and the engine's `completed` would have violated the live check
  constraint. After M3, both read the same engine-DB row with vocabulary
  `done`.

## 7. CORS proof (live engine, local run)

| Probe | Result |
|---|---|
| Preflight `OPTIONS /api/v1/me`, `Origin: http://localhost:3000` | **200** — `access-control-allow-origin: http://localhost:3000`, `allow-credentials: true`, methods `GET, POST, PATCH, PUT, DELETE, OPTIONS` |
| `GET /api/v1/me`, `Origin: https://evil.example.com` | **401, NO `access-control-allow-origin` header** — disallowed origin gets nothing |
| `GET /api/v1/me`, no token | **401** — auth enforced |

## 8. Secrets scan

- `grep` over `web/` (excluding `node_modules`, `.next`): **0 JWTs in source**;
  the only `service-role` mention is the "must NEVER appear" warning in
  `web/.env.example`. `web/.env.local` is gitignored (`web/.gitignore:34`),
  mode 0600, holds the real project URL + anon key + `NEXT_PUBLIC_API_URL`.
- `web/.env.example` now shows the real project URL (public identifier —
  same value already in the engine's `.env.example`); the anon key stays a
  placeholder with a note on where to get it.
- No real Supabase keys, no service-role key, no JWT in the repo. Engine
  `.env` files: none exist (only `.env.example`).

## 9. Honest limitations

1. **The confirm→login→profile live loop is unproven** (§4–§5) — one
   blocker: no readable test mailbox + no service-role key. The owner (or a
   run with a mailbox he controls) must click the confirmation link for
   `officerpath.m3.test@gmail.com`, or delete that user and re-test with a
   mailbox he can read. Until then the browser auth flow is built + gated
   but not live-proven end to end.
2. **RLS on/off NOT directly proven** (§1) — anon reads return 0 rows, which
   fits owner-only RLS and also fits empty tables. Needs a Dashboard check
   (Authentication → Policies) or a signed-in probe.
3. **Redirect-URL allowlist not conclusively proven** (§4) — evidence points
   to allowed, owner to confirm in Dashboard.
4. **E2E environment quirk (not a code bug):** this VM's `NO_PROXY` contains
   bracketed IPv6 entries (`[::1]`…) which httpx cannot parse — the engine's
   Supabase client failed to construct (`InvalidURL: Invalid port: ':1]'`)
   until `NO_PROXY` was sanitised for the E2E run. No code change was made
   for this; Render will not have this variable.
5. **Transient egress flakiness:** two live Auth calls dropped mid-response
   (`RemoteDisconnected`, `IncompleteRead`) and succeeded on retry. VM proxy
   behaviour, not Supabase.
6. **iPhone Safari / real device: UNVERIFIED** (as in M2). Playwright mobile
   check not re-run in M3 — no layout/CSS changed except the header auth
   area.
7. **Bucket still missing live** — migration 016 written, not applied
   (owner step). Register-source jobs are therefore skipped by the worker
   until M4 wires bucket download (by design, ADR-011).

## 10. What is NOT done

- Full dashboard (stats, documents) — **M4**.
- Document upload — **M4** (register-source jobs skipped by the worker until
  bucket download is wired; upload-source jobs are claimable now).
- Test builder, exam interface, results/analytics — **M6–M8**.
- Admin foundation, security hardening pass, SEO — **M9**.
- QA + deployment readiness — **M10**.
- Payments/subscriptions — **Phase 3, not Phase 2**.
- Migration 016 live apply; test-account deletion; redirect-URL allowlist
  confirmation — **owner steps** (§4, §9).

## 11. Files changed

- **Engine (ADR-011 + CORS + profiles):** 16 files modified, 1 deleted
  (`app/database/repositories.py`), 10 new (incl. `app/database/sqlalchemy_repositories.py`,
  `app/api/v1/me.py`, `app/services/profiles.py`, `app/schemas/me.py`,
  Alembic 0003, migration 016 ×2, 3 new test files).
- **Web:** 7 files modified (login, register, forgot-password, header,
  providers, `package.json`, `package-lock.json`), 10 new (`proxy.ts`,
  `lib/supabase/client.ts`, `lib/supabase/server.ts`, `lib/api.ts`,
  `components/layout/auth-section.tsx`, auth callback route, reset-password
  page, dashboard layout/page/profile).
- **Docs:** 4 modified (`docs/API.md`, `docs/phase2/02-api-integration-map.md`,
  `docs/phase2/03-database-extension-plan.md`, `docs/migration-015-apply.md`
  (M3 live-state correction)) + 2 new (ADR-011, this report).
- **Other:** repo-root `.env.example` modified (CORS + DATABASE_URL notes).
- **Total: 51 files changed, +2,993/−468** (commit `0ece74c`).
- **Versions installed:** `@supabase/ssr@0.12.7`, `@supabase/supabase-js@2.119.2`.
  No other dependency changes.
