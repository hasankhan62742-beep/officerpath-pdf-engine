# Migration Runbook — OfficerPath AI Phase 2 (M10)

**Status:** documentation only. Nothing here runs anything. Every step
below is an OWNER step in the Supabase Dashboard or on the owner's
machine — no agent applies these migrations.

**Current live state (verified 2026-11-22, M3/M9):** migration 015's
TABLES are live (`public.documents`, `public.jobs` exist); the
`pdf-documents` BUCKET is missing (016 unapplied); the plain unique
index on `public.documents (user_id, content_hash)` is still in place
(017 unapplied — delete-then-re-upload of the same file still 500s
live). The engine's Alembic chain (0001–0009) has NEVER run against
live Postgres — it has only ever run on SQLite in tests and in the
local E2E harnesses.

## 0. Preconditions (do these first, in order)

1. **GitHub App install + push** (owner step, outstanding since M1):
   add `officerpath-pdf-engine` at
   https://github.com/apps/meta-muse-ai/installations/new, then push
   branch `officerpath-phase2-web`. Until the code is on GitHub,
   Render cannot build it and none of the steps below can deploy.
2. **Back up the live database.** Supabase Dashboard → Database →
   Backups: confirm a recent backup exists (free-tier backups are
   the project's backup story in Phase 2 — doc 06 §5). Do not
   proceed without one.
3. **Confirm the live project** is `officerpath-ai`
   (`gliebuyyjguxrwdfuakz`, Singapore, free plan) — the project the
   web app's `.env.local` points at. Never run these steps against
   another project.

## 1. Supabase migrations 016 + 017 (Dashboard → SQL Editor)

Run in this order. Both files are idempotent (safe to re-run).

### Step 1 — 016: the `pdf-documents` bucket

- File: `supabase/migrations/016_pdf_documents_bucket.sql`
- How: Dashboard → SQL Editor → New query → paste the file → Run.
- What it does: creates the PRIVATE bucket `pdf-documents`
  (100 MB cap, PDF + image MIME types) + 3 storage policies
  (users upload their own, users view their own, admins view all).
  It does NOT touch any table, policy, trigger, or Edge Function.
- Verify (SQL Editor):
  ```sql
  select id, public, file_size_limit from storage.buckets
    where id = 'pdf-documents';
  -- expect one row: pdf-documents, public = false, limit 104857600
  select policyname from pg_policies
    where schemaname = 'storage' and tablename = 'objects'
      and policyname like '%documents%';
  -- expect the three policies above
  ```
  Also: Dashboard → Storage shows `pdf-documents` (private).
- If it fails: the file is guarded (`ON CONFLICT DO NOTHING` /
  `IF NOT EXISTS`) — re-running is safe. If the error names a
  permission, the Dashboard user needs the project's owner role;
  do not retry with a different SQL path. Reversal:
  `016_pdf_documents_bucket_down.sql` (the bucket must be EMPTY
  first — the down migration never deletes uploaded files).

### Step 2 — 017: partial unique index on documents

- File: `supabase/migrations/017_documents_hash_partial_unique.sql`
- How: same as Step 1. Order vs 016 does not matter; both run
  after 015 (already live).
- What it does: drops 015's plain unique index
  `documents_user_hash_idx` and recreates it as a PARTIAL unique
  index (`WHERE deleted_at IS NULL`). Two LIVE rows with the same
  user + hash still cannot exist (dedup preserved); deleted rows
  no longer block a fresh upload.
- Verify (SQL Editor):
  ```sql
  select indexname, indexdef from pg_indexes
    where tablename = 'documents' and indexname = 'documents_user_hash_idx';
  -- indexdef MUST contain: WHERE deleted_at IS NULL
  ```
- Behaviour check (the M6 bug, live): upload a file, delete the
  document, re-upload the SAME file — the second upload must
  succeed with a NEW document id (not a 500, not a replay of the
  deleted document). If it still 500s, 017 did not apply — check
  the indexdef above before anything else.
- If it fails: dropping the plain index is guarded; re-running is
  safe. Reversal: `017_documents_hash_partial_unique_down.sql` —
  WARNING (in that file): restoring the plain index FAILS while a
  live row and a deleted row share a user + hash, and it
  re-introduces the M6 bug. Only roll back 017 after checking no
  such row pairs exist.

## 2. Alembic chain 0001–0009 (engine DB, on a machine with DATABASE_URL)

The engine's own tables (`student_profiles`, `subjects`,
`test_templates`, `test_sessions`, `student_responses`,
`test_results`, `student_question_collections`, `notifications`,
and the 17 Phase 1 tables) live in the SAME Supabase Postgres as
the 015 tables. They are created by Alembic, NOT by the Dashboard.

