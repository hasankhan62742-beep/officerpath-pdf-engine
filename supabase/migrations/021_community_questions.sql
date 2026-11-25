-- ============================================================
-- OfficerPath AI — PDF Engine, migration 021_community_questions.sql
-- RUN ORDER: 21 — run AFTER 020.
-- HOW TO APPLY: Supabase Dashboard -> SQL Editor -> New query ->
-- paste this file -> Run. DO NOT apply from the VM (no SQL access);
-- applying needs the owner's go-ahead.
-- No secrets or keys in this file. Safe to commit.
--
-- WHY IT EXISTS (M16, "Add Questions"): students submit a
-- question + 4 options + correct answer + explanation + subject
-- + source; it waits as a staging row until an admin approves
-- it, and the approval creates the real bank rows under the
-- shared community document. Until approval the submission is
-- invisible to every pool.
--
-- This migration adds ONLY the staging table plus three
-- attribution columns on extracted_questions (contributor_name
-- + community_question_id + paper — the "Submitted by ..." and
-- "Paper: ..." display). It touches no rows and no other
-- table, index, policy, or function.
--
-- IDEMPOTENT: safe to run even if the objects already exist
-- (IF NOT EXISTS guards).
--
-- DOWNGRADE: see 021_community_questions_down.sql.
-- ============================================================

create table if not exists public.community_questions (
  id uuid primary key default gen_random_uuid(),
  contributor_id uuid not null,
  contributor_name text not null,
  question_text text not null,
  options jsonb not null,
  correct_index integer not null,
  explanation text,
  subject_id uuid references public.subjects(id) on delete set null,
  topic_id uuid references public.topics(id) on delete set null,
  source text,
  paper text,
  status text not null default 'pending',
  review_note text,
  reviewed_by uuid,
  reviewed_at timestamptz,
  bank_question_id uuid references public.extracted_questions(id) on delete set null,
  fingerprint text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_community_questions_status check (status in ('pending', 'approved', 'rejected')),
  constraint ck_community_questions_correct_index check (correct_index >= 0 and correct_index <= 3)
);

create index if not exists ix_community_questions_contributor_created
  on public.community_questions (contributor_id, created_at);
create index if not exists ix_community_questions_status_created
  on public.community_questions (status, created_at);
create index if not exists ix_community_questions_fingerprint
  on public.community_questions (fingerprint);

alter table public.extracted_questions
  add column if not exists contributor_name text;
alter table public.extracted_questions
  add column if not exists community_question_id uuid references public.community_questions(id) on delete set null;
alter table public.extracted_questions
  add column if not exists paper text;
