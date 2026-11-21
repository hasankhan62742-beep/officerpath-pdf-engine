-- ============================================================
-- OfficerPath AI — PDF Engine, migration 015 DOWN (reversal).
-- Run ONLY after confirming no jobs/documents depend on these
-- objects (Dashboard -> Table Editor: documents + jobs must be
-- empty, or their rows exported first). Reverses exactly what
-- 015_documents_jobs.sql created; touches nothing else.
-- Order matters: policies -> bucket -> tables.
-- ============================================================

-- Storage policies on pdf-documents.
drop policy if exists "Users can upload their own documents" on storage.objects;
drop policy if exists "Admins can view all documents in bucket" on storage.objects;
drop policy if exists "Users can view their own documents in bucket" on storage.objects;

-- Bucket row (fails if objects remain — delete them first, service role).
delete from storage.buckets where id = 'pdf-documents';

-- Table policies.
drop policy if exists "Admins can view all documents" on public.documents;
drop policy if exists "Admins can view all jobs" on public.jobs;
drop policy if exists "Users can cancel their own jobs" on public.jobs;
drop policy if exists "Users can view their own documents" on public.documents;
drop policy if exists "Users can insert their own documents" on public.documents;
drop policy if exists "Users can view their own jobs" on public.jobs;
drop policy if exists "Users can insert their own jobs" on public.jobs;

-- Tables (jobs first: it references documents).
drop table if exists public.jobs;
drop table if exists public.documents;