- Run from the repo root, with the live `DATABASE_URL` set
  (`postgresql+psycopg://...` — the Dashboard secret, never
  committed):
  ```bash
  alembic current        # expect: (no version) on a fresh live DB
  alembic upgrade head   # applies 0001 -> 0009 in order
  alembic current        # expect: 0009 (head)
  ```
- What each revision adds: 0001 Phase 1 engine tables (17);
  0002 `document_pages.layout_applied`; 0003 `student_profiles`;
  0004 profile timestamp server defaults; 0005 `subjects` /
  `topics` / `question_subjects` (+ 13 seeded subjects);
  0006 `marking_configs` / `test_templates` / `test_sessions` /
  `test_question_snapshots` (+ PPSC default marking config,
  + `documents`/`jobs` IF NOT EXISTS — the M5 carry-over fix);
  0007 `student_responses` / `test_results`;
  0008 `student_question_collections`;
  0009 `notifications`.
- Verify (SQL Editor, after `upgrade head`):
  ```sql
  select version_num from alembic_version;
  -- expect: the 0009 revision id (see alembic/versions/0009_m9_notifications.py)
  select count(*) from information_schema.tables
    where table_schema = 'public'
      and table_name in ('student_profiles','subjects','test_templates',
        'test_sessions','student_responses','test_results',
        'student_question_collections','notifications');
  -- expect: 8
  ```
- If `upgrade head` fails midway: Alembic stops at the failed
  revision — DO NOT re-run blindly. Read the error, fix the cause
  (usually a missing `DATABASE_URL` or a stale connection), then
  run `alembic upgrade head` again; it resumes from the last
  applied revision. Never hand-edit `alembic_version`.
- NOTE: 0006 creates `documents`/`jobs` IF NOT EXISTS — on live
  it is a no-op for those two tables (015 already created them);
  it must NOT be skipped, because the same revision also creates
  the test tables.

## 3. After both: the deploy-time smoke test (doc 06 §6)

After the migrations AND the first deploy (Render + Vercel, owner
steps — see `docs/phase2/PHASE_2_COMPLETION_REPORT.md`):

1. `GET /health` → 200 (not `degraded` — the database is now
   configured).
2. `GET /version` shows the deployed commit.
3. Unauthenticated `POST /api/v1/documents/register` → 401.
4. Register → 201 against staging data; one async job queued →
   done; review list loads.
5. **STOP CONDITION (live phone verification):** the three
   acceptance files — PPSC-66 PDF, computer table photo, Paper 60
   photo — parse through the WEB upload on the owner's phone and
   the resulting questions match the engine's stored rows. No fix
   is "done" until the phone proves it.

## 4. What is NOT in this runbook

- The 015 migration itself (already live; see
  `docs/migration-015-apply.md` if it ever needs re-applying).
- The Gemini server key (deferred by the owner — the engine runs
  with Gemini disabled; see ADR-002).
- The unconfirmed M3 test user `officerpath.m3.test@gmail.com`:
  delete it in Dashboard → Authentication → Users (a separate
  owner step, not a migration).
