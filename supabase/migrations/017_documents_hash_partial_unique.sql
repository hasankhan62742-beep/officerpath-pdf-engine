-- ============================================================
-- OfficerPath AI — PDF Engine, migration 017_documents_hash_partial_unique.sql
-- RUN ORDER: 17 — run AFTER 015 (and 016; order vs 016 does not matter).
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (M6, found by measuring in the M6 E2E):
-- 015's plain unique index on public.documents (user_id,
-- content_hash) makes delete-then-re-upload of the same file
-- fail with a 500 (UNIQUE constraint failed: documents.user_id,
-- documents.content_hash). The dedup lookup correctly ignores
-- soft-deleted rows (M4), but the plain index does not — the
-- soft-deleted row still holds the unique slot. A deleted
-- document must never block a fresh upload of the same file.
--
-- THE FIX: the uniqueness applies only to LIVE rows — a partial
-- unique index (WHERE deleted_at IS NULL). Two live rows with
-- the same user + hash still cannot exist (dedup preserved);
-- any number of deleted rows may share a hash with each other
-- or with one live row. The engine-side mirror (Alembic 0006
-- + app/db/models.py) carries the same partial index, so fresh
-- engine-managed databases already have it.
--
-- IDEMPOTENT: safe to run even if the partial index already
-- exists (IF NOT EXISTS guards throughout). Dropping the plain
-- index is also guarded.
--
-- VERIFY AFTER APPLYING: Dashboard -> SQL Editor ->
--   select indexname, indexdef from pg_indexes
--     where tablename = 'documents' and indexname = 'documents_user_hash_idx';
--   -- indexdef must contain "WHERE deleted_at IS NULL".
-- Then: upload a file, delete the document, re-upload the same
-- file — the second upload must succeed with a NEW document id
-- (not a 500, not a replay of the deleted document).
-- Reversal: 017_documents_hash_partial_unique_down.sql.
-- ============================================================

-- Drop the plain unique index from 015 (guarded: no-op if gone).
drop index if exists public.documents_user_hash_idx;

-- Recreate it as a partial unique index: live rows only.
create unique index if not exists documents_user_hash_idx
  on public.documents (user_id, content_hash)
  where deleted_at is null;
