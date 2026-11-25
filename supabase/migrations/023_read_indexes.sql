-- ============================================================
-- OfficerPath AI — PDF Engine, migration 023_read_indexes.sql
-- RUN ORDER: 23 — run AFTER 022.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (B bugfix, 2026-11-26): profiled on a
-- realistic-volume local replica (54,161 questions, 216,416
-- options, 54,104 answers), EXPLAIN showed full table scans
-- where every bank read filters by question_id — SCAN
-- question_options and SCAN extracted_answers + TEMP B-TREE
-- FOR ORDER BY — because neither table had a question_id
-- index. On the live 0.1-CPU free tier those scans pushed the
-- subject-wide bank list past the proxy timeout ("Failed to
-- fetch") and the section-counts call into an endless spinner.
--   ix_question_options_question on question_options(question_id)
--   ix_extracted_answers_question_created on
--     extracted_answers(question_id, created_at) — serves the
--     filter and the latest-first order (read backwards)
--   ix_question_subjects_topic on
--     question_subjects(topic_id, question_id) — the counts-only
--     availability query drives from topic_id
--
-- This migration adds ONLY those three indexes. It touches no
-- rows and no other table, column, policy, or function. Index
-- builds on 54k rows take well under a second.
--
-- IDEMPOTENT: safe to run even if the indexes already exist
-- (IF NOT EXISTS guards).
--
-- DOWNGRADE: see 023_read_indexes_down.sql.
-- ============================================================

create index if not exists ix_question_options_question
  on public.question_options (question_id);
create index if not exists ix_extracted_answers_question_created
  on public.extracted_answers (question_id, created_at);
create index if not exists ix_question_subjects_topic
  on public.question_subjects (topic_id, question_id);
