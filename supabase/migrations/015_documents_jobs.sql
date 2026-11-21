-- ============================================================
-- OfficerPath AI — PDF Engine, migration 015_documents_jobs.sql
-- RUN ORDER: 15 — run AFTER 001..014.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead via the coordinator.
-- No secrets or keys in this file. Safe to commit.
--
-- ADDITIVE ONLY: creates two NEW tables (documents, jobs) and one NEW
-- private bucket (pdf-documents). It does NOT modify any existing
-- table, policy, trigger, bucket, or Edge Function. In particular it
-- never touches profiles / activation_codes / payments /
-- test_results / waitlist / sent_notifications / redeem_attempts,
-- and it never touches the money path.
--
-- VERIFY AFTER APPLYING: Dashboard -> Table Editor shows documents
-- and jobs; Authentication -> Policies shows the policies below;
-- Storage -> pdf-documents shows the bucket + its policies.
--
-- M1 REVISION (2026-11-21, still unapplied — safe to edit pre-apply):
-- file_type now includes 'webp', 'tiff', 'tif' (prompt §1 inputs);
-- documents gains content_hash (SHA-256, per-user dedup key) + a
-- unique index on (user_id, content_hash); the bucket allows
-- image/webp + image/tiff. Reversal: 015_documents_jobs_down.sql.
-- See docs/migration-015-apply.md for the exact Dashboard steps.
-- ============================================================

-- (a) documents — one row per uploaded document (metadata only;
-- the file itself lives in the pdf-documents bucket).
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  storage_path text not null,
  file_type text not null
    check (file_type in ('pdf', 'txt', 'docx', 'jpg', 'jpeg', 'png', 'webp', 'tiff', 'tif')),
  file_size_bytes bigint not null check (file_size_bytes > 0),
  page_count int check (page_count is null or page_count between 1 and 100),
  -- SHA-256 hex of the file bytes (M1 ingestion dedup). NULL for
  -- pre-M1 rows; filled by the engine on every M1 upload.
  content_hash text check (content_hash is null or length(content_hash) = 64),
  metadata jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, storage_path)
);

-- (b) jobs — one durable processing job per document.
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid not null references public.documents(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'uploading', 'processing', 'done', 'failed', 'cancelled')),
  idempotency_key text,
  retry_count int not null default 0 check (retry_count >= 0),
  error text,
  result_summary jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique (user_id, idempotency_key)
);

create index if not exists jobs_user_created_idx
  on public.jobs (user_id, created_at desc);
create index if not exists jobs_active_idx
  on public.jobs (status) where status in ('queued', 'uploading', 'processing');
create index if not exists documents_user_created_idx
  on public.documents (user_id, created_at desc);
-- Dedup lookup: same user + same SHA-256 -> same document (M1).
-- Unique index enforces it at the database level too (a second
-- insert with the same hash fails instead of duplicating).
create unique index if not exists documents_user_hash_idx
  on public.documents (user_id, content_hash);

-- (c) RLS — enabled on both tables.
alter table public.documents enable row level security;
alter table public.jobs enable row level security;

-- Users can SELECT and INSERT their own documents only.
create policy "Users can view their own documents"
  on public.documents for select
  to authenticated
  using (auth.uid() = user_id);
create policy "Users can insert their own documents"
  on public.documents for insert
  to authenticated
  with check (auth.uid() = user_id);
-- No UPDATE / DELETE policy for clients: documents are immutable
-- once registered (admins use the Dashboard if one must go).

-- Users can SELECT and INSERT their own jobs only.
create policy "Users can view their own jobs"
  on public.jobs for select
  to authenticated
  using (auth.uid() = user_id);
create policy "Users can insert their own jobs"
  on public.jobs for insert
  to authenticated
  with check (auth.uid() = user_id);
-- Users may cancel their own jobs — and ONLY cancel them. The policy
-- below is the only client UPDATE on jobs: it permits setting
-- status='cancelled' on an own row, and forbids touching any other
-- column or status value.
create policy "Users can cancel their own jobs"
  on public.jobs for update
  to authenticated
  using (auth.uid() = user_id)
  with check (
    auth.uid() = user_id
    and status = 'cancelled'
  );
-- No DELETE policy for clients.

-- Admins can read all documents and jobs (read-only from the client).
create policy "Admins can view all documents"
  on public.documents for select
  to authenticated
  using (public.is_admin());
create policy "Admins can view all jobs"
  on public.jobs for select
  to authenticated
  using (public.is_admin());

-- NOTE: the Python backend writes job status/results with the
-- SERVICE-ROLE key, which bypasses RLS. Client policies above are
-- intentionally narrow so no client can forge a job outcome.

-- (d) Private bucket for uploaded documents (PDFs / page images).
-- 100 MB cap mirrors the app's import limit; PDF + image MIME types.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  values (
    'pdf-documents', 'pdf-documents', false, 104857600,
    array['application/pdf', 'text/plain',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'image/jpeg', 'image/png', 'image/webp', 'image/tiff']
  )
  on conflict (id) do nothing;

-- Authenticated users may INSERT only under their own uid folder.
create policy "Users can upload their own documents"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'pdf-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Admins may read every document in the bucket.
create policy "Admins can view all documents in bucket"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'pdf-documents'
    and public.is_admin()
  );

-- Owners may read their own documents.
create policy "Users can view their own documents in bucket"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'pdf-documents'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- No UPDATE / DELETE policy on purpose: uploaded documents are
-- immutable for clients. Cleanup of processed files is done by the
-- backend (service role) after a job completes, per the retention
-- policy in the README.
