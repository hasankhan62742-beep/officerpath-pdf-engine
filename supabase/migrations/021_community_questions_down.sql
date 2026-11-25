-- ============================================================
-- OfficerPath AI — PDF Engine, migration 021_community_questions_down.sql
-- DOWNGRADE for 021_community_questions.sql (M16).
-- Removes the staging table and the three attribution columns.
-- Run only if M16 is being rolled back; approved bank rows
-- created from community submissions keep their question text
-- and answers — only the "Submitted by" / "Paper" attribution
-- is lost.
-- ============================================================

alter table public.extracted_questions
  drop column if exists paper;
alter table public.extracted_questions
  drop column if exists community_question_id;
alter table public.extracted_questions
  drop column if exists contributor_name;
drop table if exists public.community_questions;
