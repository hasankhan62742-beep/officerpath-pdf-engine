-- ============================================================
-- OfficerPath AI — PDF Engine, migration 018_documents_deleted_at_down.sql
-- Reversal for 018: drops the deleted_at column again.
-- ONLY run while no rows are soft-deleted — check first:
--   select count(*) from public.documents where deleted_at is not null;
--   -- must be 0, otherwise soft-delete markers would be lost.
-- The partial index from 017 depends on the column, so drop the
-- index first; after the down migration, re-create 015's plain
-- unique index if dedup enforcement is still wanted:
--   create unique index if not exists documents_user_hash_idx
--     on public.documents (user_id, content_hash);
-- ============================================================

drop index if exists public.documents_user_hash_idx;

alter table public.documents
  drop column if exists deleted_at;
