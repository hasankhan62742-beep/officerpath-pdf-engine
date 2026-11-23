# Milestone 9 — Admin Foundation, Security + SEO (Phase 2)

**Branch:** `officerpath-phase2-web` · **Status:** DONE, parent verification pending ·
**Scope:** GAP-9 (notifications, in-app only) + GAP-10 (admin foundation) per
`docs/phase2/07-milestone-execution-plan.md` §M9, `docs/phase2/05-security-architecture.md` §4,
`docs/phase2/03-database-extension-plan.md` §2.6/§5. Local only — no push, no deploy,
no paid services, no live Supabase changes (migrations 016/017 still unapplied,
the unconfirmed M3 test user untouched).

## 1. What was built

### Engine — notifications (GAP-9, Alembic 0009)

- `notifications` table exactly per doc 03 §2.6: id UUID PK, user_id UUID NOT NULL,
  type Text CHECK over the six doc-03 types (`upload_done` / `upload_failed` /
  `review_needed` / `test_submitted` / `result_ready` / `subscription_change`),
  title/body Text NOT NULL, link Text NULL (in-app route), is_read Bool default
  false, created_at. Indexes on (user_id, created_at) and (user_id, is_read,
  created_at). Downgrade refuses while rows exist.
- **Doc drift noted:** the plan says "0006 in M9 for notifications" — that is
  STALE; 0006 was M6 tests, 0007 M7 exam, 0008 M8 collections. 0009 is the next
  sequential revision (also recorded in the migration docstring).
- **M9 decision (documented in code):** user_id is NOT NULL — per-user rows only,
  no broadcast NULL. (Doc 03 §2.6 allowed NULL for broadcast; M9 chose per-user
  only because no broadcast sender exists yet.)
- Rows are written by the real flows, in the same transaction as the triggering
  write: worker success → `upload_done` (+ `review_needed` only when the parse
  left questions pending); worker `_fail_job` → `upload_failed`; exam submit →
  `test_submitted` + `result_ready` (placed before the commit that also survives
  the concurrent-submit IntegrityError rollback). **In-app only — no email is
  ever sent or claimed.**
- API: `GET /api/v1/notifications` (owner-only, newest first, `?unread_only`,
  returns `unread_count`) + `PATCH /api/v1/notifications/{id}/read` (idempotent;
  a foreign id is 404).

### Engine — admin foundation (GAP-10)

- Admin = a claim on the Supabase Auth user (`app_metadata.is_admin`), read from
  the VERIFIED JWT only. `verify_jwt` now returns `{id, email, app_metadata}`
  (non-dict metadata coerced to `{}`).
- `require_admin` dependency: non-admin → **404** `not_found` on every admin
  route (same no-leak pattern as every other owner check — no 403 that confirms
  existence), with a warning log carrying the user id only.
- A top-level `is_admin`/`role`/`plan` key in a JSON request body is IGNORED by
  handlers and logged as a warning (method + path only, never body/token);
  non-JSON bodies are skipped; a logging failure never fails the request.
  (Proven by test: `is_admin` in a POST /me body is ignored + logged, and the
  user stays non-admin.)
- 6 routes under `/api/v1/admin/*`, all paginated, all real engine-DB rows:
  `overview` (real counts), `users` (profiles + per-user counts — **no email
  field: the engine DB stores no student email**), `documents` (latest job
  status), `jobs` (error text + `error_rows`, `?status=` filter), `errors`
  (`processing_errors`, newest first), `questions` (`?search=` +
  `?validation_status=` filters; `correct_index` from the latest answer's
  resolved label, −1 = unknown).
- **OpenAPI 41 → 49 paths** (measured live: `GET /openapi.json` returns 49).
- Admin audit logging decision (documented in code): admin is read-only in M9,
  so no `audit_log` writes exist yet (reads would flood it); denied attempts are
  logged by `require_admin`.

### Engine — security hardening (found by measuring, §6)

