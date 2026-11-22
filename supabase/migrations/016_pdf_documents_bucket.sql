-- ============================================================
-- OfficerPath AI — PDF Engine, migration 016_pdf_documents_bucket.sql
-- RUN ORDER: 16 — run AFTER 015.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (M3, ADR-011): live verification on 2026-11-22
-- found 015's TABLES live (public.documents / public.jobs exist)
-- but the pdf-documents BUCKET missing (GET /storage/v1/bucket/
-- pdf-documents -> 404 NoSuchBucket). 015 was applied partially,
-- or its tables were created another way and the bucket step never
-- ran. This migration creates ONLY the bucket + its storage
-- policies — the part that is missing. It does NOT touch the jobs
-- check constraint (the engine now writes `done`, which the
-- existing constraint already allows) and does NOT modify any
-- existing table, policy, trigger, or Edge Function.
--
-- IDEMPOTENT: safe to run even if the bucket or a policy already
-- exists (ON CONFLICT / IF NOT EXISTS guards throughout).
--
-- VERIFY AFTER APPLYING: Dashboard -> Storage shows pdf-documents
-- (private); Authentication -> Policies shows the three storage
-- policies below.
-- Reversal: 016_pdf_documents_bucket_down.sql (bucket must be
-- empty first — objects are never deleted by the down migration).
-- ============================================================

-- (a) Private bucket for uploaded documents (PDFs / page images).
-- 100 MB cap mirrors the app's import limit; PDF + image MIME types.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  values (
    'pdf-documents', 'pdf-documents', false, 104857600,
    array['application/pdf', 'text/plain',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'image/jpeg', 'image/png', 'image/webp', 'image/tiff']
  )
  on conflict (id) do nothing;

-- (b) Storage policies (guarded: skip any that already exist).

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects'
      and policyname = 'Users can upload their own documents'
  ) then
    create policy "Users can upload their own documents"
      on storage.objects for insert
      to authenticated
      with check (
        bucket_id = 'pdf-documents'
        and (storage.foldername(name))[1] = auth.uid()::text
      );
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects'
      and policyname = 'Admins can view all documents in bucket'
  ) then
    create policy "Admins can view all documents in bucket"
      on storage.objects for select
      to authenticated
      using (
        bucket_id = 'pdf-documents'
        and public.is_admin()
      );
  end if;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'storage' and tablename = 'objects'
      and policyname = 'Users can view their own documents in bucket'
  ) then
    create policy "Users can view their own documents in bucket"
      on storage.objects for select
      to authenticated
      using (
        bucket_id = 'pdf-documents'
        and (storage.foldername(name))[1] = auth.uid()::text
      );
  end if;
end $$;

-- No UPDATE / DELETE policy on purpose: uploaded documents are
-- immutable for clients. Cleanup of processed files is done by the
-- backend (service role) after a job completes, per the retention
-- policy in the README.
