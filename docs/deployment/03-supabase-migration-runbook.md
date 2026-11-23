# Workstream C — Supabase + Database Migration Runbook

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Supabase project:** `officerpath-ai` (`gliebuyyjguxrwdfuakz`, Singapore, free plan)
**Repository (local):** `~/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream C subagent (read-only inspection; no file modified except this report)
**Scope:** Supabase migrations 015–018, Alembic 0001–0009, RLS/storage/Auth review, backup and recovery, migration execution order, rollback limitations.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** This runbook **replaces** `docs/phase2/migration-runbook.md` (M10) as the deployment runbook. The M10 runbook is wrong on two points — see §1. Every live fact in §2 is parent-reported (verified by the parent via the browser on 2026-11-23) and is marked as such; this workstream ran **no live check** — it has no Supabase access from the VM. Every file-level finding in §3–§4 was checked by this workstream with the command shown or cited. No migration was applied, no live data was touched, no money was spent.

**Related documents (built on, not duplicated):** `docs/phase2/migration-runbook.md` (M10 — superseded by this file), `docs/phase2/rollback-runbook.md`, `docs/migration-015-apply.md`, `docs/deployment/01-repository-safety-audit.md`, `docs/deployment/02-github-ci-report.md`, `docs/phase2/PHASE_2_COMPLETION_REPORT.md`.

---

## 1. Corrections to the M10 runbook (read this first)

| # | M10 runbook said | What is actually true | Source |
|---|---|---|---|
| C1 | "Back up the live database. Confirm a recent backup exists (free-tier backups are the project's backup story)." | **WRONG — the free plan has no backups at all.** Dashboard shows "LAST BACKUP: No backups"; "Free Plan does not include project backups. Upgrade to the Pro Plan for up to 7 days of scheduled backups." The backup precondition **cannot** be met on the free plan. See §7 for the corrected procedure (manual `pg_dump`, Pro option, waiver rule). | Parent-reported, browser-verified 2026-11-23 |
| C2 | Migration order: 015 live → 016 → 017 → Alembic 0001–0009. | **017 FAILED live** (ERROR 42703, `deleted_at` does not exist) and a new migration **018** is required before 017 can be re-run. Correct order is now: 015 live → **016 DONE** → **018** → **017 (re-run)** → Alembic 0001–0009. See §5. | Parent-reported, browser-verified 2026-11-23 |
| C3 | 017 "drops 015's plain unique index and recreates it as a PARTIAL unique index" — presented as a routine step. | 017 cannot run at all until 018 adds the `deleted_at` column, because the partial index's `WHERE deleted_at IS NULL` references a column the live table does not have. The live `public.documents` table (015) was **never given** `deleted_at`, although the engine model and Alembic 0001/0006 both expect it. Root cause verified first-hand in §4. | This workstream (§4) + parent-reported failure |
| C4 | "0006 creates `documents`/`jobs` IF NOT EXISTS — on live it is a no-op for those two tables; it must NOT be skipped." | Still true — but it now matters more: because 0006 is a no-op for `documents` on live, **Alembic will never add the missing `deleted_at` column**. That is exactly why Supabase migration 018 exists. Do not expect the Alembic run to repair the gap. | This workstream (§4, `_create_documents_if_missing`) |

---

## 2. Current live state

All rows are parent-reported (browser-verified on 2026-11-23); this workstream did not re-check them.

| Item | State | Status |
|---|---|---|
| Live project | `officerpath-ai` (`gliebuyyjguxrwdfuakz`), Singapore, free plan — confirmed in the Dashboard | COMPLETED (parent-reported) |
| Migration 015 tables | `public.documents` + `public.jobs` live (since M3, 2026-11-22) | COMPLETED (parent-reported) |
| Migration 016 (bucket) | **APPLIED + VERIFIED live 2026-11-23:** `pdf-documents` bucket, private, 100 MB limit, 3 storage policies verified via SQL + Storage UI | COMPLETED (parent-reported) |
| Migration 017 (partial index) | **FAILED live 2026-11-23:** `ERROR 42703: column "deleted_at" does not exist` | FAILED (parent-reported) |
| Migration 018 (add column) | Written, **NOT applied, NOT committed** (files exist on disk, untracked — see §3) | PENDING |
| 017's DROP INDEX state | **UNKNOWN** — whether the `DROP INDEX` committed before the `CREATE` failed was never verified (the browser stopped per its stop rule; the verification query was not run). **Step 0 of §5 checks this first.** | BLOCKED (needs the Step 0 query) |
| Alembic 0001–0009 on live Postgres | **NEVER run** against live Postgres — SQLite only, in tests and local E2E harnesses (Workstream B re-verified up/down/up on fresh SQLite, landing on `0009`) | PENDING |
| Supabase backups | **NONE exist and none can exist on the free plan** ("LAST BACKUP: No backups") | FAILED (precondition unmeetable — see §7) |
| Backup waiver for 016/017 | Owner waived the backup precondition on 2026-11-23 for these two migrations only, because both are data-neutral | COMPLETED (owner decision) |
| Live project access | `officerpath-ai` lives on the owner's **original** Supabase account, signed in via **GitHub** (`hasankhan62742-beep`). The `pzmir62742@gmail.com` email login holds **only** the separate `petpassport` project and has **no access** to `officerpath-ai`. Never run these steps while signed in as the PetPassport account. | VERIFIED (parent-reported) |

---

## 3. Migration files inspected (first-hand, this workstream)

Files present in `supabase/migrations/`: 015 (+ down), 016 (+ down), 017 (+ down), 018 (+ down).

| File | Purpose | Destructive ops (`DROP TABLE` / `DROP COLUMN` / `TRUNCATE` / `DELETE FROM`) | Idempotent | Live status |
|---|---|---|---|---|
| `015_documents_jobs.sql` | Creates `public.documents` + `public.jobs` (RLS on, 7 policies), plain unique index `(user_id, content_hash)`, `pdf-documents` bucket + 3 storage policies | **0** | Yes (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING`) | COMPLETED (tables live; bucket superseded by 016) |
| `016_pdf_documents_bucket.sql` | Creates the `pdf-documents` bucket + 3 storage policies only; touches no table, policy, trigger, or Edge Function | **0** | Yes (guards throughout) | COMPLETED (applied + verified 2026-11-23) |
| `017_documents_hash_partial_unique.sql` | Drops the plain unique index, recreates it as partial (`WHERE deleted_at IS NULL`) | **0** | Yes (`IF EXISTS` / `IF NOT EXISTS`) | FAILED (42703 — see §4) |
| `018_documents_deleted_at.sql` | Adds **one** nullable column `deleted_at timestamptz` to `public.documents`; touches no rows, no other table/index/policy/function | **0** | Yes (`ADD COLUMN IF NOT EXISTS`) | PENDING (not applied) |
| `015_documents_jobs_down.sql` | Drops storage policies, bucket row, table policies, then `jobs` + `documents` tables | **3** (`DELETE FROM storage.buckets`, `DROP TABLE jobs`, `DROP TABLE documents`) | No — destructive | Never run live; see §10 |
| `016_pdf_documents_bucket_down.sql` | Drops the 3 storage policies + the bucket row | **1** (`DELETE FROM storage.buckets`) | No — fails while objects remain (storage enforces it) | Never run live; see §10 |
| `017_documents_hash_partial_unique_down.sql` | Drops the partial index, restores the plain unique index | **0** | No — fails while a live + deleted row pair share a user + hash; re-introduces the M6 bug | Never run live; see §10 |
| `018_documents_deleted_at_down.sql` | Drops the partial index, then drops the `deleted_at` column | **1** (`DROP COLUMN deleted_at`) | No — only safe while zero rows are soft-deleted; re-create the plain index afterwards if dedup is still wanted | Never run live; see §10 |

