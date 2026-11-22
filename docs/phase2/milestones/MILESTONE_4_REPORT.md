# Milestone 4 — Dashboard + Document Upload (Phase 2)

**Status: DONE, parent verification pending.** Branch `officerpath-phase2-web`,
local only, no push, no deploy, no paid services. All numbers below were
measured in this run; anything not measured is labelled UNVERIFIED.

## What was built

### Engine — new endpoints (GAP-2 DONE)

| Endpoint | Behaviour |
|---|---|
| `GET /api/v1/documents` | Paginated list, owner-only. `limit` 1–100 (default 20), `offset` ≥ 0, optional `?status=` filter over the six job statuses. Returns `{documents, total, limit, offset}`; each item carries its latest job plus `questions`/`answered` from the job's `result_summary` when done (`null` before). Soft-deleted documents excluded. |
| `GET /api/v1/documents/{id}` | Document + latest job (with `result_summary`) + stage history. Other user / unknown id: 404. |
| `DELETE /api/v1/documents/{id}` | Soft delete (`deleted_at`); a queued/processing job is cancelled first (`job_cancelled: true`). Local bytes deleted best-effort; bucket bytes never touched. Returns `{document_id, deleted: true, job_cancelled}`. |
| `GET /api/v1/dashboard/summary` | Real numbers only: `documents_total`, `jobs_by_status` with all six keys (zeros included), `recent_documents` (newest 5). No test-result numbers — none exist until M7/M8. |

New files: `app/api/v1/documents.py`, `app/api/v1/dashboard.py`,
`app/schemas/dashboard.py`, `app/services/documents.py`; both routers
registered in `app/main.py`. Repositories extended
(`DocumentRepository.find_by_id`, `list_by_user`, `soft_delete`, `count`;
`JobRepository.find_latest_by_document_ids`, `count_by_status_for_user`);
`find_by_user_and_path` / `find_by_user_and_sha256` now ignore soft-deleted
rows, so re-upload after delete creates a fresh document.

### Engine — bucket download for register jobs (M3 deferred item, done)

- `app/integrations/supabase_storage.py` gained
  `download_bucket_bytes(bucket, storage_path, *, service_client=None)`
  using the service-role client only, with classified errors: 503
  `storage_unavailable` (no service client), 500 `storage_bucket_missing`
  (message names migration 016), 500 `storage_object_missing`, 500
  `storage_error` (generic; original message not leaked). Verified against
  installed supabase 2.15.3 / storage3 0.11.3.
- `app/workers/processor.py`: `claim_next_job` NO LONGER skips
  `{"source":"register"}` jobs (the ADR-011 M3 skip is retired);
  `process_job` gained injectable `bucket_downloader` (default = real
  `download_bucket_bytes(settings.documents_bucket, path)`); a
  register-source job with no local bytes downloads once into the local
  write-once cache before parsing; download failure fails the job via the
  existing `_fail_job` path with the named storage error.
  `app/workers/runner.py` passes `bucket_downloader` through.
- **Live status: UNVERIFIED-live.** The live `pdf-documents` bucket is
  still missing (migration 016 written, NOT applied — owner step). The
  download path is proven locally only (see § Bucket-download proof).
  Migration 016 was NOT applied live and no bucket was created live.

### Frontend — dashboard, upload, documents (`web/`)

