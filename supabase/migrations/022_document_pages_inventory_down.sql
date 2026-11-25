-- ============================================================
-- OfficerPath AI — PDF Engine, migration 022_document_pages_inventory_down.sql
-- DOWNGRADE for 022_document_pages_inventory.sql (A3).
-- Removes the three inventory columns from document_pages.
-- Run only if A3 is being rolled back; the inventory is derived
-- data — it can be rebuilt by re-parsing the documents.
-- ============================================================

alter table public.document_pages
  drop column if exists error_message;
alter table public.document_pages
  drop column if exists question_count;
alter table public.document_pages
  drop column if exists extraction_status;
