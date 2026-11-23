# Workstream A — Repository Safety Audit

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`
**Audit date:** 2026-11-23 (PKT)
**Auditor:** Workstream A subagent (read-only inspection; no file modified except this report)
**Scope:** Repository state, branches, commits, working tree, secret handling, deployment-required files, fixtures, backup status, deployment blockers.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Every finding marked VERIFIED was checked by this audit with the command shown or cited. Findings marked as *parent-reported* come from the parent agent's earlier verification (GitHub API check) and were **not** independently re-checked here — this audit has no GitHub access. Test results (pytest/ruff/mypy/build) are **not** re-run in this workstream; they belong to Workstream B. The M10 figures quoted below are cited from `docs/phase2/PHASE_2_COMPLETION_REPORT.md` as reported, not re-verified.

**Related documents (built on, not duplicated):** `docs/phase2/migration-runbook.md`, `docs/phase2/rollback-runbook.md`, `docs/phase2/deployment-checklists.md`, `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `docs/API.md`, `docs/deploy-render.md`.

---

## 1. Current branches — VERIFIED

| Branch | Head | Contents | Status |
|---|---|---|---|
| `officerpath-phase2-web` (current) | `461c9a2` | Phase 1 engine + Phase 2 web app + docs | VERIFIED |
| `officerpath-phase1-engine` | `69ca62d` | Phase 1 engine only (M0–M8) | VERIFIED |

Checks run:

- `git branch --show-current` → `officerpath-phase2-web`
- `git branch -a` → exactly the two local branches above; no remote-tracking branches (no git remote is configured locally — see §4)
- `git merge-base officerpath-phase1-engine officerpath-phase2-web` → `69ca62d` (the Phase 1 head)
- `git rev-list --count officerpath-phase1-engine..officerpath-phase2-web` → **10** (the ten Phase 2 milestones M1–M10)
- `git branch --contains 69ca62d` → both branches contain the Phase 1 head, so the Phase 2 branch is a strict superset of Phase 1; no Phase 1 work is missing from the deploy branch.

## 2. Commit references — VERIFIED

**Phase 2 branch (`officerpath-phase2-web`), head `461c9a2e5a019c9da51d16effe285e0372189065`:**

| Commit | Subject |
|---|---|
| `461c9a2` (2026-11-23 06:09:30 UTC) | Phase 2 M10: complete QA + deployment readiness |
| `7abb28f` | Phase 2 M9: admin foundation, notifications, security + SEO |
| `094b6b6` | Phase 2 M8: results + student analytics (GAP-7, GAP-8) |
| `2342c4a` | Phase 2 M7: examination interface (GAP-6) |
| `1f23888` | Phase 2 M6: Test Builder (GAP-5) + Alembic 0006 + partial documents hash index |
| `61a121c` | Phase 2 M5: extraction results + question bank |
| `12568ba` | Phase 2 M4: dashboard + document upload (real data) |
| `4fae711` | Phase 2 M3: real Supabase Auth + profiles, ADR-011 job-store unification, CORS |
| `0add038` | Phase 2 M2: Next.js frontend foundation, design system, 11 public pages |
| `dee2f06` | Phase 2 M1: repository audit and web architecture (docs only) |
| `69ca62d` | Phase 1 M8: full suite, final benchmark, docs, deployment guide, Phase 1 completion report |

**Phase 1 branch (`officerpath-phase1-engine`), head `69ca62d`:** M0–M8 history intact (M7 `1051fe4`, M6 `9db0fc0`, M5 `a430297`, M4 `111f3f2`, M3 `d1e11ac`/`a769157`/`670df43`/`5b397ec`, M2 `9e20654`).

**Last known stable commit (deploy target): `461c9a2` — VERIFIED.**
Rollback position: this commit is the deploy baseline. Rollback after deploy follows `docs/phase2/rollback-runbook.md` (Vercel Promote to Production / Render Dashboard Rollback / Alembic downgrades with their stated refusal guards). The Phase 1 branch head `69ca62d` remains the fallback branch point if Phase 2 ever needs to be unwound.

## 3. Working tree status — VERIFIED

- `git status` → **"On branch officerpath-phase2-web, nothing to commit, working tree clean."**
- No uncommitted changes, no untracked files (other than ignored artefacts below).
- Ignored untracked artefacts (all covered by `.gitignore`, none committable): `.coverage`, `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` trees.
- `var/` (local storage root for uploaded originals) is **empty (0 files)** — nothing local to leak or lose.
- Tracked file counts: **488 total** — `app/` 274 files, `web/` 97 files, plus Alembic, docs, scripts, Supabase migrations, config.

