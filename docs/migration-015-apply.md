# Migration 015 — Dashboard apply steps (M1)

**Status (2026-11-21): NOT applied live.** This document is the exact
procedure for the owner to apply it. The VM has no SQL access and no
agent applies it — it is a Dashboard step by the owner, after the M1
go-ahead for migration 015 is given separately (the ADR approval on
2026-11-21 covered ADR-001 + ADR-002 and starting M1; migration 015
live apply still needs its own explicit go-ahead).

## What 015 does

Creates two NEW tables (`public.documents`, `public.jobs`) with RLS,
and one NEW private bucket (`pdf-documents`). Additive-only: it does
not modify any existing table, policy, trigger, bucket, or Edge
Function, and never touches `profiles` / `activation_codes` /
`payments` / `test_results` / `waitlist` / `sent_notifications` /
`redeem_attempts`.

M1 revision (still unapplied, so editing the file pre-apply was safe):
`file_type` includes `webp` / `tiff` / `tif`; `documents` gains
`content_hash` (SHA-256, per-user dedup) + unique index
`(user_id, content_hash)`; the bucket allows `image/webp` +
`image/tiff`.

After 015, apply Alembic 0001 (the engine-owned §14 tables) with
`DATABASE_URL` set — see "After applying" below. 0001 has foreign
keys to `documents.id` / `jobs.id`, so 015 MUST come first.

## Apply steps (Supabase Dashboard, ~5 minutes)

1. Open the Supabase Dashboard → project `officerpath-ai` → **SQL Editor** → **New query**.
2. Open `supabase/migrations/015_documents_jobs.sql` in this repo, copy
   the whole file, paste it into the query editor.
3. Press **Run**. Expect success with no errors. (If it reports
   "already exists" for any object, that is safe: every statement is
   `IF NOT EXISTS` / `ON CONFLICT DO NOTHING` — re-running is idempotent.)
4. Verify with the queries below (same SQL Editor, one at a time).

## Verification queries (run after applying)

```sql
-- Tables exist with the M1 columns.
select column_name, data_type
from information_schema.columns
where table_schema = 'public' and table_name = 'documents'
order by ordinal_position;
-- Expect: id, user_id, title, storage_path, file_type,
-- file_size_bytes, page_count, content_hash, metadata, created_at.

select count(*) from public.documents;  -- Expect: 0
select count(*) from public.jobs;       -- Expect: 0

-- RLS is on and the policies exist.
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename in ('documents', 'jobs');
-- Expect: rowsecurity = true for both.

select policyname from pg_policies
where schemaname = 'public' and tablename = 'documents';
-- Expect: "Users can view their own documents",
-- "Users can insert their own documents",
-- "Admins can view all documents".

-- Bucket exists, private, with the M1 MIME types.
select id, public, file_size_limit, allowed_mime_types
from storage.buckets where id = 'pdf-documents';
-- Expect: public = false, file_size_limit = 104857600,
-- allowed_mime_types includes image/webp and image/tiff.
```

Also check in the UI: **Table Editor** shows `documents` + `jobs`;
**Storage** shows the `pdf-documents` bucket.

## After applying

1. `GET /health` can now report healthy: it selects from
   `documents` and will return `supabase: ok` (before 015 it
   correctly reports `degraded`).
2. Apply Alembic 0001 from a machine with the repo + `DATABASE_URL`
   set to the Supabase Postgres URL:
   ```bash
   DATABASE_URL='postgresql+psycopg://postgres:<password>@db.gliebuyyjguxrwdfuakz.supabase.co:5432/postgres' \
     alembic upgrade head
   alembic current  # Expect: 0001_m1_engine_tables (head)
   ```
   The Postgres password is the Supabase Dashboard → Settings →
   Database password. Never paste it into chat or commit it.
3. Smoke-test the register flow against staging (owner's phone/Flutter
   change is M6 work; until then use curl with a real user JWT).

## Rollback (only if something is wrong)

1. Confirm `documents` and `jobs` are empty (or export their rows
   first — deleting them deletes the jobs that reference them).
2. Dashboard → SQL Editor → paste
   `supabase/migrations/015_documents_jobs_down.sql` → Run.
3. Verify: `select * from public.documents;` errors with
   "relation does not exist", and the bucket is gone from Storage.
4. Alembic 0001 must be downgraded FIRST if it was applied:
   `alembic downgrade base` (it references documents/jobs).

## What local testing could NOT verify (honest limits)

- This SQL was NOT run against live Supabase in M1 (no access, no
  go-ahead). It was reviewed line by line and its statements are
  idempotent, but live RLS/bucket behaviour is unverified until the
  owner applies it and runs the queries above.
- Alembic 0001 up/down WAS tested locally on SQLite (see
  `app/tests/test_schema.py`). SQLite cannot verify the Postgres-only
  parts: RLS policies, `gen_random_uuid()`, the storage bucket, and
  CHECK-constraint behaviour. Those are verified only by the Dashboard
  queries above.