**018 commit status — PENDING:** `supabase/migrations/018_documents_deleted_at.sql` and `018_documents_deleted_at_down.sql` exist on disk but are **untracked** (`git status` shows `??` for both). They were written by the parent on 2026-11-23 and are not in any commit. They must be committed before any push that claims to contain them; this report's commit intentionally does **not** include them (Workstream C's scope is the report file only). The parent/owner decides when to commit 018.

**No secrets in any migration file** — all eight files contain SQL only; no keys, passwords, or tokens (verified by reading all eight files in full).

---

## 4. The `deleted_at` gap — root cause (verified first-hand)

**The failure:** applying 017 live returned `ERROR 42703: column "deleted_at" does not exist`, because the `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL` references a column the live table lacks.

**Evidence (all checked in this workstream):**

- `supabase/migrations/015_documents_jobs.sql` — the `CREATE TABLE public.documents` lists columns `id, user_id, title, storage_path, file_type, file_size_bytes, page_count, content_hash, metadata, created_at`. **No `deleted_at`.** The 015 file was written before soft-delete existed in the engine.
- `app/db/models.py:100` — the engine `Document` model declares `deleted_at: Mapped[datetime | None]` (nullable `timestamptz`); lines 127–128 define the partial index with `deleted_at IS NULL` (both SQLite and Postgres variants).
- `alembic/versions/0001_m1_engine_tables.py:169` — Alembic 0001 creates `documents` **with** a `deleted_at` column. So every engine-managed database (SQLite tests, local E2E) has the column; only the live Supabase table (built by 015, not by Alembic) lacks it.
- `alembic/versions/0006_m6_tests.py:105, 144–145` — 0006 also creates the `deleted_at` column and the partial index when it creates the table — but only when the table is absent (see below).
- **Why Alembic cannot repair it:** `alembic/versions/0006_m6_tests.py`, `_create_documents_if_missing()` — returns `False` immediately when the `documents` table already exists (`if bind is None or _has_table(bind, "documents"): return False`). On live, the table exists (from 015), so 0006 skips the whole creation block, including the `deleted_at` column. The Alembic run will therefore **never** add the missing column. Supabase migration 018 is the only repair path.
- **Jobs table — no second gap (verified):** the engine `Job` model (`app/db/models.py:133–155`) lists exactly the columns 015's `public.jobs` has (`id, user_id, document_id, status, idempotency_key, retry_count, error, result_summary, created_at, started_at, completed_at`). The parent checked this live at the same time as the 017 failure. No second migration is needed for `jobs`.