- **Session answer-key leak (M7 design flaw, fixed in M9):** `GET
  /api/v1/tests/{id}/session` returned the full `SnapshotItem` — including
  `correct_index` and `answer_source` — to the student's browser WHILE the test
  was in progress, so the key was readable from the network tab. Fixed with a
  separate `SessionSnapshotItem` (no key, no source; only `is_unknown`, which is
  all the take page needs to disable options). The test-detail and result
  endpoints still return the full `SnapshotItem` with the key (post-test review
  / creator's own preview) — the split is asserted by test so a future refactor
  cannot merge the two shapes back together.
- Security headers middleware on the engine: X-Content-Type-Options nosniff,
  X-Frame-Options DENY, Referrer-Policy strict-origin-when-cross-origin,
  Permissions-Policy camera/microphone/geolocation off, CSP `default-src 'none';
  frame-ancestors 'none'` (skipped on /docs, /redoc, /openapi.json where Swagger
  UI needs its scripts).
- CORS final: `CORS_ALLOWED_ORIGINS` is exact (never `*`, credentials only for
  the allowed origins); a disallowed origin gets no CORS headers (simple request
  and preflight — preflight returns 400).

### Frontend

- Notifications: `/dashboard/notifications` (real list, All/Unread filter,
  mark-read mutation invalidating both query keys) + a live unread-count badge
  on the dashboard nav (hides on missing token/fetch failure).
- Admin: `/admin/*` — layout with a server guard (no session → /login;
  non-admin → /dashboard; UX only, the API 404 is the real enforcement) +
  robots noindex metadata; pages for Overview, Users, Documents, Jobs (status
  filter + link to errors), Errors, Questions (search + status filter + links to
  `/dashboard/questions/[id]` for the evidence trail). All client components
  with real API data, pagination, empty/error states.
- `proxy.ts`: `/admin` added to the matcher + guard.
- SEO: canonical + `openGraph.url` on all 11 public pages (home, about,
  features, how-it-works, exam-preparation, pricing, privacy, terms via
  metadata; contact via a new server `web/app/contact/layout.tsx` because the
  contact page is a client component and cannot export metadata). Home has
  JSON-LD Organization + WebSite (real facts only — name, URL, description,
  contact email `hello@abdulqadeerml.com`; no invented ratings/counts/
  partnerships). **No FAQ JSON-LD — no public page has a real FAQ section**
  (verified by grep; the one "features" match was a false lead). Canonical
  follows `NEXT_PUBLIC_SITE_URL` (defaults to `https://officerpath.ai`); under
  the E2E harness stub env it renders `http://localhost:3000`, which is
  correct for that environment.
- noindex: `robots: {index:false, follow:false}` metadata in the dashboard +
  admin layouts, plus `X-Robots-Tag: noindex, nofollow` headers in
  `next.config.ts` for /dashboard, /dashboard/*, /admin, /admin/*, /login,
  /register, /forgot-password, /auth/* (headers are the mechanism for the auth
  pages, which are client components).
- `web/public/robots.txt` now disallows /dashboard/, /admin/, /auth/, /api/
  (sitemap still lists the 11 public pages — verified current).
- `next.config.ts` `headers()`: security headers on all paths
  (X-Content-Type-Options, X-Frame-Options DENY, Referrer-Policy,
  Permissions-Policy). **No CSP on the web app — documented choice: a strict CSP
  breaks Next.js' own inline runtime scripts; clickjacking is covered by
  X-Frame-Options DENY.**
- PWA: `web/app/manifest.ts` (name/short_name/description, start_url `/`,
  display standalone, theme `#ea580c`) + PNG icons generated with PIL from the
  existing `icon.svg` design (orange #ea580c rounded square, white bold "OP"):
  `web/public/icon-192.png` (3,587 bytes), `icon-512.png` (10,778 bytes).
  Served at `/manifest.webmanifest` (200, `application/manifest+json`).
  **Honest scope: manifest only — no service worker, no offline support,
  install prompt NOT claimed.**

### Dependency audit

- Engine: `pip-audit` 2.9.0 → **0 known vulnerabilities** in the engine venv.
- Web: `npm audit` **BLOCKED on the VM** — 403 `policy_denied` from the managed
  registry proxy (even against registry.npmjs.org directly). Recorded as an
  owner step (run on his machine); no results invented. (Lighthouse itself
  later installed fine via npx — the block is specific to the audit path, not
  all registry traffic — but the audit command itself still returns 403, so the
  audit result remains "not run", not "clean".)

## 2. Gate table (exact numbers)

| Gate | Result |
|---|---|
| pytest (full) | **609 passed, 0 failed** in 840.80s — measured on the code including the session-leak fix (M8 baseline 593 + 15 M9 admin/security tests + 1 session-leak test; the pre-fix run was 608/0). The live-bank fix + its test came after that run: they pass in isolation (17/17 in `test_admin_security.py`, ruff/format clean) and the full E2E ran green against the final code. A final full run (expected 610) is in flight at commit time but starved by VM contention (parallel video work, load ~10, pytest at ~2% CPU after 36 min; session `proc_9a8511fe89f1`) — the parent's verification re-run is the authority for the final total. |
| ruff check | clean (229 files) |
| ruff format --check | clean (229 files) |
| mypy gate (`app/db app/pipeline app/storage`) | SUCCESS (68 files) |
| npm run build (real `web/.env.local`) | PASS, compiled 17.2s; 34 page routes (27 at M8 + 7 new: 6 admin + 1 notifications), 39 generated entries |
| npm run lint | exit 0, 0 problems |
| npx tsc --noEmit | exit 0 |
| OpenAPI paths | 49 (41 at M8 → 49) |
| pip-audit | 0 known vulnerabilities |
| npm audit | BLOCKED on VM (403 `policy_denied`) — owner step, not run |
| Secrets scan (web/) | 0 offenders (no JWTs / service-role keys; one warning comment only) |
| `web/.env.local` | untouched, real values (0600, mtime 2026-11-22 12:45) |

## 3. Unit tests (17 new, `app/tests/test_admin_security.py`)

Coverage: `verify_jwt` returns
app_metadata; admin routes 401 without/invalid token; non-admin 404 (code
`not_found`) on all 6 admin routes; `is_admin` in a POST /me body ignored +
logged (caplog) + user stays non-admin; admin sees real rows (overview users
1/documents 1/jobs 1/jobs_by_status {done:1}/questions 3/errors 0; users list
has no `email` key); question filters (search "capital" → 1;
`validation_status=answered` → 3, `unreviewed` → 0 — the store writes the MCQ
status, never the model default); jobs error surface (error_rows 1, errors
endpoint lists it); notifications CRUD + ownership (2 rows, unread_count 2,
mark-read idempotent, B sees 0 + PATCH → 404, unauthenticated 401); submit
writes exactly `test_submitted` + `result_ready` (hand-checked body "1.75 out
of 3.0 (58.33%)" for 2 correct/1 incorrect); cross-user 404s
(document/test/result/collection-delete); CORS disallowed origin gets no ACAO
header (preflight 400; allowed origin `http://localhost:3000` gets its header
back); security headers present on /health, CSP skipped on /docs; Alembic 0009
fresh-DB table + downgrade-to-0008 drops it + downgrade refuses with rows;
**session withholds the answer key** (no `correct_index`/`answer_source` in any
snapshot, `is_unknown` false for scored / true for unknown, while the creator's
test-detail preview still returns the key); **admin questions count is the live
bank only** (a soft-deleted document's question leaves the overview + list
counts, while the document stays in the admin audit list).

Two M7 tests were updated for the session-shape change (they read
`correct_index` from session snapshots): `test_session_returns_snapshots_in_order_and_no_responses_yet`
now asserts `is_unknown` (exactly one of four) + absence of the key, and
`test_submit_hand_checked_marks` maps snapshots via the seed's question ids
instead of the session key. Both pass.

## 4. E2E proof (`~/workspace/m9-e2e/`, M8 bank copy — 91 rows)

Harness: M8 `engine.db` copied (never the original), Alembic upgrade head adds
0009, GoTrue stub :54399 (student `m6-e2e@example.com` + admin
`m9-admin@example.com`, `app_metadata.is_admin: true`), engine :8001
(`WORKER_ENABLED=true`), web :3000 (stub env overrides, `.env.local` never
overwritten). Final run: `api_e2e.py` **ALL CHECKS PASSED** (run 5; runs 1–4
found and fixed the harness/script issues in §6, and each left real rows behind
— the final counts below include those rows, quoted exactly as measured).

### (a) Admin — student denied, admin sees real rows

- Unauthenticated `GET /api/v1/admin/overview` → **401**. An unknown
  student-prefixed token → **404** (stub limitation: the stub maps ANY
  non-admin token to the student and never 401s a present token — the
  invalid-token → 401 path is proven by the unit tests, not the stub E2E).
- Student token → **404 `not_found`** on all 6 admin routes, exact bodies
  quoted in `api-proof.json` (`admin_denied_as_student`).
- Admin overview (final run): users 1, documents 6, jobs 6, questions **91**,
  tests 23, results 10, errors 1. Admin users list: total 1, first "M9 E2E
  Student", **no `email` key**. Admin documents 6, jobs 6, errors 1.
- Admin questions search "capital" → **1**; list total **91**; overview
  questions == student bank total == **91**.

### (b) Notifications — real upload, real failure, real submit

- CA40 delete → re-upload (delete first, so the M6 dedup replay does not
  swallow it): job done, **40 questions / 40 answered / 0 pending**; notification
  rows after upload: `upload_done` present, `review_needed` correctly ABSENT
  (clean 40/40 parse).
- Corrupt upload (`%PDF-1.4` + garbage): job **failed, error "Failed to open
  stream"**; `upload_failed` notification present. (Final totals include the
  earlier runs' rows: 4× `upload_done` + 2× `upload_failed`.)
- Test built from the bank (5 scored picks), started, answered from the BANK
  key (never the session), submitted: **5.0 / 5.0, 100.0%**;
  `test_submitted` + `result_ready` rows present.
- Mark-read: idempotent (second PATCH still 200, `is_read: true`);
  `unread_count` **8 → 7**. Admin `GET /api/v1/notifications` → total **0**;
  admin PATCH of the student's notification id → **404**.

### (c) Security — cross-user, CORS, headers, session key

- Admin GET of the student's document / test / result → **404** each.
- CORS: disallowed origin `https://evil.example.com` → NO
  `access-control-allow-origin` on a simple request; preflight → **400**, no
  CORS headers. Allowed origin `http://localhost:3000` → its header back.
- Engine security headers on /health: X-Content-Type-Options `nosniff`,
  X-Frame-Options `DENY`, Referrer-Policy
  `strict-origin-when-cross-origin`, Permissions-Policy
  `camera=(), microphone=(), geolocation=()`, CSP `default-src 'none';
  frame-ancestors 'none'` — all exact.
- **Session snapshots carry no answer key** (5 snapshots checked live:
  no `correct_index`, no `answer_source`, `is_unknown: false` throughout).

### (d) SEO / headers (curl, live harness)

- Home: canonical `http://localhost:3000` (harness stub env — follows
  `NEXT_PUBLIC_SITE_URL`; real env defaults to `https://officerpath.ai`),
  og:title "OfficerPath AI — Prepare Smarter. Practice Better. Become Exam
  Ready.", og:description, og:url, twitter `summary_large_image` + title +
  description, **2 JSON-LD blocks**, robots meta `index, follow` (public page
  correctly indexable).
- `/dashboard` (logged out) → **307** `/login?next=%2Fdashboard` +
  `X-Robots-Tag: noindex, nofollow`. `/login` → `X-Robots-Tag: noindex,
  nofollow`. `/admin` (logged out) → **307** `/login?next=%2Fadmin` +
  `X-Robots-Tag: noindex, nofollow` (after the §6 fix). `/admin/users` → 307 +
  tag.
- `robots.txt` disallows `/dashboard/`, `/admin/`, `/auth/`, `/api/`;
  `sitemap.xml` lists the 11 public pages (home, about, features,
  how-it-works, exam-preparation, pricing, contact, login, register, privacy,
  terms). `/manifest.webmanifest` → 200, `application/manifest+json`.

### (e) Lighthouse 13.6.0 (harness, localhost — real measured scores)

| Page | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|
| Home `/` | **73** | **96** | **100** | **100** |
| Features `/features` | **60** | **94** | **100** | **100** |

Home drivers: LCP 1.5s (score 1), TBT **1,790ms** (score 0.1 — the drag),
CLS 0 (score 1), Speed Index 2.1s, Interactive 4.5s. No load-opportunities
flagged — the TBT is JS execution/hydration under the VM's throttled CPU, not
a single asset. These are localhost-harness numbers, not production numbers;
performance tuning is M10 work.

## 5. Browser proof (Playwright, stub GoTrue + local engine)

`browser_e2e.mjs` **ALL CHECKS PASSED** (two runs; run 2's numbers reflect run
1's mark-read). Highlights from `browser-proof.json`:

- Student login via real form (2,971ms) → `/admin` redirects to `/dashboard`.
- Nav badge reads **"Notifications7"** (run 1; 6 in run 2) — the real unread
  count from the API.
- Notifications page shows all 8 real titles ("Result ready: M9 E2E exam
  test", "Test submitted: M9 E2E exam test", "Processing failed: bad.pdf",
  "Processing complete: ppsc-current-affairs-40-mcqs.pdf" ×4, "Processing
  failed: bad.pdf" ×2). Mark-read in the UI: 7 → 6 buttons (run 1), 6 → 5
  (run 2); server `unread_count` decremented to match (7 → 6, then 6 → 5).
- Admin login via real form (1,723–1,868ms) → `/admin` overview shows real
  counts: Students **1**, Documents **8**, Questions in bank **91**, Jobs **8**,
  Tests **24**, Results **11**, Processing errors **2**, Notifications sent **8**,
  Jobs by status Done **6** / Failed **2**. (Documents/jobs/tests/results grew
  across the five API runs + two browser runs — all real rows.)
- `/admin/users` shows "M9 E2E Student". `/admin/questions` search "capital"
  renders the bank row.
- Mobile 360px: **0px overflow** on `/admin`, `/admin/users`,
  `/dashboard/notifications`.

## 6. What was found by measuring (bugs + fixes)

1. **Session answer-key leak (M7, fixed in M9).** The exam session returned
   `correct_index` + `answer_source` mid-exam. Fixed with `SessionSnapshotItem`
   / `is_unknown` (engine schema + service + web `ExamSessionSnapshot` +
   `exam-client.tsx`); 2 M7 tests updated to the new contract; 1 new regression
   test; live E2E assertion added.
2. **Admin questions counted soft-deleted documents' questions (131 vs 91).**
   The E2E cross-check (admin overview vs student bank) caught it: after a
   delete + re-upload the admin overview said 131 while the bank said 91.
   Fixed: `overview.questions` and `list_questions` now join `documents` with
   `deleted_at IS NULL` (the live bank); the documents audit totals still
   include soft-deleted rows and the admin documents list still shows them with
   `deleted_at`. 1 new regression test.
3. **Bare `/admin` lacked `X-Robots-Tag`.** `/admin/:path*` does not match the
   bare `/admin` redirect (measured: `/admin/users` had the tag, `/admin` did
   not — while bare `/dashboard` did). Fixed with explicit exact-path entries
   for `/admin` and `/dashboard` in `next.config.ts`; re-verified live
   (307 + tag).
4. **E2E/script issues (not product bugs):** the stub maps any non-admin token
   to the student (invalid-token 401 stays unit-test-only); `GET /jobs/{id}`
   returns `JobResponse` with NO `result_summary` (the async-jobs endpoint has
   it — the E2E polls that); bank list items use `question_id`, not `id`;
   profile creation returns 409 `profile_exists` on re-runs; the admin
   questions page is newest-first 20/page, so the browser check uses the real
   search box.
5. **Pre-existing M7 edge, OBSERVED not fixed (M10):** re-submitting IDENTICAL
   bytes to `POST /api/v1/async-jobs/parse` 500s — `IntegrityError: UNIQUE
   constraint failed: documents.user_id, documents.content_hash` at
   `async_jobs.py:123` (proven in `logs/engine.log`, run 4). The
   `/documents/upload` path handles the replay (M6); the async path never got a
   dedup check. The E2E varies the corrupt payload per run to stay on the
   supported path. Fixing the async dedup is a design decision for M10.

## 7. Honest limitations

- `npm audit` not run (VM registry 403) — owner step on his machine.
- No email in the admin users list (the engine DB stores no student email;
  adding it needs service-role `auth.admin.list_users` — out of M9 scope).
- No service worker / offline support (manifest + icons only); install prompt
  NOT claimed.
- Invalid-token → 401 proven by unit tests only (stub limitation, §4a).
- iPhone Safari / real device unverified (M9/M10); Lighthouse scores are
  localhost-harness numbers (Performance 73/60 is TBT-bound under VM
  throttling), not production numbers.
- Urdu preservation not E2E-proven in M9 (no Urdu fixture in the bank runs);
  inferred-flag + Q&A-pair card rendering still unit-test-only (0 inferred in
  the fixtures).
- Live Supabase unchanged (016 bucket + 017 unapplied, M3 auth-loop blocker +
  unconfirmed test user still owner steps).
- The `test_admin_security.py` count: the file holds **17 tests** (15 original
  M9 tests + session-leak + live-bank). The measured full-suite total is 609
  (which includes 16 of them); the 17th passes in isolation and a final full
  run (expected 610) is in flight at commit time, starved by VM contention —
  see the pytest row in §2. The parent's verification re-run is the authority
  for the final total.

## 8. What is NOT done (not M9)

- M10 QA/deployment. Payments/subscriptions (Phase 3). Email notifications
  (provider-gated, future). No live migration application. No push, no deploy.
- The async-jobs re-submit 500 (§6.5) is flagged for M10, not fixed here.
- Admin `audit_log` writes: none yet (admin is read-only in M9).
- Performance tuning for the Lighthouse TBT numbers (M10).

## 9. Files changed

Engine (new): `alembic/versions/0009_m9_notifications.py`,
`app/api/v1/admin.py`, `app/api/v1/notifications.py`, `app/schemas/admin.py`,
`app/schemas/notifications.py`, `app/services/admin.py`,
`app/services/notifications.py`, `app/tests/test_admin_security.py`.
Engine (modified): `app/db/models.py` (Notification), `app/main.py` (routers +
2 middlewares), `app/security/dependencies.py` (`require_admin`),
`app/integrations/supabase_auth.py` (app_metadata), `app/services/exam.py`
(submit notification hook + session snapshot shape), `app/schemas/exam.py`
(`SessionSnapshotItem`), `app/workers/processor.py` (upload notification
hooks), `app/tests/conftest.py` (admin token), `app/tests/test_exam.py`
(2 tests updated to the new session contract).
Web (new): `web/app/admin/` (layout + 6 pages), `web/app/dashboard/notifications/`,
`web/app/manifest.ts`, `web/app/contact/layout.tsx`, `web/public/icon-192.png`,
`web/public/icon-512.png`, `web/components/admin/admin-nav.tsx`.
Web (modified): `web/lib/api.ts` (notifications + admin + `ExamSessionSnapshot`),
`web/components/dashboard/dashboard-nav.tsx` (Notifications + badge),
`web/components/dashboard/exam-client.tsx` (`is_unknown`),
`web/app/page.tsx` + 7 public pages (canonical/OG/JSON-LD),
`web/app/dashboard/layout.tsx` (noindex), `web/proxy.ts` (/admin guard),
`web/next.config.ts` (headers + exact-path noindex entries),
`web/public/robots.txt`.
Docs: `docs/API.md` (notifications + admin sections, session shape, submit
hook), `docs/phase2/02-api-integration-map.md` (GAP-9 + GAP-10 DONE, GAP-6
session amendment, §6 correction).
Harness (never committed): `~/workspace/m9-e2e/` — `api_e2e.py`,
`browser_e2e.mjs`, `gotrue_stub.py`, `setup.sh`, `api-proof.json`,
`browser-proof.json`, `lighthouse-home.json`, `lighthouse-features.json`,
`engine.db` (M8 bank copy + M9 runs).
