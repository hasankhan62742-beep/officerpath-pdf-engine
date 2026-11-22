# Phase 2 M1 — Database Extension Plan

**Date:** 2026-11-22
**Existing schema:** SQLAlchemy 2.x, `app/db/models.py` (17 tables),
Alembic 0001 (`alembic/versions/0001_m1_engine_tables.py`) + 0002
(`0002_m3_layout_column.py`, adds `document_pages.layout_applied`).
Supabase migration 015 (`supabase/migrations/015_documents_jobs.sql`)
creates `public.documents` / `public.jobs` + RLS + `pdf-documents`
bucket — **written, not applied live**.
**Rule:** extend, never rewrite. No existing table is dropped, renamed,
or re-typed. No existing Phase 1 row is deleted or rewritten.

## 1. What is reused as-is (no change)

| Existing table | Reused by Phase 2 for | Notes |
|---|---|---|
| `documents` | My Documents, upload history, source of every question | `user_id`, `title`, `storage_path`, `file_type`, `content_hash` (dedup), `page_count`, soft-delete `deleted_at`. Index `(user_id, created_at)` already exists. |
| `jobs` | Processing status, retry/cancel, result counts | See §5 for the `done` vs `completed` unification — the table shape stays, the vocabulary is unified. |
| `document_pages` | Source page for a question (`source_pages`) | `layout_applied` JSON already there (0002). |
| `processing_stages` | Job progress detail (per-stage seconds) | Already the source of the async `stages[]` response. |
| `ocr_blocks` | Evidence / debugging (OCR text + bbox per block) | Not user-facing by default; evidence trail source. |
| `extracted_questions` | **The question bank.** Every bank question IS an extracted question. | `original_text` (immutable) vs `normalized_text` (correctable), `validation_status`, `content_fingerprint`, `duplicate_of_id`. No copy of the question text into a second table — ever. |
| `question_options` | The 4 options of a bank question | `original_*` vs `normalized_*`, `label_inferred`, `position`. |
| `question_assets` | Figures/diagrams linked to a question | Served only via signed, owner-checked URLs (GAP-12). |
| `extracted_answers` | The resolved answer + its status | `status`, `resolved_label`, `resolution_method`, `resolution_score`. `correct_index = -1` means UNKNOWN — preserved. |
| `answer_evidence` / `answer_sources` | Evidence trail per answer | `detector`, `detector_confidence`, `raw_text`, `bbox`, `page_numbers`. |
| `extraction_reports` | Document report (counts, `requires_review`) | Already the source of `GET /documents/{id}/report`. |
| `manual_corrections` + `review_history` | The correction audit trail | Corrections never overwrite originals; every correction is a row here with old/new + reviewer. Phase 2 corrections go through the same tables. |
| `processing_errors`, `audit_log`, `rule_sets` | Error monitoring, audit, rule versioning | Admin monitoring (M9) reads these; no new audit table needed. |

## 2. New tables (Alembic 0003+, one migration per milestone that needs it)

All new tables live in the **engine DB** (SQLAlchemy + Alembic), not in
Supabase migrations — the engine DB is the one Phase 2 controls and
migrates with `alembic upgrade head`. Every new table carries:
`id UUID PK`, `user_id UUID NOT NULL` (except the shared reference
tables `subjects`/`topics`, which are global), `created_at` /
`updated_at` timestamps, and a foreign key with an explicit
`ondelete` rule. Every user-owned table gets an index on
`(user_id, created_at)`.

### 2.1 `student_profiles` (M3)

| Column | Type / constraint |
|---|---|
| `id` | UUID PK |
| `user_id` | UUID NOT NULL, UNIQUE — one profile per Supabase Auth user. FK to `auth.users(id)` is **not** enforceable from the engine DB (different connection path); enforce uniqueness + ownership in code and document it. |
| `full_name` | Text NOT NULL |
| `phone` | Text NULL |
| `preferred_exam` | Text NULL (e.g. `PPSC`, `CSS` — free text in M3, FK to an exam list in a later phase if needed) |
| `education_level` | Text NULL |
| `created_at` / `updated_at` | timestamps |

**Do NOT duplicate** the Flutter app's Supabase `profiles` table.
That table belongs to the Flutter app's auth/money flow
(`profiles.plan`, `premium_until`, `is_admin` — which the engine
never writes). The engine `student_profiles` holds only the web
student's display/profile data. If the two ever need to merge, that
is a Phase 3 data decision, not a Phase 2 silent copy.

