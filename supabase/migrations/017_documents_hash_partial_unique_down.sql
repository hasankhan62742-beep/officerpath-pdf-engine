-- OfficerPath AI — PDF Engine, migration 017 down.
-- Reverses 017_documents_hash_partial_unique.sql: restores 015's
-- plain unique index on public.documents (user_id, content_hash).
--
-- WARNING: restoring the plain index FAILS while two rows share
-- a user + hash with at least one of them live and the other
-- deleted (the state 017 permits). It also re-introduces the
-- M6 bug: delete-then-re-upload of the same file fails with a
-- 500. Only run this if 017 itself must be rolled back, after
-- checking no such row pairs exist:
--   select user_id, content_hash, count(*)
--     from public.documents group by 1, 2 having count(*) > 1;

drop index if exists public.documents_user_hash_idx;

create unique index if not exists documents_user_hash_idx
  on public.documents (user_id, content_hash);
