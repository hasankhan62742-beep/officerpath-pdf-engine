# Rollback Runbook — OfficerPath AI Phase 2 (M10)

**Status:** documentation only. Nothing here rolls anything back.
The web deploy and the engine deploy roll back SEPARATELY — they
are independent services (doc 06 §1). The frontend never migrates
data, so its rollback is data-safe by construction; the backend
rollback has a database step that must be decided explicitly.

## 1. Roll back the web deploy (Vercel free)

- Vercel Dashboard → project → Deployments → pick the previous
  GOOD deployment → **⋯ → Promote to Production** (instant
  rollback; the previous build is re-served, no rebuild).
- Verify: home loads, login page loads, `/dashboard` (logged out)
  → 307 `/login?next=%2Fdashboard`, `X-Robots-Tag: noindex,
  nofollow` present on `/login`.
- No data step. No env-var change (the rollback re-serves the old
  build with the same env vars). If the bad deploy was caused by a
  bad env var instead of bad code, fix the env var first — rolling
  back the code will not help.
- If the frontend was never deployed (Phase 2 state at M10: local
  only), there is nothing to roll back — the "rollback" is simply
  not deploying.

## 2. Roll back the engine deploy (Render free)

- Render Dashboard → service `officerpath-pdf-engine` →
  **Rollback** (restores the previous deploy — the previous Docker
  image + the env vars as they were at that deploy).
- Verify: `GET /health` → 200; `GET /version` shows the PREVIOUS
  commit; unauthenticated parse → 401; one async job queued →
  done.
- The engine deploy is stateless (the database lives in Supabase,
  not on Render), so rolling back the service does NOT roll back
  any data. Whether the DATABASE also needs rolling back is a
  separate decision — see §3. As a rule: **if the bad deploy only
  changed API/frontend code and the database schema is unchanged,
  roll back the service only and leave the database alone.**

## 3. Roll back the database (Alembic downgrades 0003–0009)

Run from the repo root with the live `DATABASE_URL` set. Alembic
downgrades go ONE revision at a time, newest first:

```bash
alembic current            # confirm where you are (expect 0009)
alembic downgrade -1       # 0009 -> 0008 (drops notifications)
alembic downgrade -1       # 0008 -> 0007 (drops student_question_collections)
# ... repeat as far back as the rollback needs to go
alembic current            # confirm the landing revision
```

### Downgrade behaviour per revision (all verified in the migration code)

| Revision | Drops | Refuses when |
|---|---|---|
| 0009 notifications | `notifications` table + 2 indexes | `notifications` holds ANY rows |
| 0008 collections | `student_question_collections` + index | the table holds ANY rows |
| 0007 exam | `student_responses` + `test_results` | either table holds ANY rows |
| 0006 tests | `marking_configs` / `test_templates` / `test_sessions` / `test_question_snapshots` | `test_sessions` or `test_templates` holds ANY rows |
| 0005 subjects | `subjects` / `topics` / `question_subjects` (+ seeded subjects) | `question_subjects` holds ANY user assignments |
| 0004 profile timestamps | server defaults on `student_profiles.created_at/updated_at` | never refuses (no data is dropped) |
| 0003 profiles | `student_profiles` table + index | `student_profiles` holds ANY rows |

**The refusal rule (doc 03 §6) is the safety net: a downgrade
never deletes user data silently.** If a downgrade raises
`RuntimeError: Refusing to drop ...`, STOP. The correct move is
almost always to LEAVE the schema in place and roll back only
the service (§2): the old code must be able to run against the
newer schema, or the rollback is not safe. Archiving rows to
make a downgrade pass is a deliberate, owner-approved data
operation — export the rows first (`pg_dump` of the affected
tables), confirm the export, and only then downgrade.

### Revisions you do NOT downgrade

- **0001 (Phase 1 engine tables):** the downgrade drops ALL 17
  engine tables with NO refusal guard. Only ever run it on an
  empty/dev database. On live, 0001 is never rolled back.
- **0002 (`layout_applied` column):** the downgrade drops the
  column and its values (no refusal). Only roll back if the
  column's data is genuinely disposable.

### Supabase migrations (015/016/017) rollback

- 016 down: `016_pdf_documents_bucket_down.sql` — drops the three
  storage policies + the bucket. **Fails while objects remain**
  (storage enforces it) — empty the bucket first (Dashboard →
  Storage). Never deletes uploaded files.
- 017 down: `017_documents_hash_partial_unique_down.sql` —
  restores 015's plain unique index. **Fails while a live row and
  a deleted row share a user + hash**, and re-introduces the M6
  bug (delete-then-re-upload 500s). Only run after checking no
  such row pairs exist.
- 015 down: `015_documents_jobs_down.sql` — drops the documents +
  jobs tables. **Destructive and irreversible without the backup
  (§0 of the migration runbook).** Never run on live without the
  owner explicitly approving it with a verified backup in hand.

## 4. After any rollback

1. Re-run the deploy-time smoke test (migration runbook §3):
   `/health` 200, `/version` shows the rolled-back commit,
   unauthenticated parse → 401, one async job queued → done.
2. Check the admin overview counts (`/admin` — users/documents/
   jobs/questions) against the pre-rollback numbers. A mismatch
   means the rollback touched data it should not have — stop and
   restore from the backup instead of rolling forward again.
3. Record what was rolled back and why in `CHANGELOG.md` (a
   rollback is a change like any other).