**Phase 2 branch contents confirmed present:** backend `app/` (API, pipeline, workers, services, schemas), frontend `web/` (35 `page.tsx` routes across public, dashboard, admin, auth), Alembic migrations, Supabase migrations, `render.yaml`, `Dockerfile`, CI workflow, docs.

## 4. Backup status

| Backup | State | Status |
|---|---|---|
| Local repository (VM) | Branch `officerpath-phase2-web`, head `461c9a2`, clean tree | VERIFIED |
| GitHub push | Branch `officerpath-phase2-web` head `461c9a2` (21 commits, full history) — pushed by the owner from his PC on 2026-11-23 ~12:34 PKT; parent verified via GitHub API (`list_commits` head `461c9a2`, then `7abb28f`, `094b6b6`) | COMPLETED (parent-reported; not independently re-checked in this audit — no GitHub access here) |
| Local git bundles (VM disk) | `officerpath-phase2-web.bundle` (53,066,950 bytes, full history) and `officerpath-deploy-bundle.bundle` (1,088,155 bytes, code-only) present in `~/workspace/`; snapshot manifest `officerpath-push-manifest.txt` present | VERIFIED (presence + sizes only; bundle contents not re-verified in this audit) |
| `web/.env.local` backup | `~/workspace/user/officerpath-web-env-backup.txt`, 390 bytes, mode 0600, same mtime as `web/.env.local` (2026-11-22 12:45) | VERIFIED |
| No git remote configured locally | `git remote -v` returns nothing; the VM repo cannot push or fetch on its own — pushes go through the owner's PC | VERIFIED (by design; not a defect) |
| Off-machine backup beyond GitHub | None beyond the GitHub push and the VM bundles | PENDING |

**Note on the push history:** the GitHub branch previously held a single GitHub-generated "Initial commit" (`eaff4cb`, 207 bytes, almost certainly a README, created 2026-11-23 ~11:51 PKT). The owner replaced it with the full 21-commit history by force-push (`--force-with-lease`) from his PC. The replacement is complete and verified by the parent; no work was lost (the replaced commit contained no project code).

## 5. Secret exposure risks — VERIFIED (no live secret found)

Checks run on tracked files only (`git grep`, counts and file names — **no secret value was printed or recorded anywhere in this audit**):

