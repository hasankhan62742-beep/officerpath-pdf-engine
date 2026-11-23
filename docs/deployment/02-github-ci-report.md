# Workstream B — GitHub + CI Report

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream B subagent (local inspection + local test runs; no file modified except this report)
**Scope:** Repository access, branch relationships, PR strategy, CI workflow inspection, local re-run of the CI gates (pytest, ruff, mypy, web typecheck/lint/build, pip-audit, detect-secrets, Alembic up/down), lockfiles and dependency findings, CI verification status.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Every number in §5–§6 comes from a check run in this workstream, with the command shown or cited. Where an M10 figure is quoted for comparison it is cited as *reported* (from `docs/phase2/PHASE_2_COMPLETION_REPORT.md`), not re-verified. The GitHub head `461c9a2` is parent-reported (verified by the parent via the GitHub API) and was **not** independently re-checked here — this workstream has no GitHub access. No CI run result is claimed anywhere in this report: no CI run has ever happened, and none is invented.

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` (Workstream A), `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `docs/phase2/deployment-checklists.md`, `.github/workflows/ci.yml`.

---

## 1. Repository access — VERIFIED (local) / PENDING (GitHub-side)

| Check | Result | Status |
|---|---|---|
| Current branch | `officerpath-phase2-web` | VERIFIED |
| Working tree | Clean (`git status --short` empty) at head `4510a90` | VERIFIED |
| Local branches | `officerpath-phase1-engine`, `officerpath-phase2-web` only | VERIFIED |
| Git remote configured locally | None (`git remote -v` empty) — the VM repo cannot push/fetch on its own; pushes go through the owner's PC | VERIFIED (by design) |
| GitHub head | `461c9a2` (Phase 2 M10), parent-verified via GitHub API (`list_commits` head `461c9a2`, then `7abb28f`, `094b6b6`) | COMPLETED (parent-reported) |
| Local branch vs GitHub | Local head `4510a90` (this workstream's predecessor, Workstream A report) is **1 commit ahead** of the GitHub head `461c9a2`; the Workstream A commit has not been pushed | PENDING (push is an owner-PC step) |
| GitHub Actions runs | None exist yet — the repository was empty until the owner's push on 2026-11-23 ~12:34 PKT, so no workflow has ever run | PENDING (first run) |

## 2. Branch relationships — VERIFIED

| Check | Result |
|---|---|
| Merge-base `officerpath-phase1-engine` ↔ `officerpath-phase2-web` | `69ca62d` (the Phase 1 head) |
| Commits Phase 1 head → Phase 2 head | **11** — the ten Phase 2 milestones (M1–M10) plus the Workstream A report commit `4510a90` |
| Total commits on `officerpath-phase2-web` | **22** (21 project commits + 1 audit report commit) |
| Phase 1 head | `69ca62d8ff8e14ed785c792348f4b7963ecbddb3` — "M8: full suite, final benchmark, docs, deployment guide, Phase 1 completion report" |
| Phase 2 head (local) | `4510a900760a76761aafdc53810f98b7340cf16b` — "Deploy audit: repository safety report (Workstream A)" |
| Phase 2 deploy baseline | `461c9a2` (M10) — the commit on GitHub; the Workstream A commit adds only the audit report, no code |

The Phase 2 branch is a strict superset of Phase 1: no Phase 1 work is missing from the deploy branch (Workstream A §1, re-confirmed here by merge-base).

## 3. PR strategy — PENDING (plan prepared, no PR created)

**Target:** merge `officerpath-phase2-web` → `main` on GitHub, once, after the deploy gates pass. No PR was created in this workstream; creating one is an owner decision (it needs a GitHub-side action and, per the master prompt, no production change without approval — merging to `main` is the production-branch event).

**Current state of `main`:** on GitHub, `main` points at `eaff4cb` ("Initial commit", 3 objects, 207 bytes — almost certainly a GitHub-generated README, created 2026-11-23 ~11:51 PKT). `main` has never been a deploy branch and contains no project code. The PR would therefore bring the entire project history onto `main` in one merge.

**Proposed PR:**
- **Title:** `Phase 1 + Phase 2: OfficerPath AI engine and web application`
- **Base:** `main` — **Head:** `officerpath-phase2-web`
- **Contents:** 22 commits (Phase 1 M0–M8 engine, Phase 2 M1–M10 web app, Workstream A audit report). Full history, no squashing — the milestone commits are the audit trail.
- **Body (outline):** link to `docs/phase2/PHASE_2_COMPLETION_REPORT.md` and `docs/deployment/01-repository-safety-audit.md`; state the gates (pytest/ruff/mypy/web build, OpenAPI 49 paths, E2E 37/37 browser + 17/17 API as *reported* in M10); list the known deployment blockers (Supabase 016/017 unapplied, Alembic live pending, Render/Vercel not connected, phone acceptance outstanding).
- **Required checks before merge (all must be green on the PR):** the CI workflow's six jobs (§4) on the first GitHub run — in particular `test` (pytest), `lint`, `typecheck`, `web` (tsc/lint/build), `security` (pip-audit + detect-secrets), `docker-build`. Do **not** merge while any job is red or while CI has never run.
- **Merge method:** merge commit (preserve the milestone history). Do not squash, do not rebase onto `main` (nothing to rebase onto — `main` is a single README commit; a rebase would rewrite all 22 commit hashes for no benefit).
- **After merge:** `main` becomes the production branch; Render and Vercel should then build from `main` (their configs currently point at `officerpath-phase2-web` — see Workstreams D/E for the branch switch). Do **not** delete `officerpath-phase2-web` immediately after merging; keep it until the first successful deploy from `main` is verified.
- **What NOT to do:** no direct commits to `main`, no force-push to `main`, no PR from the Phase 1 branch (it is a strict subset of Phase 2 and is superseded as a deploy source).

## 4. CI workflow inspection — VERIFIED (file read in full)

File: `.github/workflows/ci.yml` (name: `CI`).

**Triggers:** `push` and `pull_request` to branches `main`, `officerpath-phase1-engine`, `officerpath-phase2-web`. It does **not** deploy, does **not** touch live Supabase, does **not** push any image.

**Jobs (6):**

| Job | Runs on | Steps (what it proves) |
|---|---|---|
| `web` | `ubuntu-latest`, `working-directory: web` | `actions/checkout@v4`; `setup-node@v4` Node **24** with npm cache (`web/package-lock.json`); `npm ci`; `npx tsc --noEmit` (typecheck); `npm run lint` (ESLint); `npm run build` (production build) |
| `lint` | `ubuntu-latest` | `setup-python@v5` Python **3.12**; `pip install -r requirements-dev.txt`; `ruff check .`; `ruff format --check .` |
| `typecheck` | `ubuntu-latest` | Python 3.12; `pip install -r requirements.txt -r requirements-dev.txt`; `mypy app/db app/pipeline app/storage` (the M1-packages gate — the same gate re-run locally in §5) |
| `test` | `ubuntu-latest` | Python 3.12; `apt-get install tesseract-ocr tesseract-ocr-urd tesseract-ocr-ara` (the Tesseract tests run the real binary — eng+urd; PaddleOCR is NOT run in unit tests, so no model download happens in CI); `pip install -r requirements.txt -r requirements-dev.txt`; `pytest -q`; then **Alembic up/down on SQLite** (`DATABASE_URL=sqlite:////tmp/officerpath-ci-test.db`: create `documents`/`jobs` tables, `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`, `alembic current`) |
| `security` | `ubuntu-latest` | `checkout` with `fetch-depth: 0`; Python 3.12; `pip install -r requirements-dev.txt` + `detect-secrets==1.5.0`; `pip-audit -r requirements.txt -r requirements-dev.txt`; `detect-secrets scan --baseline .secrets.baseline` |
| `docker-build` | `ubuntu-latest`, `needs: [lint, typecheck, test, security]` | `docker build -t officerpath-pdf-engine:ci .` (only runs after the four code jobs pass; `web` is **not** a dependency of this job) |

**Notes:**
- The workflow has no `npm audit` step (npm audit is a known VM limitation, §6, and is an owner-machine step — it is not a CI gap to fix here).
- The `test` job installs Tesseract **without** `tesseract-ocr-eng` explicitly — `tesseract-ocr` pulls `tesseract-ocr-eng` as a dependency, so eng is present; urd and ara are installed explicitly. This matches the language set the engine tests need.
- The Alembic step uses a fresh SQLite file in `/tmp`; it does not touch any real database.
- **CI status: PENDING — first run.** No workflow run has ever existed for this repository. The owner's push of `461c9a2` (2026-11-23 ~12:34 PKT) should have triggered a run on branch `officerpath-phase2-web` if GitHub Actions is enabled for the repository — that cannot be verified from this VM (no GitHub access). **Owner check:** GitHub → repository → Actions tab → the run for commit `461c9a2`; all six jobs must be green before the PR in §3 is merged. If no run appears, check that Actions is enabled (Settings → Actions → General) and that the workflow file is on the pushed branch (it is — `.github/workflows/ci.yml` is tracked at `461c9a2`).

## 5. Local re-run of the CI gates — VERIFIED (commands run in this workstream)

Environment for all runs below: repo at `/home/hatch/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`, head `4510a90`. Python **3.12.3** (`.venv`), Node **v24.22.1**, npm **10.9.4**. `web/.env.local` present, mode **0600** (values never printed). Tesseract **5.3.4** with languages `ara`, `eng`, `osd`, `urd` at the start of this workstream.

| Gate (CI job) | Command run | Result | Status |
|---|---|---|---|
| Ruff lint (`lint`) | `.venv/bin/ruff check .` | **All checks passed!** | VERIFIED |
| Ruff format (`lint`) | `.venv/bin/ruff format --check .` | **229 files already formatted** | VERIFIED |
| Mypy gate (`typecheck`) | `.venv/bin/mypy app/db app/pipeline app/storage` | **Success: no issues found in 68 source files** | VERIFIED |
| TypeScript typecheck (`web`) | `cd web && npx tsc --noEmit` | Exit **0**, no errors | VERIFIED |
| ESLint (`web`) | `cd web && npm run lint` | Passed, no errors | VERIFIED |
| Production build (`web`) | `cd web && npm run build` | Exit **0**; 34 `page.tsx` routes (filesystem count, matches M10's reported 34 pages); `.next` build output present | VERIFIED |
| Dependency audit (`security`) | `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` | **No known vulnerabilities found** (pip-audit's own output text) | VERIFIED |
| Secret scan (`security`) | `.venv/bin/detect-secrets scan --baseline .secrets.baseline` | True exit code **0** (verified unpiped). The scan records 3 hashed entries — `.env.example:22` (placeholder comment), `app/tests/test_observability.py:49` and `app/tests/test_ocr_gemini.py:55` (test-dummy values) — none is a live secret (consistent with Workstream A §5). Note: the scan rewrites the baseline file in place; the repo copy was restored to HEAD with `git checkout` after the run, so the working tree is clean. The committed baseline is stale (empty `results`, generated 2026-11-21); refreshing it is a housekeeping item, not a gate failure. | VERIFIED |
| Alembic up/down (`test`) | Fresh SQLite `/tmp/officerpath-ci-test.db`, CI's exact sequence: `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` → `alembic current` | **0009_m9_notifications (head)** after the final upgrade; all revisions 0001–0009 applied and downgraded cleanly | VERIFIED |
| Full pytest (`test`) | `.venv/bin/python -m pytest -q` | **613 passed, 0 failed, 39 warnings, in 307.66s (0:05:07)** — exit 0; run after the tesseract restore (see incident note below) | VERIFIED |

**Incident — runtime restart wiped tesseract and killed the first pytest run (environment, not code):** the first full pytest run (started ~12:43 PKT) was interrupted by a runtime restart ~5 minutes in; its recorded log is 0 bytes (the `tail -30` pipe buffered everything, so no partial count survives) and the run has no confirmed result. The same restart wiped system tesseract again (the 6th wipe in this project's history: M7, Phase 1 M8 ×2, M8-verification, M9-verification, M10, now). `which tesseract` returned nothing after the restart. The cell's own os-intent replay restored it (tesseract 5.3.4, langs `ara eng osd urd`, back after ~12.5 min; the `.deb` files were already in the local apt cache). The suite was then re-run once, in the background, with no parallel heavy work: **613 passed / 0 failed in 307.66s** — exactly reproducing M10's parent-verified 613/0. The 39 warnings are pre-existing DeprecationWarnings (SWIG `swigvarlink`, Alembic `path_separator`); none is a failure.

## 6. Lockfiles, dependencies, and audit limitations

| Check | Result | Status |
|---|---|---|
| `web/package-lock.json` | Present, 247,456 bytes, 5,602 lines; `npm ci` in CI uses it | VERIFIED |
| `requirements.txt` | Present, 1,547 bytes, all versions pinned (`==`) | VERIFIED |
| `requirements-dev.txt` | Present; `pytest==9.0.3`, `ruff==0.14.4`, `mypy==1.18.2`, `pip-audit==2.9.0` | VERIFIED |
| No root `package-lock.json` | By design — the root is a Python project; the Node lockfile lives at `web/package-lock.json` | VERIFIED |
| Frontend versions (installed) | Next **16.4.6**, React **19.3.0**, Tailwind CSS **4.3.3**, TypeScript **^5** (installed 5.9.x per lockfile) | VERIFIED |
| Backend pins (selected) | FastAPI 0.165.0, SQLAlchemy 2.0.44, Alembic 1.16.4, Pydantic 2.10.4, supabase 2.15.3, Pillow 13.0.0, numpy 2.3.2, paddleocr 3.7.0, onnxruntime 1.32.0 | VERIFIED |
| PyMuPDF | **1.26.3**, installed and pinned; AGPLv3 dual licence (ADR-004) — **noted here only; licensing resolution is Workstream G's topic** | VERIFIED (presence only) |
| `pip-audit` | **No known vulnerabilities found** (see §5) | VERIFIED |
| `npm audit` | **FAILED as expected on this VM** — `npm audit` returns `403 Forbidden - POST https://registry.npmjs.org/-/npm/v1/security/audits/quick - policy_denied` (`zz_managed_internal_spaces_package_registries`). The audit endpoint is blocked by VM policy, not by the project. Recorded as an **owner step on the owner's machine** (`cd web && npm audit`); no npm-audit result is claimed. | BLOCKED (VM policy) |
| Outdated-dependency check | Not run systematically in this workstream — no tool on the VM can check npm outdatedness against the registry (same 403 policy), and no outdated-version list is invented. Pinned versions are recorded above for the owner's review. | PENDING (owner machine, alongside `npm audit`) |

## 7. CI verification status — PENDING (first run)

| Item | Status | What to watch / who |
|---|---|---|
| First GitHub Actions run on `officerpath-phase2-web` (triggered by the 12:34 PKT push of `461c9a2`) | PENDING | Owner: GitHub → Actions tab. All six jobs must be green. If no run exists, check Actions is enabled (Settings → Actions → General). |
| Local re-run of all CI gates | VERIFIED — all gates pass, including pytest 613/0 (see §5) | This workstream |
| `npm audit` | BLOCKED (VM 403) | Owner machine: `cd web && npm audit` |
| PR `officerpath-phase2-web` → `main` | PENDING | Owner decision after CI is green (§3). No PR created here. |
| Docker image build | PENDING (CI) | First CI `docker-build` job is the verification (no Docker on the VM). Locally unbuildable. |
| Pushing the Workstream A + B report commits | PENDING | Owner PC (local branch is 2 commits ahead of GitHub after this report is committed). |

## 8. Recommended safe next actions

1. **Pytest re-run: DONE — 613 passed / 0 failed in 307.66s.** This report is complete; commit it. — COMPLETED
2. **Owner: check the first CI run** (Actions tab, commit `461c9a2`); all six jobs green before any merge. — REQUIRES OWNER APPROVAL (to act on results)
3. **Owner: run `npm audit`** on his machine (`cd web && npm audit`) and record the result; this is the only dependency check the VM cannot do. — PENDING (owner step)
4. **Owner: push the two audit-report commits** (Workstream A `4510a90` + this report) from his PC when convenient — they are docs-only and do not change the deploy baseline `461c9a2`. — PENDING
5. **Owner decision: create the PR** in §3 only after CI is green; merge with a merge commit; do not delete `officerpath-phase2-web` until the first deploy from `main` is verified. — REQUIRES OWNER APPROVAL
6. **Do not do:** no direct commits to `main`, no force-push to `main`, no invented CI results, no deploy from an unmerged branch without the owner's say-so.

## Appendix — evidence (commands run in this workstream)

- `git status` → clean, branch `officerpath-phase2-web`, head `4510a90`
- `git merge-base officerpath-phase1-engine officerpath-phase2-web` → `69ca62d`
- `git rev-list --count officerpath-phase1-engine..officerpath-phase2-web` → 11
- `git rev-list --count officerpath-phase2-web` → 22
- `git remote -v` → (empty)
- `which tesseract` → `/usr/bin/tesseract`, 5.3.4, langs `ara eng osd urd` (before the restart; wiped by it — see §5)
- `.venv/bin/python --version` → 3.12.3; `node --version` → v24.22.1; `npm --version` → 10.9.4
- `.venv/bin/ruff check .` → "All checks passed!"; `.venv/bin/ruff format --check .` → "229 files already formatted"
- `.venv/bin/mypy app/db app/pipeline app/storage` → "Success: no issues found in 68 source files"
- `cd web && npx tsc --noEmit` → exit 0; `npm run lint` → passed; `npm run build` → exit 0
- `find web/app -name 'page.tsx' | wc -l` → 34
- `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` → "No known vulnerabilities found"
- `.venv/bin/detect-secrets scan --baseline .secrets.baseline` → true exit code 0 (verified unpiped against a /tmp copy of the committed baseline). Records 3 hashed entries (`.env.example:22` placeholder; `test_observability.py:49`, `test_ocr_gemini.py:55` test dummies). Side effect found and fixed: the scan rewrites the baseline file in place — the repo copy was restored with `git checkout -- .secrets.baseline` after the run; working tree clean.
- Alembic on fresh SQLite: `upgrade head` → `downgrade base` → `upgrade head` → `alembic current` → `0009_m9_notifications (head)`
- `npm audit` (in `web/`) → `403 Forbidden ... policy_denied` (`zz_managed_internal_spaces_package_registries`)
- `ls -l web/.env.local` → mode 0600 (values never printed)
- First pytest run (background session `proc_8945a6a9c0bc`): interrupted by a runtime restart after ~5 min; recorded log 0 bytes; no confirmed result — superseded by the re-run below
- Pytest re-run (background session `proc_a61ab3a0c7ba`, after the tesseract restore): **613 passed, 39 warnings in 307.66s (0:05:07)**, exit 0; `time` real 5m18.679s
- Tesseract restore: cell os-intent replay (`apt-get update` PID 794, ~12.5 min) restored tesseract 5.3.4 with langs `ara eng osd urd` from the local apt cache

**Workstream B conclusion:** repository access and branch relationships are verified; the PR plan is prepared but no PR exists; the CI workflow is inspected in full and is sound (six jobs, correct versions, no deploy step); locally, **every CI gate passes on re-run** — pytest **613/0** in 307.66s, ruff clean (229 files), mypy gate clean (68 files), tsc clean, ESLint clean, production build passes (34 pages), pip-audit clean (0 vulnerabilities), detect-secrets clean, Alembic up/down/up lands on `0009` (head). The runtime restart that wiped tesseract mid-workstream was an environment incident, not a code failure, and the re-run after the restore reproduces M10's 613/0 exactly. CI on GitHub has never run; its first run remains PENDING and must be green before the §3 PR is merged. The only dependency check no agent can do from this VM is `npm audit` (registry 403) — an owner-machine step.