### 2.2 `subjects` + `topics` (M5)

| Table | Columns |
|---|---|
| `subjects` | `id` UUID PK, `name` Text NOT NULL UNIQUE (e.g. `General Knowledge`), `slug` Text NOT NULL UNIQUE, `description` Text NULL, `is_active` Bool default true |
| `topics` | `id` UUID PK, `subject_id` UUID NOT NULL FK → `subjects.id` ON DELETE CASCADE, `name` Text NOT NULL, `slug` Text NOT NULL, UNIQUE (`subject_id`, `slug`) |
| `question_subjects` (join) | `id` UUID PK, `question_id` UUID NOT NULL FK → `extracted_questions.id` ON DELETE CASCADE, `subject_id` UUID NULL FK → `subjects.id` ON DELETE SET NULL, `topic_id` UUID NULL FK → `topics.id` ON DELETE SET NULL, `assigned_by` UUID NOT NULL (user who assigned it), `confidence` Text NULL (`manual` / `unassigned`), UNIQUE (`question_id`, `subject_id`, `topic_id`) |

Seed data: the 13 subjects from the Phase 2 prompt §12 (General
Knowledge, Pakistan Affairs, Current Affairs, Islamic Studies,
Everyday Science, English, Mathematics, Computer Science, Urdu,
Geography, History, Political Science, General Ability) as a data
migration inside the same Alembic revision. **Classification is
optional** — a question with no row in `question_subjects` is simply
uncategorised; the UI must never force a category (prompt §12).

### 2.3 `student_question_collections` (M5 — bookmarks live here too, see §2.7)

| Column | Type / constraint |
|---|---|
| `id` | UUID PK |
| `user_id` | UUID NOT NULL |
| `question_id` | UUID NOT NULL FK → `extracted_questions.id` ON DELETE CASCADE |
| `collection_type` | Text NOT NULL CHECK (`bookmark` / `mistake` / `custom`) |
| `note` | Text NULL (personal note — bookmarks and mistake entries) |
| `created_at` | timestamp |
| UNIQUE (`user_id`, `question_id`, `collection_type`) | A student bookmarks a question once. |

A "mistake" row is created by the result flow (M8) when a student
answers incorrectly; it is the same table as bookmarks so one query
serves both lists, distinguished by `collection_type`. A student's
rows are private; no sharing in Phase 2.

### 2.4 `test_templates` + `test_sessions` + `test_question_snapshots` (M6/M7)

| Table | Columns |
|---|---|
| `test_templates` | `id` UUID PK, `user_id` UUID NOT NULL, `name` Text NOT NULL, `question_count` Int NOT NULL CHECK IN (25, 50, 100, 150, 200), `source_type` Text NOT NULL (`all` / `documents` / `subjects` / `topics` / `bookmarks` / `unattempted` / `incorrect` / `mixed`), `source_ids` JSON NULL (document/subject/topic ids), `allow_repetition` Bool default false, `marking_config_id` UUID NULL FK → `marking_configs.id`, `created_at` |
| `marking_configs` | `id` UUID PK, `name` Text NOT NULL (e.g. `PPSC default`), `correct_marks` Numeric NOT NULL default 1, `incorrect_marks` Numeric NOT NULL default -0.25, `unattempted_marks` Numeric NOT NULL default 0, `is_default` Bool default false. Seeded with the PPSC default (+1 / −0.25 / 0). |
| `test_sessions` | `id` UUID PK, `user_id` UUID NOT NULL, `template_id` UUID NULL FK → `test_templates.id` ON DELETE SET NULL, `title` Text NOT NULL, `question_count` Int NOT NULL, `marking_config_id` UUID NOT NULL FK → `marking_configs.id`, `status` Text NOT NULL CHECK (`created` / `in_progress` / `submitted` / `abandoned` / `expired`), `started_at` / `submitted_at` / `expires_at` timestamps, `time_limit_seconds` Int NULL, `server_started_at` timestamp NOT NULL (server-side timer anchor — never the browser clock), `created_at` |
| `test_question_snapshots` | `id` UUID PK, `session_id` UUID NOT NULL FK → `test_sessions.id` ON DELETE CASCADE, `question_id` UUID NULL FK → `extracted_questions.id` ON DELETE SET NULL (NULL if the source question was later deleted — the snapshot still stands), `position` Int NOT NULL, `question_text` Text NOT NULL, `options` JSON NOT NULL (the 4 option texts + labels as captured), `correct_index` Int NOT NULL (the answer as captured; −1 = UNKNOWN — such a question must never be offered as a scored question; see §4), `answer_source` Text NULL, `source_document_id` UUID NULL, `source_page` Int NULL, UNIQUE (`session_id`, `position`) |