| Check | Result | Status |
|---|---|---|
| `.env` / `web/.env.local` / `.env.local` ever committed? | `git log --all -- <those paths>` returns nothing — never committed | VERIFIED |
| Files matching env/secret/credential/key in the tracked tree | Only `.env.example` (placeholders) and `.secrets.baseline` (detect-secrets baseline) | VERIFIED |
| JWT-like strings (`eyJ…`, 20+ chars) | Exactly **1** match: `web/package-lock.json` line 5236. Inspected by machine (key path only): it is a **30-character base64 fragment inside an npm `integrity` hash** (preceding JSON keys: `version`, `resolved`, `integrity`) — far too short for a JWT and part of a package checksum, not a credential. False positive. | VERIFIED (benign) |
| `service_role` references (7 lines) | All are code/config references: Pydantic field `supabase_service_role_key`, `service_role_configured()` checks, `create_client(...)` call, and a health-endpoint test asserting the string never appears in responses. No value. | VERIFIED |
| `SUPABASE_SERVICE` references (13 lines) | Env-var names in code/docs, `SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here` placeholder in `.env.example`, and test dummies (`"test-service-role-key"`, `"SECRET-ROLE-VALUE-12345"`) in `conftest.py` / `test_security.py` / `benchmark_m7.py`. No real value. | VERIFIED |
| AWS keys / GitHub PATs / Slack tokens (`AKIA…`, `ghp_…`, `xox…`) | 0 matches | VERIFIED |
| `sk-…` API-key pattern | 0 matches | VERIFIED |
| `.env.example` content | Placeholders only (`your-anon-key-here`, `your-service-role-key-here`, `<redacted>` for `DATABASE_URL`/`GEMINI_API_KEY`); real Supabase project ref is named but no key value appears | VERIFIED |
| `web/.env.local` (real values) | Present, mode **0600**, 390 bytes; covered by `.gitignore` (`web/.env.local`, `web/.env*.local`); not tracked | VERIFIED |
| `.gitignore` coverage | `.env`, `web/.env.local`, `web/.env*.local`, `var/`, `*.db`, `.coverage`, `node_modules/`, `.next/`, caches, keystores (`*.keystore`, `*.jks`, `key.properties`) | VERIFIED |
| `render.yaml` secrets | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` are all `sync: false` — Dashboard secrets, never in the file or the repo | VERIFIED |
| Secret scanning wired in | `.secrets.baseline` (detect-secrets v1.5.0) present; CI runs a detect-secrets job (see §7) | VERIFIED |

**Residual risks (not findings of exposure):**

1. `web/.env.local` holds real values on the VM and in one backup file. Both are mode 0600 and gitignored. If the VM is ever shared or its disk exported, these two files must be treated as secrets. — Status: PENDING (owner awareness; no action required now).
2. The Supabase **service-role key is not available from the VM** (no copy stored here). That is good for security but means admin operations (e.g. deleting the unconfirmed M3 test user, admin-confirming users) can only be done by the owner in the Supabase Dashboard. — Status: PENDING (owner step, recorded in §7).

## 6. Missing files — VERIFIED (none missing)

Deployment-required files, all present:

| File | Size | Status |
|---|---|---|
| `render.yaml` (branch `officerpath-phase2-web`, plan `free`, Docker runtime, `healthCheckPath: /health`) | 2,928 bytes | VERIFIED |
| `Dockerfile` (multi-stage, `python:3.12-slim`, non-root, `HEALTHCHECK /health`) | 3,115 bytes | VERIFIED |
| `requirements.txt` | 1,547 bytes | VERIFIED |
| `requirements-dev.txt` | 75 bytes | VERIFIED |
| `web/package.json` | 774 bytes | VERIFIED |
| `web/package-lock.json` | 247,456 bytes | VERIFIED |
| `web/next.config.ts` | 2,697 bytes | VERIFIED |
| `supabase/migrations/015_documents_jobs.sql` + `_down.sql` | 7,084 bytes | VERIFIED |
| `supabase/migrations/016_pdf_documents_bucket.sql` + `_down.sql` | 3,656 bytes | VERIFIED |
| `supabase/migrations/017_documents_hash_partial_unique.sql` + `_down.sql` | 2,383 bytes | VERIFIED |
| `alembic/versions/0001`–`0009` (M1 engine tables → M9 notifications) | 9 files | VERIFIED |
| `.github/workflows/ci.yml` | present (see §7) | VERIFIED |
| `docs/phase2/migration-runbook.md`, `rollback-runbook.md`, `deployment-checklists.md`, `PHASE_2_COMPLETION_REPORT.md` | present | VERIFIED |
| `docs/deployment/01-repository-safety-audit.md` | this file | COMPLETED |

**Not missing, by design:** there is no `package-lock.json` at the repository root — the root is a Python project; the Node lockfile lives at `web/package-lock.json` (present). There is no committed `.env` — real values live only in `web/.env.local` (gitignored) and its backup.

**Destructive-operation scan of the three Supabase up-migrations:** `grep -c` for `DROP TABLE|DROP COLUMN|TRUNCATE|DELETE FROM` returns **0** in each of `015`, `016`, `017` (up files). Down files exist for rollback; their contents are reviewed in Workstream C.

**Largest tracked file:** 4,455,603 bytes (`app/tests/fixtures/golden/ppsc66/Pak_Study_1000__MCQs_for_ETEA.pdf`) — well under GitHub's 100 MB per-file limit.

## 7. Deployment blockers

These are **not** repository defects — the repository is ready. They are the remaining owner/environment gates before or during deployment:

| # | Blocker | Status | Owner / next workstream |
|---|---|---|---|
| B1 | Supabase migration **016** (bucket `pdf-documents`) not applied live | PENDING | Owner, Supabase Dashboard SQL Editor (Workstream C runbook) |
| B2 | Supabase migration **017** (partial unique index) not applied live | PENDING | Owner, Supabase Dashboard SQL Editor (Workstream C runbook) |
| B3 | Alembic 0001–0009 not applied to live Postgres | PENDING | Owner machine with live `DATABASE_URL` (Workstream C) |
| B4 | Supabase backup confirmation before migrations | PENDING | Owner, Dashboard → Database → Backups (Workstream C) |
| B5 | Render service not created / not connected to GitHub | PENDING | Owner, Render Dashboard (Workstream D) |
| B6 | Vercel project not created / not connected | PENDING | Owner, Vercel (Workstream E) |
| B7 | Canonical production domain unconfirmed (`https://officerpath.ai` is a placeholder) | PENDING | Owner decision (Workstream E) |
| B8 | Redirect URL allowlist not conclusively proven (localhost callback + production URL) | PENDING | Owner, Supabase Dashboard (Workstream C) |
| B9 | Unconfirmed M3 test user `officerpath.m3.test@gmail.com` still exists in live Auth | PENDING | Owner, Dashboard → Authentication → Users (delete) |
| B10 | Docker image never built (no Docker on the VM; Dockerfile comments record this as UNVERIFIED) — first CI Docker build after the push is the verification | PENDING | CI run after push (Workstream B) |
| B11 | GitHub CI never run (no push existed before today) — workflow exists (`.github/workflows/ci.yml`: web job Node 24 + tsc/lint/build; lint, pytest, mypy, pip-audit, detect-secrets, Alembic up/down, Docker build) but no run results exist yet | PENDING | First CI run on the pushed branch (Workstream B) |
| B12 | `npm audit` never run (VM registry returns 403 `policy_denied`) | PENDING | Owner machine (Workstream G) |
| B13 | Live phone acceptance (STOP CONDITION) — PPSC-66 / table photos / Paper 60 through the web upload on the owner's phone | BLOCKED | Owner device after deploy (Workstream F) — cannot be done by any agent |
| B14 | Gemini server key deferred by the owner ("baad ki bat") — Gemini advisory adapter stays disabled; no key provisioned, no Gemini API calls ever made | PENDING | Owner, later (not a deploy blocker) |