**Blast radius of the gap (why 018 is not optional):** without `deleted_at`, the M4 soft-delete path (`DELETE /api/v1/documents/{id}` sets `deleted_at`) would also 500 live, not just 017. The column is required by the engine's normal operation, not only by the index. 018 is a one-column, nullable, no-rows-touched change — the smallest possible repair.

---

## 5. Migration execution order

Run in this order. Every step is an **owner step** in the Supabase Dashboard (SQL Editor) or on the owner's machine — no agent applies these migrations. Each step's verification query must pass before the next step starts.

### Step 0 — Check the live index state FIRST (REQUIRES OWNER APPROVAL)

017's `DROP INDEX` may or may not have committed before its `CREATE` failed. The SQL Editor's transaction behaviour for a multi-statement paste is not assumed here — **check before doing anything else:**

```sql
select indexname, indexdef from pg_indexes
  where tablename = 'documents' and indexname = 'documents_user_hash_idx';
```

- **If the query returns the PLAIN index** (`create unique index ... on public.documents (user_id, content_hash)` with **no** `WHERE` clause): the DROP did not commit (or rolled back). The live state is exactly 015's. Proceed to Step 1.
- **If the query returns NO row:** the DROP committed and the CREATE failed — the table currently has **no** `(user_id, content_hash)` unique index at all. Dedup is unenforced at the database level until Step 2 completes. Do not run any upload-heavy traffic until 017 is re-applied; proceed to Step 1 immediately (018 first, then 017).
- **If the query returns the PARTIAL index** (`WHERE deleted_at IS NULL`): 017 somehow applied despite the reported error — do not re-run 017 blindly; record the indexdef and skip to Step 3's verification.

### Step 1 — Apply 018: add the `deleted_at` column (REQUIRES OWNER APPROVAL)

- File: `supabase/migrations/018_documents_deleted_at.sql` (commit it first — see §3).
- How: Dashboard → SQL Editor → New query → paste the file → Run.
- What it does: `alter table public.documents add column if not exists deleted_at timestamptz;` — one nullable column, no rows touched, no other object changed.
- Verify (SQL Editor):
  ```sql
  select column_name, data_type from information_schema.columns
    where table_schema = 'public' and table_name = 'documents'
      and column_name = 'deleted_at';
  -- expect one row: deleted_at, timestamp with time zone
  ```
- If it fails: the statement is guarded (`IF NOT EXISTS`) — re-running is safe. A permission error means the Dashboard user needs the project's owner role; do not retry with a different SQL path. Reversal: `018_documents_deleted_at_down.sql` (only while zero rows are soft-deleted — see §10).

### Step 2 — Re-run 017: partial unique index (REQUIRES OWNER APPROVAL)

- File: `supabase/migrations/017_documents_hash_partial_unique.sql` (unchanged — re-run the same file).
- How: same as Step 1. **Only after Step 1's verification passes.**
- What it does: drops 015's plain unique index (guarded no-op if already gone — this is what makes the Step 0 uncertainty safe) and recreates it as partial (`WHERE deleted_at IS NULL`). Two LIVE rows with the same user + hash still cannot exist (dedup preserved); deleted rows no longer block a fresh upload.
- Verify (SQL Editor):
  ```sql
  select indexname, indexdef from pg_indexes
    where tablename = 'documents' and indexname = 'documents_user_hash_idx';
  -- indexdef MUST contain: WHERE deleted_at IS NULL
  ```
- Behaviour check (the M6 bug, live): upload a file, delete the document, re-upload the SAME file — the second upload must succeed with a NEW document id (not a 500, not a replay of the deleted document). If it still 500s, 017 did not apply — check the indexdef above before anything else.
- Reversal: `017_documents_hash_partial_unique_down.sql` — WARNING: restoring the plain index FAILS while a live row and a deleted row share a user + hash, and it re-introduces the M6 bug. Only roll back 017 after checking no such row pairs exist:
  ```sql
  select user_id, content_hash, count(*) from public.documents
    group by 1, 2 having count(*) > 1;
  -- expect: no rows
  ```