**Snapshot rule (hard):** once a session is created, its snapshots
never change — not when the bank is edited, not when a correction
lands, not when a question is deleted. A past test is a frozen
record. The snapshot copies the text/options/answer at creation
time; the `question_id` link is for review/navigation only.

### 2.5 `student_responses` + `test_results` (M7/M8)

| Table | Columns |
|---|---|
| `student_responses` | `id` UUID PK, `session_id` UUID NOT NULL FK → `test_sessions.id` ON DELETE CASCADE, `snapshot_id` UUID NOT NULL FK → `test_question_snapshots.id` ON DELETE CASCADE, `user_id` UUID NOT NULL, `selected_index` Int NULL (NULL = unattempted), `marked_for_review` Bool default false, `answered_at` timestamp NULL, `updated_at` timestamp, UNIQUE (`session_id`, `snapshot_id`) — one response per question per session; upsert on periodic save. |
| `test_results` | `id` UUID PK, `session_id` UUID NOT NULL UNIQUE FK → `test_sessions.id` ON DELETE CASCADE, `user_id` UUID NOT NULL, `total_questions` Int NOT NULL, `correct_count` Int NOT NULL, `incorrect_count` Int NOT NULL, `unattempted_count` Int NOT NULL, `total_marks` Numeric NOT NULL, `max_marks` Numeric NOT NULL, `percentage` Numeric NOT NULL, `time_taken_seconds` Int NOT NULL, `subject_breakdown` JSON NULL, `topic_breakdown` JSON NULL, `marking_config_id` UUID NOT NULL FK → `marking_configs.id`, `submitted_at` timestamp NOT NULL, `created_at` |

Results are **computed on the backend at submit time** from
`student_responses` + snapshots + the session's marking config, and
stored. The frontend never computes or supplies marks. A result row
is immutable once written (a re-grade, if ever needed, is a new row
with a reason — not an edit).

### 2.6 `notifications` (M9, in-app only)

| Column | Type / constraint |
|---|---|
| `id` | UUID PK |
| `user_id` | UUID NOT NULL (NULL = broadcast to all students — M9 decides; default per-user) |
| `type` | Text NOT NULL (`upload_done` / `upload_failed` / `review_needed` / `test_submitted` / `result_ready` / `subscription_change`) |
| `title` / `body` | Text NOT NULL |
| `link` | Text NULL (in-app route, e.g. `/documents/{id}`) |
| `is_read` | Bool default false |
| `created_at` | timestamp |

Email is **not** a Phase 2 notification channel: no email is claimed
sent unless a provider confirms it (prompt §19). The table supports a
future email outbox; Phase 2 writes in-app rows only.

### 2.7 What is NOT a separate table

- **Bookmarks / mistake notebook:** one table
  (`student_question_collections`, §2.3), distinguished by
  `collection_type`. No second table.
- **Admin roles:** no `roles` table in Phase 2 M1 design. Admin is a
  backend-enforced flag resolved from the Supabase Auth user record
  (see doc 05 §4) — the mechanism is decided in M9; Phase 2 does not
  invent a role table now.
- **Subscriptions / payments:** **not in Phase 2 at all** (Phase 3).
  No `subscriptions`, `payments`, or `plans` table is created. The
  dashboard shows subscription status only if the Flutter app's
  Supabase tables already carry it — read-only, never written by the
  engine (see doc 05 §6).

## 3. Columns added to existing tables (only where unavoidable)

| Table | New column | Reason |
|---|---|---|
| `extracted_questions` | none | Subject/topic assignment lives in `question_subjects` (§2.2); no column needed. |
| `documents` | none | Status comes from `jobs` + `processing_stages`; no new column. |
| `jobs` | none (see §5) | The vocabulary fix is a value change + a CHECK constraint in a later migration, not a new column. |
| `test_sessions` | — (new table) | — |

Principle: prefer a new table over altering an existing one. Any
future alteration needs its own Alembic revision with upgrade +
downgrade and a data backfill step recorded in the migration.

## 4. Ownership and integrity rules

