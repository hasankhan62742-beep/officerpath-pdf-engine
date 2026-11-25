-- ============================================================
-- OfficerPath AI — PDF Engine, migration 023_read_indexes_down.sql
-- DOWNGRADE for 023_read_indexes.sql (B bugfix).
-- Removes the three read-path indexes. Run only if the B build
-- is being rolled back; reads get slow again, nothing else
-- changes.
-- ============================================================

drop index if exists public.ix_question_subjects_topic;
drop index if exists public.ix_extracted_answers_question_created;
drop index if exists public.ix_question_options_question;
