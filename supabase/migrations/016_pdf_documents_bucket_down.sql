-- OfficerPath AI — PDF Engine, migration 016 down.
-- Reverses 016_pdf_documents_bucket.sql: drops the three storage
-- policies and the pdf-documents bucket.
--
-- The bucket delete FAILS while objects remain (storage enforces
-- it) — that is deliberate: this migration never deletes uploaded
-- files. Empty the bucket first (Dashboard -> Storage), then run.
-- The 015 tables are NOT touched by this file.

drop policy if exists "Users can upload their own documents"
  on storage.objects;
drop policy if exists "Admins can view all documents in bucket"
  on storage.objects;
drop policy if exists "Users can view their own documents in bucket"
  on storage.objects;

delete from storage.buckets where id = 'pdf-documents';