## 8. Recommended safe next actions

In order. No step here makes a production change; production-impacting steps require the owner's explicit approval at the time.

1. **Workstream B — GitHub + CI:** watch the first CI run on `officerpath-phase2-web` (push is already on GitHub); record real results, do not invent them. — PENDING
2. **Workstream C — Supabase:** owner confirms a recent backup exists, then applies 016 and 017 via the Dashboard SQL Editor exactly as `docs/phase2/migration-runbook.md` §1 prescribes, running its verification queries; then Alembic 0001–0009 on live Postgres and verification of `alembic_version = 0009`. — REQUIRES OWNER APPROVAL (production data)
3. **Workstream D — Render:** owner connects the repo in the Render Dashboard (Blueprint from `render.yaml`); set the four `sync: false` secrets in the Dashboard; verify `/health` returns 200 (not `degraded`). — REQUIRES OWNER APPROVAL
4. **Workstream E — Vercel:** owner creates the Vercel project from the repo, sets the four `NEXT_PUBLIC_*` variables (values from the owner, never invented), confirms the canonical domain decision. — REQUIRES OWNER APPROVAL
5. **Workstream F — Live acceptance:** after deploy, owner tests the three acceptance fixtures on his own Android phone; nothing is marked complete until that happens. — BLOCKED (owner device)
6. **Workstream G — Security + licensing:** run `npm audit` on the owner's machine; resolve the PyMuPDF AGPLv3 decision before any closed-source distribution. — PENDING
7. **Housekeeping (owner, any time):** delete the unconfirmed M3 test user in the Supabase Dashboard (B9); confirm the redirect URL allowlist (B8). — PENDING
8. **Do not do:** no force-push to `main` (nothing has ever been pushed to `main` from this repo — `origin/main` on GitHub points at the replaced initial commit and is not a deploy branch), no direct commits to `main`, no production migration without the backup check, no paid service, no Gemini key request.

## Appendix — evidence (commands run in this audit)

- `git status` → clean, branch `officerpath-phase2-web`
- `git branch -a` → `officerpath-phase1-engine`, `officerpath-phase2-web`
- `git log --oneline` (both branches), `git merge-base` → `69ca62d`, `git rev-list --count` → 10
- `git remote -v` → (empty)
- `git ls-files | wc -l` → 488; `web` 97; `app` 274
- `git ls-files | grep -i env/secret/credential` → `.env.example`, `.secrets.baseline` only
- `git log --all -- .env web/.env.local .env.local` → (empty)
- `git grep -c` secret patterns → see §5 table
- `ls -l web/.env.local` → 0600, 390 bytes; backup file identical size/mode
- `grep -c` destructive ops in 015/016/017 up-migrations → 0 each
- Fixture presence: `~/workspace/officerpath-ai/test-fixtures/ppsc66/` — `ppsc_paper_66.pdf` (5,911,945 bytes), `paper60-photo.jpg` (3,475,937 bytes), `table-computer-q67-81-resent-20261121.jpg` (1,076,655 bytes), `table-interjection-q230-257-resent-20261121.jpg` (998,156 bytes); repo copies in `app/tests/fixtures/ppsc66/` (`p-1.png`–`p-7.png`, both table photos, `PROVENANCE.md`); golden dataset `app/tests/fixtures/golden/dataset.json` — **38 entries** (v2)
- Largest tracked file 4,455,603 bytes
- `git bundle` files present in `~/workspace/` (sizes listed in §4)

**Audit conclusion:** the repository is in a safe, deployable state. Working tree clean, full history on the intended branch, no secrets committed, no deployment-required file missing, fixtures present, backup exists on GitHub and on the VM. All remaining blockers are owner/environment gates (Supabase migrations, Render/Vercel connection, CI first run, phone acceptance), not repository defects. Proceed to Workstream B.
