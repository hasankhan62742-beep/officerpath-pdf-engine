# OfficerPath AI — Phase 2: Web Application

**Branch:** `officerpath-phase2-web` (created 2026-11-22 from Phase 1 head `69ca62d`)
**Phase 1 head:** commit `69ca62d` — "M8: full suite, final benchmark, docs, deployment guide, Phase 1 completion report"
**Milestone:** M1 — Repository Audit and Web Architecture (audit + plan only; no application code)

## The one rule

**Phase 2 reuses the Phase 1 Python engine without rebuilding it.**
The FastAPI engine (`app/`) is the document-intelligence core: OCR, layout,
extraction, answer detection, matching, review, background jobs. Phase 2 adds
a Next.js web frontend and the student-facing features the engine does not
have (accounts, question bank organisation, test builder, exam interface,
results, admin foundation). It does not replace the engine, does not migrate
it to Node.js, and does not break any existing API contract.

## Documents in this directory

| Doc | Contents |
|---|---|
| [01-repository-findings.md](01-repository-findings.md) | What actually exists in the repo, verified against the code — live vs local-only, and every drift found. |
| [02-api-integration-map.md](02-api-integration-map.md) | Every existing endpoint the web app will use, plus the GAPs (endpoints Phase 2 must still build). |
| [03-database-extension-plan.md](03-database-extension-plan.md) | New Phase 2 entities mapped onto the existing M1 schema; what is reused, what is new, migration strategy. |
| [04-frontend-architecture.md](04-frontend-architecture.md) | Next.js App Router architecture, `web/` layout, design tokens, auth flow, routes, PWA readiness. |
| [05-security-architecture.md](05-security-architecture.md) | Supabase Auth + ownership model, roles, rate limits, secrets, and what the frontend must never trust. |
| [06-deployment-plan.md](06-deployment-plan.md) | Independent frontend/backend deployment, Render realities, env inventory, CORS, backup, rollback. |
| [07-milestone-execution-plan.md](07-milestone-execution-plan.md) | M2–M10 execution plan: scope, dependencies, acceptance criteria, explicit non-scope. |

## Evidence rule

Every claim in these docs cites the file it was verified against
(file:line where useful) or is labelled **UNVERIFIED**. Where the Phase 1
completion report and the code disagree, the **code wins** and the
disagreement is recorded in `01-repository-findings.md`.

## Status (2026-11-22, M1)

- Nothing is deployed. No push has ever happened (no git remote is
  configured). Migration 015 is written but **not applied live**. The
  Gemini server key is deferred by the owner. The Flutter "Server parse"
  toggle is prepared-only (3 uncommitted files, no `.git` in
  `~/workspace/officerpath-ai/`).
- Phase 1 is complete as a **local** milestone (pytest 492/0, ruff clean,
  mypy CI gate SUCCESS — parent-verified 2026-11-22 ~13:24 PKT). The Phase 1
  STOP CONDITION (live phone verification) is still unmet.
