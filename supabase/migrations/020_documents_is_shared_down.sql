-- ============================================================
-- OfficerPath AI — PDF Engine, migration 020_documents_is_shared_down.sql
-- DOWNGRADE for 020_documents_is_shared.sql: drops the
-- is_shared column. Only run while no test depends on shared
-- bank questions (sharing is an admin flag, not user data).
-- ============================================================

alter table public.documents drop column if exists is_shared;
