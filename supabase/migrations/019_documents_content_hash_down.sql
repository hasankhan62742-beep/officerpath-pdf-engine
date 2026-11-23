-- ============================================================
-- OfficerPath AI — PDF Engine, migration 019_documents_content_hash_down.sql
-- Reversal for 019: drops the content_hash column again.
-- ONLY run while no rows carry a content_hash — check first:
--   select count(*) from public.documents where content_hash is not null;
--   -- must be 0, otherwise dedup keys would be lost.
-- The partial index from 017 depends on the column, so drop the
-- index first; after the down migration, dedup enforcement at the
-- database level is gone (the engine still dedups in code).
-- ============================================================

drop index if exists public.documents_user_hash_idx;

alter table public.documents
  drop column if exists content_hash;