- `/dashboard` (replaces the M3 redirect to `/dashboard/profile`; profile
  stays a sub-page): stat cards (Documents, Processing, Done, Failed) from
  the summary endpoint, recent-documents list, active-jobs alert, honest
  "Tests — coming in Milestone 6" card (no fake numbers). Polls the summary
  while a job is active (5 s, backoff to 15 s after 2 min) and stops on
  terminal states. Honest empty state ("No documents yet — upload your
  first paper").
- `/dashboard/upload`: drag-and-drop + file picker, client validation
  (PDF/JPG/PNG, ≤ 100 MB/file, ≤ 20 files), per-file results with a live
  `JobTracker` per job, 1 file → single endpoint (per-file progress),
  2–20 → batch endpoint (one rate-limit charge), 429 shown as a plain
  message, rejected files listed with reasons.
- `/dashboard/documents`: real list with status filter, table
  (Title/Type/Size/Questions/Status/Actions), pagination, per-row
  View/Retry/Cancel/Delete (delete via confirm modal — real endpoint).
- `/dashboard/documents/[id]`: metadata, job status + stage list +
  result counts (Questions/Answered/Needs review) when done, engine
  error when failed, Retry/Cancel/Delete, honest "Questions and answers
  arrive in Milestone 5" note. Polls while the job is active.
- `web/lib/api.ts`: `JobStatus`, `DocumentJob`, `DashboardDocument`,
  `DocumentDetail`, `DashboardSummary`, `getDashboardSummary`,
  `listDocuments`, `getDocument`, `deleteDocument`, `getJob`,
  `cancelJob`, `retryJob`, `getSessionToken()`, XHR `uploadFile` /
  `uploadBatch` with real progress. `web/lib/utils.ts`: `formatBytes`,
  `formatDateTime`.
- New components: `components/dashboard/job-status-badge.tsx`,
  `job-tracker.tsx` (TanStack `useQuery`, 5 s → 15 s backoff, stops on
  terminal), `dashboard-nav.tsx`, `document-detail-client.tsx`.
  Dashboard layout rewritten (real nav, max-w-5xl).
- **Login redirect fix (M3 leftover found by the E2E):**
  `web/app/login/page.tsx` defaulted post-login to
  `/dashboard/profile` because in M3 `/dashboard` redirected there.
  Now defaults to `/dashboard`.

## Bugs found by measuring (all fixed in this milestone)

1. **Alembic 0003 has no server defaults on `student_profiles`
   timestamps — POST /api/v1/me 500 on any migration-built DB.**
   0003 creates `created_at`/`updated_at` NOT NULL with NO server
   default, while the model declares `server_default=func.now()`. The
   suite never caught it because conftest builds tables from the MODELS
   (which carry the default). Only `alembic upgrade head` produces the
   broken DDL: `sqlite3.IntegrityError: NOT NULL constraint failed:
   student_profiles.created_at`. **Fix: Alembic 0004**
   (`alembic/versions/0004_m4_profile_timestamps.py`, batch mode so it
   works on SQLite and Postgres) adds `DEFAULT now()`/`CURRENT_TIMESTAMP`
   to both columns; downgrade drops the defaults (no data deleted, no
   row-count refusal). 0001 already had the defaults right — only 0003
   was wrong. Regression test added:
   `test_alembic_head_db_accepts_profile_and_job_inserts` — upgrades a
   scratch file to head, then inserts a profile (no timestamps, exactly
   as the service does), a document, a job and a stage, asserting all
   four commit with timestamps filled in by the database.
   Related: a bare `alembic upgrade head` on a fresh DB still needs the
   015-owned `documents`/`jobs` tables first — that is the documented
   deploy order (015, then Alembic; `docs/deploy-render.md`), not a
   bug. The E2E setup replicates it by pre-creating those two tables
   from the models, exactly as `test_schema.py` does.
2. **`/dashboard/documents/[id]` build failure (Next 16 Cache
   Components).** `useParams` on a route without `generateStaticParams`
   suspends, and the shared header's `usePathname` has no value at
   prerender time for a dynamic id. `export const dynamic =
   "force-dynamic"` is rejected under `cacheComponents`. **Fix (per the
   Next 16 docs in `node_modules/next/dist/docs/`):** the page is now
   a server wrapper that awaits `params` and renders the client detail
   view inside `<Suspense>`, plus `export const instant = false` on
   that route only (opts it out of static-shell validation).
3. **Login landed on `/dashboard/profile`** (see above).

## Gates (all measured in this run)

| Gate | Result |
|---|---|
| `npm run build` (final state, real `.env.local`) | PASS — compiled, 22 routes (`/dashboard`, `/dashboard/documents`, `/dashboard/documents/[id]`, `/dashboard/profile`, `/dashboard/upload` all ◐ partial prerender) |
| `npm run lint` | PASS — 0 problems |
| `npx tsc --noEmit` | PASS — exit 0 |
| `pytest` (full) | **529 passed, 0 failed, 301.27 s** (510 M3 baseline + 19 new) |
| `ruff check` | PASS — clean (1 import-sort issue in the new test found and fixed with `--fix`) |
| `ruff format --check` | PASS — 201 files |
| `mypy` CI gate (`app/db app/pipeline app/storage`) | SUCCESS — 68 files |
| Secrets scan (`web/app web/components web/lib web/proxy.ts` + changed engine files) | **0 offenders** (grep for JWT-shaped tokens / service-role / `sk-` / `AKIA…`). Note: the same pattern matches dummy JWTs inside `web/node_modules` third-party test fixtures (zod) and base64 source maps — those are dependency files, not our code or keys. |

New engine tests (19): `test_documents.py` (9), `test_bucket_download.py`
(3), `test_storage_download.py` (6), `test_job_store_unification.py`
updated (old skip test replaced by
`test_worker_claims_oldest_job_including_register`), `test_schema.py`
+1 (0004 regression). Two real bugs found and fixed during the engine
work: a stage query passing a string job id to a UUID column
(`AttributeError: 'str' object has no attribute 'hex'`), and a SQLite
`created_at` second-precision tie breaking FIFO order in the
unification test (register job backdated 1 minute).

## End-to-end upload proof

Fixture (never modified): `~/workspace/officerpath-ai/test-fixtures/ppsc66/ppsc-current-affairs-40-mcqs.pdf`
(CA40, 6 pages, digital, 35,985 bytes).

### API-level (exact calls the frontend makes)

| Step | Call | Result |
|---|---|---|
| 1. Sign in (stub GoTrue, see below) | `POST /auth/v1/token?grant_type=password` | 200, access token |
| 2. Create profile | `POST /api/v1/me` `{full_name: "M4 E2E Test"}` | 200, profile with `created_at`/`updated_at` set (failed 500 before the 0004 fix) |
| 3. Upload | `POST /api/v1/documents/upload` (multipart `file`) | 200 `stored`; document `823f96ef-2aac-4057-a7dd-06cb36a6390b`, job `c2c60a10-0269-42c0-8aa5-54cf2f28f5f4` `queued`; 6 pages, all `digital` |
| 4. Worker | in-process worker (`WORKER_ENABLED=true`) claims job | `queued` → `processing` → `done` |
| 5. Terminal | `GET /api/v1/jobs/{id}` | `done`; created 10:57:03.045 → started 10:57:05.716 → completed 10:57:06.016 (**≈ 3.0 s** end to end); `retry_count` 0, `error` null |
| 6. Dashboard summary | `GET /api/v1/dashboard/summary` | `documents_total` 1, `jobs_by_status.done` 1 (all other statuses 0), recent document `questions` **40**, `answered` **40** |
| 7. Document detail | `GET /api/v1/documents/{id}` | job `done`, 10 stages all `done` (`uploaded`, `validated`, `queued`, `uploaded`, `validated`, `extracted`, `answers_detected`, `matched`, `scored`, `completed`) |
| 8. Delete | `DELETE /api/v1/documents/{id}` | `{deleted: true, job_cancelled: false}` (job already done); summary back to `documents_total` 0 |

The 40/40 count is the number the engine actually returned, not the
expected one — it matches the fixture's 40 MCQs. The table photo path
was proven in the suite instead of the browser:
`test_table_photo_upload_completes_through_worker` (repo golden fixture,
md5 `927ccc5e7d0bb2b7c4d68a4f3526b28d`) → `done`, 0 questions / 2
pending — the same result as the M8 sync parse.

### Browser-level (Playwright Chromium, real UI)

Harness (test-only, in `/tmp/m4-e2e/`, never committed, never in
product code): a stub GoTrue server implementing the slice of the
GoTrue API the app and engine need (`POST /auth/v1/token`
password + refresh, `GET /auth/v1/user`, `POST /auth/v1/logout`,
minimal `/rest/v1/*` returning `[]` for the engine's `/health`
probe), one fixed test user
(`11111111-1111-1111-1111-111111111111`, `m4-e2e@example.com`).
Engine on :8001 (fresh SQLite DB: Alembic 0001→0004, 015 tables
pre-created from the models), web on :3000 (production build
pointed at the stub), Chromium 1254. Full script run green
(`ok: true`):

| Step | Observed |
|---|---|
| Logged-out `/dashboard` | 307 → `/login?next=/dashboard` |
| Log in via the real form | 326–719 ms → lands on `/dashboard` |
| Empty dashboard | "No documents yet", Documents 0, Processing 0 |
| Upload CA40 via the UI (choose file → "Upload 1 file") | Accepted in 392–1,056 ms; job tracker shows **Done 5.7–6.4 s** after the click |
| Dashboard populated | Documents **1**, Done **1**, recent document listed with 40 questions |
| Documents list | Row present (PDF, 35.1 KB, date, Done) |
| Document detail | **Done**, Questions **40**, Answered **40**, Needs review **0**, stage list |
| Log out | Lands on home; `/dashboard` redirects to login again |
| Mobile 360×800 | `/dashboard`, `/dashboard/upload`, `/dashboard/documents`: `scrollWidth` 360 = `innerWidth` 360, **zero horizontal overflow** on all three |

## Dashboard proof (populated + empty)

- **Empty:** after deleting the only document via the API, the summary
  returned `documents_total` 0 with all job counts 0, and the browser
  dashboard showed "No documents yet" with 0/0 stat cards.
- **Populated:** after the browser upload, the dashboard showed
  Documents 1, Done 1, and the real recent document (see table above).
  Both states were recorded in the same run, before/after the upload.

## Bucket-download proof (local only)

- `test_bucket_download.py` (3 tests): register job downloads via the
  injected downloader into the local cache and completes; missing
  bucket → job fails `storage_bucket_missing`; missing object → job
  fails `storage_object_missing`; no service client → 503
  `storage_unavailable`.
- `test_storage_download.py` (6 tests): `download_bucket_bytes`
  classification against the real storage3 client surface.
- `test_job_store_unification.py`: the worker now claims
  register-source jobs (old skip retired).
- **Live status: UNVERIFIED-live** — no live bucket exists (016 not
  applied), so the download path cannot be proven against live
  Supabase. Do NOT treat the local proof as a live proof.

## Environment quirks found during the E2E (harness notes, not product bugs)

- This VM sets egress-proxy env vars; `httpx` (via supabase-py)
  fails to construct the Supabase client (`InvalidURL: Invalid port:
  ':1]'`) because it mis-parses the bracketed IPv6 entries in
  `no_proxy`. Workaround for local E2E runs only: `NO_PROXY='*'
  no_proxy='*'` + empty proxy vars for the engine/Node processes.
- The browser origin is `http://127.0.0.1:3000` while the engine's
  default CORS origin is `http://localhost:3000` — the E2E engine was
  started with both origins. The stub echoes the request `Origin`
  (localhost or 127.0.0.1) and allows the `x-supabase-api-version`
  header supabase-js sends.

## Honest limitations

- **Live bucket UNVERIFIED-live** (016 not applied — owner step).
  Register-job download is local-only proof.
- **Live Auth confirm→login→profile loop still NOT live-proven**
  (M3 blocker, unchanged): the only test user is the unconfirmed M3
  one; anonymous sign-in is disabled on the live project. The browser
  E2E above proves the flow against a stub, not live Supabase.
- iPhone Safari / real device NOT verified (Playwright Chromium only);
  Lighthouse not run (M9/M10).
- The single-transaction-across-document+job-create wart from ADR-011
  ("M4 follow-up") was NOT taken up — carried forward.
- `docs/API.md` and doc 02 updated for GAP-2; the M4 report is this
  file. `CHANGELOG.md` / `TEST_REPORT.md` remain stale (M4 / M0) —
  not updated in this milestone.

## What is NOT done (later milestones)

- Extraction results UI / question bank (M5), test builder (M6), exam
  interface (M7), results/analytics (M8), admin + security + SEO (M9),
  QA + deployment readiness (M10), payments/subscriptions (Phase 3).

## Files changed

15 modified + 15 new (untracked) files, branch
`officerpath-phase2-web`, no commit yet at report time:

- **Modified:** `app/database/sqlalchemy_repositories.py`,
  `app/integrations/supabase_storage.py`, `app/main.py`,
  `app/tests/conftest.py`, `app/tests/test_job_store_unification.py`,
  `app/tests/test_schema.py`, `app/workers/processor.py`,
  `app/workers/runner.py`, `docs/API.md`,
  `docs/phase2/02-api-integration-map.md`,
  `web/app/dashboard/layout.tsx`, `web/app/dashboard/page.tsx`,
  `web/app/login/page.tsx`, `web/lib/api.ts`, `web/lib/utils.ts`
  (850 insertions, 77 deletions across the 15 modified files).
- **New:** `alembic/versions/0004_m4_profile_timestamps.py`,
  `app/api/v1/dashboard.py`, `app/api/v1/documents.py`,
  `app/schemas/dashboard.py`, `app/services/documents.py`,
  `app/tests/test_bucket_download.py`, `app/tests/test_documents.py`,
  `app/tests/test_storage_download.py`,
  `web/app/dashboard/documents/page.tsx`,
  `web/app/dashboard/documents/[id]/page.tsx`,
  `web/app/dashboard/upload/page.tsx`,
  `web/components/dashboard/dashboard-nav.tsx`,
  `web/components/dashboard/document-detail-client.tsx`,
  `web/components/dashboard/job-status-badge.tsx`,
  `web/components/dashboard/job-tracker.tsx`.
- No new packages installed (Next.js 16.4.6, React 19.3.0,
  TypeScript 5.9.3, Tailwind 4.3.3, TanStack Query 5.108.2 —
  unchanged from M2/M3).

## Gate verdict

**GATE MET** — all frontend and engine gates pass, the upload→done→
dashboard flow is proven at API level and in the real browser UI
(empty and populated states), the bucket-download path is proven
locally with live status honestly labelled UNVERIFIED-live. The two
real bugs found by measuring (Alembic 0003 defaults, `[id]`
prerender) are fixed with regression coverage. The remaining open
items are owner steps (migration 016, live Auth confirmation loop,
M3 test-user deletion), not code failures.