### Step 3 — Alembic 0001–0009 on live Postgres (REQUIRES OWNER APPROVAL)

The engine's own tables live in the SAME Supabase Postgres as the 015 tables. They are created by Alembic, NOT by the Dashboard.

- Run from the repo root on a machine with the live `DATABASE_URL` set (`postgresql+psycopg://...` — the Dashboard secret, never committed, never pasted into chat):
  ```bash
  alembic current        # expect: (no version) on a fresh live DB
  alembic upgrade head   # applies 0001 -> 0009 in order
  alembic current        # expect: 0009 (head)
  ```
- What each revision adds (verified from the files; chain is linear, `down_revision` verified for all nine):

  | Revision | Adds | Notes |
  |---|---|---|
  | 0001 `0001_m1_engine_tables` | Phase 1 engine tables (17), **including** `documents` **with** `deleted_at` | On live, `documents`/`jobs` already exist from 015 — 0001's own `documents`/`jobs` creation is the part 0006 later made conditional; see the 0006 note below |
  | 0002 `0002_m3_layout_column` | `document_pages.layout_applied` | Column add only |
  | 0003 `0003_m3_student_profiles` | `student_profiles` | |
  | 0004 `0004_m4_profile_timestamps` | Server defaults on `student_profiles.created_at/updated_at` | Never refuses a downgrade |
  | 0005 `0005_m5_subjects` | `subjects` / `topics` / `question_subjects` (+ 13 seeded subjects) | Seed uses hex UUIDs (M5 fix) |
  | 0006 `0006_m6_tests` | `marking_configs` / `test_templates` / `test_sessions` / `test_question_snapshots` (+ PPSC default marking config); `documents`/`jobs` **IF NOT EXISTS** | On live this is a no-op for `documents`/`jobs` — it does **not** add `deleted_at` (§4). Must NOT be skipped: the same revision also creates the test tables |
  | 0007 `0007_m7_exam` | `student_responses` / `test_results` (incl. `unknown_count`) | |
  | 0008 `0008_m8_collections` | `student_question_collections` | |
  | 0009 `0009_m9_notifications` | `notifications` (per-user only, no broadcast NULL) | Head revision |

- Verify (SQL Editor, after `upgrade head`):
  ```sql
  select version_num from alembic_version;
  -- expect: 0009_m9_notifications
  select count(*) from information_schema.tables
    where table_schema = 'public'
      and table_name in ('student_profiles','subjects','test_templates',
        'test_sessions','student_responses','test_results',
        'student_question_collections','notifications');
  -- expect: 8
  ```
- If `upgrade head` fails midway: Alembic stops at the failed revision — DO NOT re-run blindly. Read the error, fix the cause (usually a missing `DATABASE_URL` or a stale connection), then run `alembic upgrade head` again; it resumes from the last applied revision. **Never hand-edit `alembic_version`.**
- Local proof that the chain works: Workstream B re-ran the CI's exact Alembic sequence on a fresh SQLite database (`upgrade head` → `downgrade base` → `upgrade head` → `current`) and landed on `0009_m9_notifications (head)`. SQLite cannot prove the Postgres-only parts (RLS, `gen_random_uuid()`, storage) — those are proven only by the Dashboard queries above.

### Step 4 — Deploy-time smoke test (after migrations AND the first deploy)

Per the M10 runbook §3 (unchanged) and Workstreams D/E: `GET /health` → 200 (not `degraded`); `GET /version` shows the deployed commit; unauthenticated `POST /api/v1/documents/register` → 401; register → 201; one async job queued → done; review list loads. **STOP CONDITION (live phone verification):** the three acceptance files — PPSC-66 PDF, computer table photo, Paper 60 photo — parse through the WEB upload on the owner's phone and the resulting questions match the engine's stored rows. No fix is "done" until the phone proves it.

---

## 6. Staging verification (honest limitation)

**There is no staging Supabase project.** No second project, no staging database, and no staging environment variable set exists for OfficerPath AI. Every verification below is therefore done against the live project, in order, with a verification query after each step — that is the staging discipline available, and it is the reason every step in §5 is idempotent and individually verified.

What substitutes for a staging run (all VERIFIED in this workstream or Workstream B):