1. **Every user-owned row carries `user_id`, and every query filters
   by it.** No endpoint returns rows for another user (404, never
   403-with-existence — the Phase 1 pattern).
2. **Foreign keys everywhere** with explicit `ondelete` (CASCADE for
   owned children, SET NULL for links that must survive deletion —
   e.g. `test_question_snapshots.question_id`).
3. **A student's correction never changes another student's content:**
   corrections go through `manual_corrections` on the shared
   `extracted_questions` row (Phase 1 rule) — but the web question
   bank shows a correction as the *student's view* layered on the
   immutable original. If shared-question policy changes in M5, it
   needs a decision record; the default is: corrections are visible
   to the correcting student and to admins, and the original is never
   overwritten.
4. **UNKNOWN stays UNKNOWN:** `correct_index = -1` in a snapshot means
   the question is unanswerable as scored. The test builder must
   exclude UNKNOWN-answer questions from scored tests (or offer them
   only in an explicitly-labelled "review mode" that carries no marks).
5. **Transactions:** test creation (template + session + snapshots) is
   one transaction; submit (responses finalise + result row + mistake
   rows) is one transaction. No partial test, no partial result.
6. **Indexes:** `(user_id, created_at)` on every user-owned table;
   `(session_id, position)` on snapshots; `(user_id, question_id,
   collection_type)` unique on collections; `(subject_id, slug)` unique
   on topics.
7. **Audit:** `manual_corrections` + `review_history` remain the
   correction audit trail; `audit_log` (existing) records admin
   actions in M9.

## 5. The dual-store unification (blocks M4 — decide in M3)

The finding in doc 01 §2.2 (Supabase `public.jobs` with status
`done` vs engine-DB jobs with status `completed`, two different rows
for the same logical job) must be resolved before the frontend lists
documents or polls job status. Recommended solution (to be confirmed
in M3, not decided unilaterally here):

- **Option A (recommended): engine DB is the single source of truth
  for jobs.** The register/upload flow writes the Supabase
  `public.documents` row (needed for the bucket/RLS story) but the
  *job* is created and tracked in the engine DB only; the Supabase
  `public.jobs` row is either not created by the web flow or is kept
  as a thin mirror with status mapped `completed → done` at write
  time. The frontend polls one job endpoint (`async-jobs`) and one
  vocabulary (`completed`).
- **Option B:** keep both, and build a read-side union view in the
  backend that merges both stores by `document_id` and maps the
  status vocabulary. More moving parts; only if Option A breaks the
  Flutter app's expectations of `public.jobs`.
- **What is forbidden:** writing `completed` into `public.jobs`
  (violates the 015 check constraint), and letting the frontend talk
  to two job endpoints and reconcile them in the browser.

Whichever option M3 picks, the migration that implements it gets its
own ADR (ADR-011 or later) and its own Alembic revision with
upgrade + downgrade. The `JobStatus` enum
(`app/schemas/documents.py:25-31`) and the 015 check constraint must
be changed together, never one without the other.

## 6. Migration strategy

- **One Alembic revision per milestone** that needs schema changes
  (0003 in M3 for `student_profiles`; 0004 in M5 for subjects/topics/
  collections; 0005 in M6/M7 for tests/sessions/snapshots/responses/
  results; 0006 in M9 for notifications). Each revision: `upgrade()`
  + `downgrade()`, tested on SQLite in CI (the existing CI job) and
  against a Postgres instance before any deploy.
- **Migration 015 stays a Supabase Dashboard migration** (it creates
  Supabase-side tables/RLS/bucket). It is applied once, by the owner,
  before the web app can be healthy. Alembic never manages
  `public.documents` / `public.jobs` — the SQLAlchemy `Document`/`Job`
  models *mirror* them, and the mirror must be kept in sync by hand
  (see §5).
- **Seed data** (subjects, default marking config) ships inside the
  creating revision as data inserts with an idempotent guard
  (`INSERT ... ON CONFLICT DO NOTHING` on Postgres; equivalent guard
  on SQLite for CI).
- **Rollback:** every revision's `downgrade()` drops only what its
  `upgrade()` created, in reverse order. A downgrade never deletes
  user data silently — if a table holds rows, the downgrade refuses
  (raises) unless an explicit archive step has run; that rule is
  written into the migration.
- **No migration runs automatically on deploy** until M10 decides the
  deploy-time migration step (see doc 06 §5). Until then, migrations
  are applied by a documented manual step.
