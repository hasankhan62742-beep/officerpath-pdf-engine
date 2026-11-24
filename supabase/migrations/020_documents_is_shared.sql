-- ============================================================
-- OfficerPath AI — PDF Engine, migration 020_documents_is_shared.sql
-- RUN ORDER: 20 — run AFTER 019.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (M11, shared question bank): students must be
-- able to take tests from the admin-owned question bank, but the
-- M6 test pool only ever saw the caller's own documents. The
-- engine's Document model (app/db/models.py) now carries
-- ``is_shared`` and Alembic 0011 adds the same column to
-- fresh/local DBs; this file adds it to the live table, which
-- is owned by migration 015.
--
-- This migration adds ONLY that one column (NOT NULL, default
-- false — every existing document stays private until an admin
-- explicitly shares it via PATCH /api/v1/admin/documents/{id}/
-- sharing). It touches no rows and no other table, index,
-- policy, or function.
--
-- IDEMPOTENT: safe to run even if the column already exists
-- (IF NOT EXISTS guard).
--
-- DOWNGRADE: see 020_documents_is_shared_down.sql.
-- ============================================================

alter table public.documents
  add column if not exists is_shared boolean not null default false;
