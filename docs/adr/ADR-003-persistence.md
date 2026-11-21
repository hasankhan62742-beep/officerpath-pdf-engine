# ADR-003 — Persistence: SQLAlchemy + Alembic for engine tables, supabase-py kept for Auth + documents/jobs

- **Status:** DECIDED in M1 (2026-11-21) — implements the §14 schema on the approved hosting baseline (ADR-001).
- **Deciders:** Phase 1 M1 (owner approved ADR-001 + ADR-002 on 2026-11-21; this ADR records the M1 persistence choice, which the prompt §14 requires — SQLAlchemy 2.x + Alembic).
- **Context source:** Ultimate Master Prompt §5 (layered design, persistence layer = repositories over SQLAlchemy), §14 (normalized PostgreSQL schema + Alembic), §21 (code quality); v2 §12 (same).

## Context

The skeleton persisted only through supabase-py (PostgREST) to two
tables (`documents`, `jobs`, created by Supabase migration 015). The
prompt §14 requires 15+ entities (pages, stages, OCR blocks,
questions, options, assets, answers, evidence, sources, reports,
corrections, review history, errors, audit log, rule-set versions)
with UUID keys, FKs, indexes, soft-delete, and append-only audit
tables — plus reversible migrations tested up and down. PostgREST
alone cannot express that schema, and hand-writing 15 tables of raw
Supabase SQL with no migration runner would repeat the 015 problem
(no down path, no local test).

## Decision

1. **SQLAlchemy 2.x models** (`app/db/models.py`) define the full §14
   schema. `documents` + `jobs` are MIRROR models of the 015 tables
   (same table names, same columns + `content_hash`) so the engine can
   join across them; they are NOT created by Alembic.
2. **Alembic** manages ONLY the new engine-owned tables (revision
   `0001_m1_engine_tables`, 15 tables). It runs against the SAME
   Supabase Postgres via `DATABASE_URL` (postgresql+psycopg). Apply
   order is enforced by documentation + FKs: 015 first, then Alembic.
3. **supabase-py is KEPT** for exactly two things: Auth verification
   (`auth.get_user` — never decode JWTs locally) and the
   documents/jobs PostgREST flow (register/status/retry), which is
   tested (22 tests) and must not be rewritten mid-Phase-1. It is NOT
   used for the new §14 tables.
4. **Storage abstraction** (`app/storage/`): `StorageBackend` protocol
   with a local-disk implementation first. Originals are immutable
   (write-once, safe generated names, traversal-guarded). S3-compatible
   backends are added later behind the same interface; the durable
   home for originals on Render is the Supabase `pdf-documents`
   bucket, because Render's filesystem is ephemeral.
5. **Stage history**: `processing_stages` rows are written through a
   `StageRecorder` protocol. With `DATABASE_URL` unset the engine
   still serves (Null recorder, logs only) — the API must never fail
   for lack of the analytics database.

## Consequences

- M1 tables are fully implemented as models + migration; the M2–M6
  tables exist as models + migration now so later milestones fill
  them, not redesign them. "Implement the M1 tables fully and the
  rest as models+migrations ready for later stages" (M1 scope) is met.
- Two migration systems now exist (Supabase SQL 015 + Alembic 0001).
  That is a deliberate split: 015 owns the Supabase-managed surface
  (RLS, bucket, client policies) that only Supabase SQL can express;
  Alembic owns engine tables. The split and the apply order are
  documented in `docs/migration-015-apply.md`; a future consolidation
  (Alembic owning everything, with RLS in raw SQL inside revisions)
  is a post-Phase-1 cleanup, not M1 work.
- Local migration testing is SQLite-only (no local Postgres/Docker on
  the VM). Postgres-only behaviour (RLS, `gen_random_uuid()`,
  bucket) is verified only by the Dashboard queries in
  `docs/migration-015-apply.md`. This limitation is labelled in the
  M1 report, not hidden.
- Connection pooling is small by design (pool_size=2, max_overflow=2):
  Render free is 512 MB / 0.1 CPU and Supabase free Postgres caps
  connections. M7 re-tunes with measured load-test numbers.

## Alternatives considered

- **PostgREST-only for all §14 tables:** rejected — no FK/index
  enforcement in code, no reversible migrations, 15 hand-written SQL
  files with no runner. The audit (D4) already flagged this.
- **Alembic owning documents/jobs too (replacing 015):** rejected for
  M1 — 015 is written, reviewed, and its RLS/bucket policies are
  Supabase-specific; replacing it now would churn a reviewed
  artefact for no user-visible gain. Revisit post-Phase-1.
- **Prisma/Drizzle/other ORM:** rejected — the prompt mandates
  SQLAlchemy + Alembic, and the team (one engineer + agents) needs
  the smallest new surface, not a second ecosystem.

## Revisit conditions

- If Supabase Postgres direct access (DATABASE_URL) proves
  unavailable at deploy time, Alembic cannot run and the §14 tables
  fall back to Supabase-SQL files mirroring 015 — the models stay
  the same, only the migration runner changes.
- If a second replica is ever run, the in-memory rate limiter and
  the Null recorder must be replaced first (both are single-process).
