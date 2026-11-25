-- ============================================================
-- OfficerPath AI — PDF Engine, migration 022_document_pages_inventory.sql
-- RUN ORDER: 22 — run AFTER 021.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (A3, gap-report F7): the pipeline recorded
-- per-page classification at ingest but never what extraction
-- found on each page. These three additive columns hold the
-- inventory the worker records after a parse (see
-- app/services/pages.py):
--   extraction_status: processed | no_questions | failed |
--     low_confidence (NULL = never inventoried)
--   question_count: stored question rows (MCQs + pending)
--     attributed to the page
--   error_message: short reason when status is "failed"
--     (a code / page number only — never file contents or OCR text)
--
-- This migration adds ONLY those three columns to the existing
-- document_pages table. It touches no rows and no other table,
-- index, policy, or function. The expected question count needs
-- NO migration: it lives in documents.metadata (JSONB).
--
-- IDEMPOTENT: safe to run even if the columns already exist
-- (IF NOT EXISTS guards).
--
-- DOWNGRADE: see 022_document_pages_inventory_down.sql.
-- ============================================================

alter table public.document_pages
  add column if not exists extraction_status text;
alter table public.document_pages
  add column if not exists question_count integer;
alter table public.document_pages
  add column if not exists error_message text;