- **Alembic chain:** proven on a fresh SQLite database (Workstream B, CI's exact up/down/up sequence → `0009` head). This proves revision ordering and downgrade code, not Postgres behaviour.
- **Supabase SQL files:** all four up-files are idempotent (`IF NOT EXISTS` / `ON CONFLICT DO NOTHING` / `IF EXISTS`) and were read in full (§3). Re-running a failed step is safe by construction; a failed step leaves the previous state intact except for the Step 0 uncertainty, which is why Step 0 exists.
- **Local engine behaviour:** the M10 E2E harnesses proved the engine against the same schema on SQLite (PPSC-66 41/41/27, table photo 0/0/2, Paper 60 4/4/9 via the web UI — as *reported* in M10, not re-run here).
- **What staging cannot prove:** Postgres-only behaviour (RLS enforcement, `gen_random_uuid()`, storage policies, `CHECK` constraints) is proven only by the live Dashboard verification queries in §5. If the owner later creates a staging project, the same files apply there first — the runbook needs no change, only a different project ref.

**Recommendation (not a gate):** before any future data-changing migration, create a free-tier staging project and run the migration there first. For the current data-neutral steps (018, 017), the idempotency + per-step verification in §5 is sufficient — that is the same reasoning behind the owner's backup waiver for 016/017.

---

## 7. Pre-migration backup and recovery procedure (corrected)

### 7.1 The free-plan reality

- **Scheduled backups do not exist on the free plan.** Dashboard → Database → Backups shows "LAST BACKUP: No backups" and "Free Plan does not include project backups. Upgrade to the Pro Plan for up to 7 days of scheduled backups." Point-in-time recovery is a Pro add-on (quoted in the Dashboard at $100/month).
- **Consequence:** the M10 runbook's precondition "confirm a recent backup exists" can never be satisfied while the project stays on the free plan. Any runbook that requires it is unexecutable. This section replaces that precondition.

### 7.2 The three backup options (in order of preference)

| Option | What it is | Cost | When to use |
|---|---|---|---|
| **A. Manual `pg_dump` (recommended before any data-changing migration)** | A full logical dump of the live Postgres, taken by the owner from his own machine, stored locally | $0 | Before Alembic on live, and before any future migration that touches rows. This is the only $0 backup that exists on the free plan. |
| **B. Pro plan** | Upgrades the project to Pro: daily scheduled backups (7 days retention) included | $25/month (parent-provided figure — confirm the current price in the Dashboard before paying) | When the project has real student data worth protecting automatically. Recommended before public launch, not required for the current data-neutral steps. |
| **C. Owner waiver (data-neutral migrations only)** | The owner explicitly waives the backup precondition for a named migration | $0 | **Only** for migrations that touch no rows: 016 (bucket + policies), 017 (index only), 018 (one nullable column, no rows touched). The owner already waived it for 016/017 on 2026-11-23. **Never** waive for a data-changing migration. |

### 7.3 Manual `pg_dump` procedure (Option A)

Run on the owner's machine (Postgres client tools required — `pg_dump` ships with PostgreSQL; install it if missing). The connection string comes from Dashboard → Settings → Database → Connection string (URI mode); the password is the database password set in the Dashboard. **Never paste the connection string or password into chat, and never commit it.**

```bash
# Full logical dump (schema + data), custom format for selective restore.
pg_dump "postgresql://postgres:<password>@db.gliebuyyjguxrwdfuakz.supabase.co:5432/postgres" \
  -Fc -f officerpath-ai-backup-YYYY-MM-DD.dump

# Quick sanity check that the dump is real (lists the tables it contains).
pg_restore -l officerpath-ai-backup-YYYY-MM-DD.dump | head -30
# Expect: public.documents, public.jobs, auth.users references, storage schema rows.
```

- **Verify the dump before relying on it:** the `pg_restore -l` listing must show `public.documents` and `public.jobs`. A zero-byte or error file is not a backup.
- **Store it off the machine you dumped from** (a second drive or the owner's PC, not only the VM). A backup on the same disk as the database protects against a bad migration, not against disk loss.
- **Restore (only if a migration goes wrong):** restore into an empty database, never over the live one in place — then point the app at the restored copy after verifying row counts:
  ```bash
  createdb officerpath-ai-restored
  pg_restore -d officerpath-ai-restored officerpath-ai-backup-YYYY-MM-DD.dump
  ```

### 7.4 Waiver rule (Option C — the rule, not just the instance)

A backup waiver is valid **only** when all three conditions hold:

1. The migration touches **no rows** (verified by reading the file: 016, 017, 018 all score 0 on the destructive-op scan in §3).
2. The migration is **idempotent** (safe to re-run if it fails halfway).
3. The owner **names the migration** when waiving (as he did for 016/017 on 2026-11-23).

A waiver is **never** valid for: any migration that updates, deletes, or rewrites rows; any `DROP TABLE` / `DROP COLUMN` on a table that holds user data; the Alembic run on live if it ever includes a data migration (it currently does not — 0001–0009 are DDL-only, verified from the files); or the 015 down migration. For those, Option A (manual dump) or B (Pro) is required first.

### 7.5 Recovery procedure (if a migration goes wrong)

1. **STOP.** Do not run the next migration, do not re-run blindly, do not hand-edit `alembic_version`.
2. **Read the exact error** from the SQL Editor or Alembic output and record it.
3. **Check the actual state** with the verification queries for that step (§5) — determine what committed and what did not before deciding anything.
4. **If the failed step is idempotent (016/017/018):** fix the cause (usually a missing column — now 018 — or a permission), then re-run the same file. Re-running is safe by construction.
5. **If Alembic failed midway:** it stops at the failed revision. Fix the cause, run `alembic upgrade head` again; it resumes from the last applied revision.
6. **If rows were lost or corrupted (not expected from 016/017/018):** restore from the Option A dump or the Pro backup into a fresh database, verify row counts against the pre-migration numbers, then re-point the app. Do **not** restore over the live database in place.
7. **If a downgrade is needed instead:** see §10 — the refusal guards exist precisely so a downgrade never deletes user data silently. If a downgrade refuses, the correct move is almost always to leave the schema in place and roll back only the service (Render/Vercel rollback per `docs/phase2/rollback-runbook.md`).

---

## 8. RLS, storage, Auth, and access review

### 8.1 RLS on `documents` / `jobs` (015) — VERIFIED (file read)

- RLS is enabled on both tables (`alter table ... enable row level security`).
- `documents`: users SELECT + INSERT their own rows only (`auth.uid() = user_id`); **no client UPDATE/DELETE policy** — documents are immutable for clients; admins SELECT all via `public.is_admin()`.
- `jobs`: users SELECT + INSERT their own; the **only** client UPDATE is cancel (`status = 'cancelled'`, own rows only); no client DELETE; admins SELECT all via `public.is_admin()`.
- The engine writes job status/results with the **service-role key**, which bypasses RLS — client policies are intentionally narrow so no client can forge a job outcome.

### 8.2 Storage bucket + policies (016, live) — COMPLETED (parent-reported)

- Bucket `pdf-documents`: **private**, 100 MB cap, MIME types PDF / TXT / DOCX / JPEG / PNG / WebP / TIFF.
- Three policies: users upload under their own uid folder; users view their own; admins view all. **No UPDATE/DELETE policy** — uploaded documents are immutable for clients; cleanup is done by the backend (service role) after a job completes.
- **Dependency note:** the policies call `public.is_admin()`. That function is **not defined in any migration file in this repo** (001–014 predate this project and are not in the repo). Its existence live is **inferred, not directly verified**: 015's admin policies exist live, and 016's admin policy was created successfully on 2026-11-23 — Postgres validates function existence at `CREATE POLICY` time, so the function must exist live. If it ever disappears, the admin policies fail at creation, not silently.

### 8.3 Supabase Auth configuration — PENDING (live re-check outstanding)

From the M3 report (2026-11-22, cited as reported, not re-run here):

- Sign-up allowed; **email confirmation REQUIRED** (`mailer_autoconfirm = false` — no session until the user confirms).
- 5 Edge Functions ACTIVE (not in this runbook's scope).
- **Redirect-URL allowlist NOT conclusively proven.** The web app requests `${window.location.origin}/auth/callback` on register and `/auth/callback?type=recovery` on password recovery (verified in `web/app/register/page.tsx:52` and `web/app/forgot-password/page.tsx:36` by this workstream). A re-sign-up with that `redirect_to` reached the send step (429 rate-limit) rather than a redirect error — consistent with the URL being allowed, but the rate limit stopped it before a 200. **Owner check (before launch):** Dashboard → Authentication → URL Configuration → Redirect URLs must include `http://localhost:3000/auth/callback` (local dev) **and** the production callback URL (which only exists after the Vercel deploy — Workstream E). Do not claim this is proven until the Dashboard shows both entries.
- **Service-role key is not obtainable from the VM** (Management API 403 in M3). Consequence: admin operations that need it — deleting the unconfirmed M3 test user `officerpath.m3.test@gmail.com`, admin-confirming users — can only be done by the owner in the Dashboard. The test user still exists in live Auth (Workstream A blocker B9).

### 8.4 Database access permissions

- **Engine (Render):** connects with the Postgres connection string (`DATABASE_URL`, Dashboard secret) plus the Supabase URL + anon key + service-role key (all `sync: false` in `render.yaml` — Dashboard secrets, never in the repo; Workstream A §5).
- **Web app (Vercel):** receives only `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`. The frontend **never** receives the service-role key or `DATABASE_URL` (M3/Phase 2 rule, verified in code by M3).
- **VM / agents:** no live SQL access and no service-role key — by design. All live steps are owner Dashboard steps.
- **Client (anon key):** RLS-gated as in §8.1–§8.2; the anon key alone cannot read another user's documents or jobs, and cannot write job outcomes.

---

## 9. Post-migration verification (complete checklist)

Run every query in the SQL Editor unless noted. Each expected result is stated; anything else means **stop and investigate**.

| # | Check | Query / action | Expect | Status |
|---|---|---|---|---|
| V0 | Live index state (Step 0) | `select indexname, indexdef from pg_indexes where tablename = 'documents' and indexname = 'documents_user_hash_idx';` | Plain index, no index, or partial index — record which (§5 Step 0) | BLOCKED |
| V1 | 018 column exists | `select column_name, data_type from information_schema.columns where table_schema = 'public' and table_name = 'documents' and column_name = 'deleted_at';` | One row: `deleted_at`, `timestamp with time zone` | PENDING |
| V2 | 017 partial index | `select indexname, indexdef from pg_indexes where tablename = 'documents' and indexname = 'documents_user_hash_idx';` | `indexdef` contains `WHERE deleted_at IS NULL` | PENDING |
| V3 | 017 behaviour (M6 bug) | Upload a file → delete the document → re-upload the SAME file | Second upload succeeds with a NEW document id (not a 500) | PENDING |
| V4 | 016 bucket (already done) | `select id, public, file_size_limit from storage.buckets where id = 'pdf-documents';` + policies query | One row: `pdf-documents`, `false`, `104857600`; three policies | COMPLETED (parent-reported 2026-11-23) |
| V5 | 015 tables + RLS | `select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename in ('documents', 'jobs');` | `rowsecurity = true` for both | COMPLETED (parent-reported, M3) |
| V6 | Alembic version | `select version_num from alembic_version;` | `0009_m9_notifications` | PENDING |
| V7 | Phase-2 tables | `select count(*) from information_schema.tables where table_schema = 'public' and table_name in ('student_profiles','subjects','test_templates','test_sessions','student_responses','test_results','student_question_collections','notifications');` | `8` | PENDING |
| V8 | Health after deploy | `GET /health` | 200 (not `degraded`) | PENDING (needs deploy) |
| V9 | Phone acceptance | Three acceptance files through the web upload on the owner's phone | Questions match stored rows | BLOCKED (owner device only) |

---

## 10. Rollback limitations

### 10.1 Supabase migrations

| File | What the down file does | Limitation |
|---|---|---|
| 015 down | Drops storage policies, bucket row, table policies, then `jobs` + `documents` tables | **Destructive and irreversible without a backup.** Never run on live without the owner explicitly approving it with a verified backup (Option A or B) in hand. Confirm `documents` + `jobs` are empty or exported first. Alembic 0001 must be downgraded FIRST if applied (it references `documents`/`jobs`). |
| 016 down | Drops the 3 storage policies + the bucket row | **Fails while objects remain** (storage enforces it) — empty the bucket first (Dashboard → Storage). Never deletes uploaded files. The 015 tables are untouched. |
| 017 down | Drops the partial index, restores the plain unique index | **Fails while a live row and a deleted row share a user + hash**, and re-introduces the M6 bug (delete-then-re-upload 500s). Only run after the `group by` check in §5 Step 2 returns no rows. |
| 018 down | Drops the partial index, then drops the `deleted_at` column | **Only safe while zero rows are soft-deleted** — check `select count(*) from public.documents where deleted_at is not null;` (must be 0) or the soft-delete markers are lost. Re-create the plain unique index afterwards if dedup enforcement is still wanted. |

### 10.2 Alembic downgrades (0003–0009)

One revision at a time, newest first (`alembic downgrade -1`, repeat). Full table in `docs/phase2/rollback-runbook.md` §3; the refusal rule is the safety net:

| Revision | Drops | Refuses when |
|---|---|---|
| 0009 | `notifications` + 2 indexes | Table holds ANY rows |
| 0008 | `student_question_collections` + index | Table holds ANY rows |
| 0007 | `student_responses` + `test_results` | Either table holds ANY rows |
| 0006 | `marking_configs` / `test_templates` / `test_sessions` / `test_question_snapshots` | `test_sessions` or `test_templates` holds ANY rows |
| 0005 | `subjects` / `topics` / `question_subjects` | `question_subjects` holds ANY user assignments |
| 0004 | Server defaults on `student_profiles` timestamps | Never refuses (no data dropped) |
| 0003 | `student_profiles` + index | Table holds ANY rows |

**If a downgrade refuses, STOP.** The correct move is almost always to leave the schema in place and roll back only the service (Render/Vercel rollback). Archiving rows to make a downgrade pass is a deliberate, owner-approved data operation — export the rows first (`pg_dump` of the affected tables), confirm the export, and only then downgrade.

**Never downgrade on live:** 0001 (drops ALL 17 engine tables with NO refusal guard) and 0002 (drops the `layout_applied` column and its values, no refusal). 0001 is never rolled back on live.

---

## 11. Owner actions required

In order. Production-impacting steps require the owner's explicit approval at the time; nothing in this runbook authorises an agent to apply a migration.

1. **Commit 018** (or have the parent do it): `supabase/migrations/018_documents_deleted_at.sql` + `_down.sql` are untracked. They must be committed before any push that claims to contain them. — PENDING
2. **Step 0 — check the live index state** (Dashboard → SQL Editor, query in §5 Step 0) and record which of the three states the index is in. — BLOCKED (first action)
3. **Apply 018, then re-run 017**, each with its verification query (§5 Steps 1–2). The backup waiver for 016/017 does **not** automatically cover 018 — but 018 is the same class (data-neutral, one nullable column, no rows touched); the owner should name it in the waiver, or take a manual dump first (§7.4). — REQUIRES OWNER APPROVAL
4. **Alembic 0001–0009 on live Postgres** from a machine with the live `DATABASE_URL`, then the V6/V7 verification queries. Take a manual `pg_dump` first (Option A) — this is the first step that creates tables holding user data, so the waiver rule does not apply. — REQUIRES OWNER APPROVAL
5. **Confirm the redirect-URL allowlist** (Dashboard → Authentication → URL Configuration): `http://localhost:3000/auth/callback` now, and the production callback URL after the Vercel deploy. — PENDING
6. **Delete the unconfirmed M3 test user** `officerpath.m3.test@gmail.com` (Dashboard → Authentication → Users). — PENDING
7. **Decide the backup story before public launch:** Pro ($25/month, daily backups) or a standing manual `pg_dump` routine. The free plan will never back the project up. — PENDING (not a gate for 018/017/Alembic)
8. **Do not do:** no `DROP TABLE` / `DROP COLUMN` on live without a verified backup; no hand-editing `alembic_version`; no running these steps while signed in as the PetPassport account (`pzmir62742@gmail.com` — no access to this project); no paid upgrade without the owner's explicit say-so.

---

## Appendix — evidence (commands and files read in this workstream)

- `ls supabase/migrations/` → 015/016/017/018, each with a down file (018 pair untracked).
- `git status --short` → `?? supabase/migrations/018_documents_deleted_at.sql`, `?? supabase/migrations/018_documents_deleted_at_down.sql`; otherwise clean at head `a4337af`.
- Read in full: `015_documents_jobs.sql` (no `deleted_at` in the `documents` CREATE TABLE), `016_pdf_documents_bucket.sql`, `017_documents_hash_partial_unique.sql`, `018_documents_deleted_at.sql`, all four down files.
- Destructive-op scan (`grep -ciE "drop table|drop column|truncate|delete from"`): up-files 015/016/017/018 → **0 each**; down-files 015 → 3, 016 → 1, 017 → 0, 018 → 1.
- `grep -n "deleted_at" app/db/models.py` → lines 100 (Document column), 127–128 (partial index), 423 (second model column).
- `grep -n "deleted_at" alembic/versions/0001_m1_engine_tables.py` → line 169 (column created).
- `grep -n "deleted_at" alembic/versions/0006_m6_tests.py` → lines 34, 105, 144–145 (column + partial index, created only when the table is absent).
- `_create_documents_if_missing()` in 0006: returns `False` when the table exists — verified by reading the function (lines ~80–150).
- Job model vs 015: `app/db/models.py:133–155` — all 11 columns match 015's `jobs` table exactly.
- Alembic chain: `grep "^revision" alembic/versions/*.py` → linear chain 0001 → 0009 (`down_revision` verified for each file); head `0009_m9_notifications`.
- Redirect URLs: `web/app/register/page.tsx:52` (`emailRedirectTo: ${window.location.origin}/auth/callback`), `web/app/forgot-password/page.tsx:36` (`redirectTo: .../auth/callback?type=recovery`); M3 report §4 (allowlist not conclusively proven).
- `public.is_admin()`: no definition in any file under `supabase/` (grep, no hits) — pre-existing project function; existence inferred from 015 policies live + 016 apply success (§8.2).
- Auth config: M3 report (cited as reported) — `mailer_autoconfirm = false` (confirmation REQUIRED); service-role key not obtainable from the VM (Management API 403).
- Live facts (016 applied + verified, 017 failed 42703, no backups on free plan, waiver for 016/017, GitHub-linked account): parent-reported, browser-verified 2026-11-23 — **not** re-checked in this workstream (no Supabase access from the VM).

**Workstream C conclusion:** the M10 runbook is superseded. The free plan has no backups (precondition unmeetable — corrected procedure in §7); 016 is done; 017 failed on a real schema gap (`deleted_at` missing from the live table, verified first-hand in the files); 018 is the one-column repair, written but uncommitted and unapplied; Alembic 0006 will never repair the gap because it skips existing tables. The remaining path is short and fully specified: Step 0 index check → 018 → re-run 017 → Alembic 0001–0009 → smoke test → phone acceptance. No step here is data-destructive; the only irreversible action in the whole chain (015 down) is explicitly fenced in §10.
