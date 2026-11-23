# Workstream G — Security + Licensing Report

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream G subagent (read-only inspection; no file modified except this report; no code changed)
**Scope:** PyMuPDF AGPLv3 licensing, other-dependency licences, security review (auth, admin, exam-key handling, RLS/storage, secrets, CORS, headers, dependency audits, rate limiting, upload limits).

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Every file-level finding marked VERIFIED was checked by this workstream with the command shown or cited. Live facts (M3 confirm-email gate, pip-audit clean, CI never run) are cited from earlier workstreams as reported and were **not** re-run here, except `npm audit`, which was re-run in this workstream and failed exactly as before. Licence terms for PyMuPDF, pypdfium2 and pypdf were verified against the installed package metadata or the PyPI record on 2026-11-23; commercial-licence prices are **not** published by Artifex and none is claimed. **This report is research, not legal advice and not legal clearance.** A lawyer's view is needed before any closed-source commercial distribution.

**Related documents (built on, not duplicated):** `docs/adr/ADR-004-pdf-and-preprocessing.md`, `docs/deployment/01-repository-safety-audit.md`, `docs/deployment/02-github-ci-report.md`, `docs/deployment/03-supabase-migration-runbook.md`, `docs/deployment/04-render-backend-deployment.md`, `docs/deployment/05-vercel-frontend-deployment.md`, `docs/deployment/06-live-acceptance-report.md`, `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `docs/phase2/milestones/MILESTONE_9_REPORT.md`.

---

## 1. PyMuPDF AGPLv3 — the open question

### 1.1 Presence and usage — VERIFIED

PyMuPDF **1.26.3** is installed and pinned (`requirements.txt`: `PyMuPDF==1.26.3`). Installed metadata states the licence as **"Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"**. It is imported as `fitz` in 6 non-test files:

| File | What it uses PyMuPDF for |
|---|---|
| `app/pipeline/pdf/analysis.py` | `fitz.open`, `page.get_text("text")` + `get_text("dict")` (spans/fonts), `get_drawings()` count, page rect/rotation, `doc.is_encrypted`, `doc.metadata`, `doc.pdf_version` |
| `app/pipeline/pdf/renderer.py` | `fitz.open`, `page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))` — **page rendering to PNG for OCR** |
| `app/pipeline/ocr/digital.py` | `fitz.open`, `fitz_page.get_text("dict")` — digital text extraction with layout |
| `app/pipeline/extract/service.py` | `fitz.open` (page count / text-length estimation) |
| `app/pipeline/answers/inline_detector.py` | `fitz.open`, `page.get_text()` + `get_text("dict")`, `page.get_images(full=True)` + `fitz.Pixmap` — inline answer-mark detection |
| `app/pipeline/matching/service.py` | `fitz.open`, `page.get_text()` — total character count |

Two distinct roles: **(a) text extraction with layout** (`get_text("dict")` spans, words, fonts, image bboxes) and **(b) page rendering** (`get_pixmap` at 200 DPI, the input to Tesseract for scanned pages). Any replacement must cover **both** roles, or the OCR path breaks — rendering is not optional.

### 1.2 What AGPLv3 actually requires — research, not legal advice

AGPLv3 is GPLv3 plus Section 13 ("Remote Network Interaction"). The operative text:

> "if you modify the Program, your modified version must prominently offer all users interacting with it remotely through a computer network (if your version supports such interaction) an opportunity to receive the Corresponding Source of your version by providing access to the Corresponding Source from a network server at no charge..."

Two points that matter for this project, stated plainly:

1. **The Section 13 trigger is narrowly written** — it applies to a *modified* version of the Program offered over a network. Running an *unmodified* AGPL library as part of a larger service is a genuinely contested boundary: whether the whole combined service becomes a "modified version" / derivative work is the question lawyers argue about, not something this report settles.
2. **Artifex's own position is stricter than the narrow reading.** Its licensing page states that server-based use of its open-source software requires disclosing your own application's full source code under AGPL, and points SaaS/hosted products at the commercial licence. Artifex is the copyright holder — its interpretation is the one that would be enforced.

**Correction to ADR-004:** ADR-004 says the exposure "is limited today" because "the engine source must stay available to its users — which it already is (the repo is public)". That is imprecise in one respect: **there is no LICENSE file in this repo** (verified: `ls LICENSE*` → none). A public repo without a licence is "all rights reserved" by default — public visibility is **not** the same as an AGPL licence grant. To rely on the AGPL path honestly, the project needs an explicit AGPLv3 licence (a `LICENSE` file stating AGPLv3, plus a source offer visible to users of the service). Until that file exists, the "already compliant" claim is shaky even for the free beta.

### 1.3 What this means for the three stages

| Stage | Position |
|---|---|
| Free beta (20–30 students, no money, repo public) | Exposure is limited **if** the licence gap in §1.2 is closed (add the AGPLv3 `LICENSE` file + a source link in the app). Without the file, even the beta rests on an unlicensed public repo. |
| Phase 3 paid launch (closed-source commercial service) | **Blocked until the owner decides.** With PyMuPDF in the engine, a closed-source paid service conflicts with the AGPL unless (a) the whole service stays AGPL-licensed with source offered to users, (b) a commercial licence is bought, or (c) PyMuPDF is replaced. |
| Any distribution of the engine as a closed-source binary/APK bundle | Same as the paid launch — blocked until decided. |

No legal clearance is claimed anywhere in this report. Before closed-source commercial distribution, the owner needs a lawyer's view (or a commercial licence, or a replacement).

### 1.4 Alternatives — evaluated on their merits, from the actual usage

| Alternative | Licence (verified) | Covers text + layout? | Covers rendering? | Verdict |
|---|---|---|---|---|
| **pdfplumber** (already installed, used for ruled tables in M3) | MIT (classifier in installed metadata) | Yes — words/chars with positions; better tables than PyMuPDF | **No** | Cannot replace rendering. Keeps the table role only. |
| **pdfminer.six** (already installed, under pdfplumber) | MIT (installed metadata) | Yes — layout analysis, char-level detail | **No** | Text role only; slower than PyMuPDF on large PDFs. |
| **pypdf** (not installed) | BSD-3-Clause (PyPI record, current 7.1.1, verified 2026-11-23) | Partial — `extract_text()` only, no layout dict, no spans/fonts | **No** | Text role only, and the weakest layout fidelity of the three. Third-party benchmarks put it ~8–12x slower than PyMuPDF on plain extraction (not measured here). |
| **pypdfium2** (not installed) | BSD-3-Clause / Apache-2.0 (PyPI record, current 5.15.2, verified 2026-11-23) | Yes — `TextPage` with char-level rects | **Yes** — renders pages to bitmaps | **The only single-library candidate covering both roles.** Caveats: different API (no `get_text("dict")` spans/fonts, no `get_drawings()`, no `get_images()` equivalent — 6 call-site files need rewriting); bundles third-party PDFium binaries (supply-chain consideration); needs a benchmark on the acceptance fixtures before any switch. Candidate only — **not** evaluated in code. |
| **Poppler / pdf2image** | GPL (system library) | Via `pdftotext` | Via `pdftoppm` | Same copyleft family as AGPL for practical purposes, plus a system dependency in Docker. Not an escape from copyleft. |
| **Commercial PyMuPDF licence** | Artifex commercial | Full — no code change | Full — no code change | Artifex **does not publish prices** (quote-based, "crafted based on your individual use case"). Third-party write-ups mention five-figure annual ranges — **unverified, not claimed here**. Requires a sales conversation; no cost is asserted. |

### 1.5 Decision — REQUIRES OWNER APPROVAL

No silent replacement. No recommendation is imposed; the trade-offs are:

- **Option A — Keep PyMuPDF, close the licence gap:** add an AGPLv3 `LICENSE` file + a source offer link in the app, and accept that the service is AGPL-licensed (source stays public). Cost: $0. Consequence: the engine can never go closed-source while PyMuPDF remains.
- **Option B — Buy the commercial licence:** ask Artifex for a quote first, then decide with a real number. Cost: unknown until quoted. Consequence: no code change, closed-source launch allowed.
- **Option C — Replace with pypdfium2 (+ pdfplumber for tables):** a dedicated migration milestone — rewrite 6 call-site files, re-benchmark on PPSC-66 / table photo / Paper 60, re-run the full suite + M10 E2E. Cost: engineering time + re-verification. Consequence: closed-source launch allowed with no licence fee.
- **Option D — Defer the decision:** allowed **only** while the service stays free and the repo stays public. The Phase 3 paid launch is blocked until A, B, or C is chosen.

The cheapest honest path for the free beta is **A** (the LICENSE file costs nothing and closes the current gap). The only paths to a closed-source paid product without paying Artifex are **C** (engineering) or **B** (money). The decision is the owner's, before Phase 3 — not before the beta.

---

## 2. Other-dependency licence scan — VERIFIED

Licences read from the installed package metadata (backend) and `node_modules/*/package.json` (frontend). Transitive dependencies were not exhaustively audited; `pip-audit` covers vulnerabilities, not licences.

### 2.1 Backend (`requirements.txt`) — all permissive except PyMuPDF and psycopg

| Package | Version | Licence |
|---|---|---|
| PyMuPDF | 1.26.3 | **AGPLv3 dual** (see §1) |
| opencv-python-headless | 4.11.0.86 | Apache 2.0 |
| Pillow | 13.0.0 | MIT-CMU |
| numpy | 2.3.2 | BSD-3-Clause |
| pytesseract | 0.3.13 | Apache 2.0 |
| pdfplumber | 0.11.11 | MIT |
| pdfminer.six | 20260107 | MIT |
| paddleocr | 3.7.0 | Apache 2.0 |
| onnxruntime | 1.32.0 | MIT |
| fastapi | 0.165.0 | MIT |
| uvicorn | 0.34.0 | BSD-3-Clause |
| pydantic / pydantic-settings | 2.10.4 / 2.7.1 | MIT |
| supabase | 2.15.3 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| SQLAlchemy | 2.0.44 | MIT |
| alembic | 1.16.4 | MIT |
| psycopg | 3.2.10 | **LGPLv3** — see note below |
| python-multipart | 0.0.34 | Apache-2.0 |

**psycopg LGPLv3 note:** a weak copyleft (library) licence. Used unmodified, as a dynamically linked library, it does not require the application to be open-sourced under normal use — but it is a copyleft licence and is recorded here rather than hidden. No other copyleft licence was found in the backend.

### 2.2 Frontend (`web/package.json`) — all permissive

`next`, `react`, `react-dom`, `tailwindcss`, `@supabase/ssr`, `@supabase/supabase-js`, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `eslint-config-next` — **MIT**. `typescript`, `@playwright/test` — **Apache-2.0**. No copyleft in the frontend.

### 2.3 Dev dependencies — not shipped

`requirements-dev.txt` (pytest, pytest-cov, ruff, mypy, pip-audit) is **not** installed by the Dockerfile — it installs `requirements.txt` only. Dev-only licences do not reach the deployed image.

---

## 3. Security review

### 3.1 Authentication — VERIFIED

- Supabase Auth, email + password. **Confirm-email gate works** (M3 verified: login before confirming returns 400 "Email not confirmed"; `mailer_autoconfirm = false`) — cited as reported from M3, not re-run here.
- JWT verification is done **server-side** by asking Supabase Auth itself (`client.auth.get_user(token)` in `app/integrations/supabase_auth.py`). The token is **never decoded locally with a hardcoded secret, never logged, never stored**. Invalid/expired → 401; Auth unreachable / unconfigured → 503.
- No client request body is ever consulted for a role (see §3.2).

### 3.2 Admin access — VERIFIED

- Every admin route is behind `require_admin` (`app/api/v1/admin.py`: `/overview`, `/users`, `/documents`, `/jobs`, `/errors`, `/questions` — all six, verified in the file).
- The admin claim comes **only** from the verified JWT's `app_metadata.is_admin` (`app/security/dependencies.py:54-55`, `is True` check). It is set by the owner via the Supabase Dashboard / service-role script, never self-assigned, never settable through any API.
- Non-admins get **404** (not 403 — the route's existence is not confirmed to an attacker). Denied attempts are logged with the user id only, never a token.
- A second middleware (`app/main.py`, `role_field_anomaly_log`) logs any `is_admin` / `role` / `plan` field appearing in a JSON request body (method + path only) — the field is ignored by the handlers.
- **Admin users list has no email field — known limitation, not a bug.** `AdminUserItem` (`app/schemas/admin.py:19`) carries `user_id`, `full_name`, `phone`, `preferred_exam`, `education_level`, counts and timestamps — no email. The engine DB stores no student email (`app/services/admin.py:59-61`); `/me` returns the email from the caller's own JWT. An admin therefore cannot contact a student by email from the admin panel.

### 3.3 M9 exam-leak fix — VERIFIED for the session endpoint

- `SessionSnapshotItem` (`app/schemas/exam.py:40`) deliberately carries **no `correct_index` and no `answer_source`** — only `is_unknown`.
- `_session_snapshot_dict` (`app/services/exam.py:147-158`) builds exactly that shape: `"is_unknown": row.correct_index < 0`, key withheld.
- `GET /tests/{test_id}/session` (`app/api/v1/tests.py:216`) returns `ExamSessionResponse` built from it.
- The exam-take UI uses **only** `getExamSession` (`web/components/dashboard/exam-client.tsx:125`); no UI page calls the detail endpoint during the exam (verified by grep — no caller of `getTest` in `web/app`).
- The M9 regression test asserts the session response carries no key (M9 report §5, cited as reported).

### 3.4 FINDING — Residual answer-key exposure via `GET /tests/{test_id}` — FAILED

The M9 fix closed the session endpoint, but the **detail endpoint still returns the key**:

- `GET /tests/{test_id}` (`app/api/v1/tests.py:169`) → `TestDetailResponse`, whose `snapshots` are built by `_snapshot_dict` (`app/services/tests.py:581-592`) — which includes **`"correct_index": row.correct_index`** and **`"answer_source": row.answer_source`**.
- `get_test` (`app/services/tests.py:816-831`) checks **ownership only** (`_own_session` — the caller must own the test). It has **no status guard**: a student can call it while their own test is `in_progress` and read every correct answer from the response (curl / browser devtools), bypassing the M9 session fix entirely.
- Cross-user exposure is **blocked** (`_own_session` 404s for another user's test) — the hole is strictly self-exposure mid-test, i.e. an **exam-integrity (cheating) hole**, not a cross-user data breach.
- The normal UI does not call this endpoint during the exam (§3.3) — exploiting it requires a deliberate direct API call. That lowers the likelihood, not the severity: any motivated student can do it in seconds.
- `create_test` also returns the detail shape (line 794) — that is legitimate: the test is in status `created` (pre-start) and the creator is reviewing their own bank-derived test.

**Status: FAILED** — the control "no answer key available while a test is in progress" fails on this route.

**Recommended fix (NOT implemented in this audit workstream):** in `get_test`, withhold `correct_index`/`answer_source` (return the `SessionSnapshotItem` shape) while the session status is `in_progress`, or return 409 while in progress; add a regression test asserting the detail endpoint returns no key mid-test. This is a small, well-scoped fix for an owner-approved follow-up milestone — record it as a pre-beta fix, since students could cheat in the free beta too. (Post-submit review showing the key is intended and is unaffected.)

### 3.5 RLS and storage policies — VERIFIED (files read)

From `supabase/migrations/015_documents_jobs.sql` and `016_pdf_documents_bucket.sql`:

| Object | Policy | Result |
|---|---|---|
| `public.documents` | RLS enabled; users SELECT + INSERT their own rows only (`auth.uid() = user_id`); **no client UPDATE/DELETE policy** — documents are immutable for clients; admins SELECT all via `public.is_admin()` | Matches the intended access |
| `public.jobs` | RLS enabled; users SELECT + INSERT their own; the **only** client UPDATE is cancel (`status = 'cancelled'`, own rows only); no client DELETE; admins SELECT all via `public.is_admin()` | Matches the intended access |
| `pdf-documents` bucket (016, live) | Private, 100 MB cap; users upload under their own uid folder, view their own; admins view all; **no UPDATE/DELETE policy** — cleanup is done by the backend (service role) | Matches the intended access |

The engine writes job status/results with the **service-role key**, which bypasses RLS — client policies are intentionally narrow so no client can forge a job outcome.

**Caveat (carried from Workstream C):** `public.is_admin()` is **not defined in any migration file in this repo** — its existence live is inferred (015's admin policies exist live and 016's admin policy was created successfully, and Postgres validates function existence at `CREATE POLICY` time). If it ever disappears, admin policies fail at creation, not silently.

### 3.6 Secrets handling — VERIFIED

- Working tree is clean except the two **untracked 018 migration files** (by design — the parent's fix, awaiting owner approval). No other untracked file.
- `web/.env.local` holds real values, mode **0600**, gitignored (verified: `git check-ignore` returns the path). Its backup (`~/workspace/user/officerpath-web-env-backup.txt`) is also 0600. Neither was ever committed (`git log --all --` on those paths is empty — Workstream A, cited as reported).
- **No service-role key in the frontend:** grep for `SERVICE_ROLE`/`service_role` across `web/app`, `web/lib`, `web/components`, `web/*.ts` returns nothing. The frontend receives only the four `NEXT_PUBLIC_*` variables (Workstream E).
- `render.yaml`: all four secrets (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`) are `sync: false` — Dashboard secrets, never in the file or the repo.
- `.dockerignore` excludes `.env`, `.git`, `.venv`; the Dockerfile runs as non-root user `appuser` and installs only `requirements.txt` (no dev deps, no secrets).

### 3.7 CORS — open gap (carried from Workstream D) — PENDING

- Code default is `http://localhost:3000` (`app/config.py:57`); `CORSMiddleware` is configured with an explicit origin list and `allow_credentials=True` — never `"*"` (correct pattern).
- **`CORS_ALLOWED_ORIGINS` is missing from `render.yaml`** (verified by grep — no match). Until it is set in the Render Dashboard, the production frontend would be blocked from calling the API. The value depends on the **domain decision** (Workstream E) — the production origin must be added once the domain is chosen. Status: PENDING, blocked on the owner domain decision.

### 3.8 Security headers — VERIFIED

- **Backend** (`app/main.py`, `security_headers` middleware, on every response): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`; `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` on everything except `/docs`, `/redoc`, `/openapi.json` (Swagger UI needs its own scripts there).
- **Frontend** (`web/next.config.ts`, `SECURITY_HEADERS` on `/:path*`): same four headers; no CSP (a strict CSP breaks Next.js' own inline runtime scripts — recorded, not hidden); `X-Robots-Tag: noindex, nofollow` on every private route (`/dashboard`, `/admin`, `/login`, `/register`, `/forgot-password`, `/auth/*`, including the bare-path entries M9 found by measuring).

### 3.9 Dependency audits

| Check | Result | Status |
|---|---|---|
| `pip-audit` (backend) | **No known vulnerabilities found** (Workstream B re-ran it) | VERIFIED (reported by Workstream B, not re-run here) |
| `npm audit` (frontend) | **BLOCKED on this VM** — re-run in this workstream: `403 Forbidden - POST https://registry.npmjs.org/-/npm/v1/security/audits/quick - policy_denied` (`zz_managed_internal_spaces_package_registries`). The audit endpoint is blocked by VM policy, not by the project. | BLOCKED (VM policy) |
| CI `docker-build` job | First CI run is the proof the image builds (no Docker on the VM) | PENDING (first CI run) |

**Owner step:** run `npm audit` on the owner's machine:
```bash
cd web && npm audit
```
and record the result. No npm-audit result is claimed anywhere in this report. (The CI workflow has no `npm audit` step — noted, not treated as a gap to fix here.)

### 3.10 Rate limiting, input validation, upload limits — VERIFIED (with gaps)

**Rate limiting — present on the expensive endpoints, absent elsewhere:**

- In-memory sliding-window limiter (`app/security/rate_limit.py`, `RateLimiter.check` → 429 `rate_limited`). Applied per-user on: async-parse register (**10/min**), job retry (**5/min**), review endpoints, batch routes, `/me`. Limits from `app/config.py` (`rate_limit_register_per_minute = 10`, `rate_limit_retry_per_minute = 5`, `rate_limit_window_seconds = 60`).
- **Not** applied to 8 routers: `admin.py`, `collections.py`, `dashboard.py`, `documents.py`, `notifications.py`, `questions.py`, `results.py`, `tests.py` (including exam answer-save and submit). Reads are cheap, so the exposure is mainly exam save/submit and admin list endpoints — low severity on a single free instance, but an unthrottled submit loop is possible.
- **Documented limitation** (in the file itself): limiter state lives in this process only. With a single Render free instance (the Stage-1 deploy shape) that is acceptable; more than one replica needs a distributed limiter (e.g. Redis).

**Input validation — honest, server-side:**

- Uploads are validated by **magic bytes, not by filename or client MIME type** (`app/api/v1/async_jobs.py:102-110`): `%PDF` → pdf, PNG/JPEG signatures → image; anything else → 422 `invalid_file`. The same check exists in `review.py`.
- **File size cap: 100 MB** (`max_file_size_bytes = 100 * 1024 * 1024` in `app/config.py:26`, enforced before the file is read into processing) — matches the Supabase bucket cap (100 MB).
- **Batch cap: 20 files** (`BATCH_MAX_FILES = 20`, `app/api/v1/routes.py:51`).
- List endpoints are capped at 100 rows (`MAX_LIST_LIMIT = 100` in documents/questions/results/collections).
- Pydantic schemas validate request bodies; test names ≤ 200 chars, descriptions ≤ 2000 chars (enforced in `update_test`).
- Encrypted PDFs are handled in the pipeline (`doc.is_encrypted` checks in analysis/extract) — they fail honestly rather than crashing.

### 3.11 What was NOT checked

No live penetration test was run; no live Supabase Auth configuration re-check (M3 cited); no staging environment exists; the first CI run (including the `docker-build` job and detect-secrets) has not happened yet. Nothing in this report claims a live security test.

---

## 4. Owner decisions required

In order. Nothing here authorises an agent to change code, apply a migration, or spend money.

1. **PyMuPDF path (Options A–D, §1.5)** — before the Phase 3 paid launch; the LICENSE-file gap (Option A's first step) can be closed now, for free, regardless of the eventual choice. — REQUIRES OWNER APPROVAL
2. **Fix the residual exam-key exposure (§3.4)** — withhold the key in `GET /tests/{test_id}` while the test is `in_progress`, plus a regression test. Recommend before the free beta (students could cheat in the beta too). — REQUIRES OWNER APPROVAL (a code change)
3. **Run `npm audit` on the owner's machine** (`cd web && npm audit`) and record the result. — PENDING (owner step)
4. **Decide the canonical domain** — unblocks Render `CORS_ALLOWED_ORIGINS` (§3.7) and the Supabase redirect allowlist. — REQUIRES OWNER APPROVAL
5. **Delete the unconfirmed M3 test user** `officerpath.m3.test@gmail.com` and confirm the redirect allowlist (carried from Workstreams A/C/F). — PENDING (owner step)
6. **Check the first CI run** (Actions tab, commit `461c9a2`) — all six jobs green before the PR to `main` is merged (carried from Workstream B). — PENDING (owner step)
7. **Do not do:** no silent PyMuPDF replacement, no closed-source commercial distribution with PyMuPDF in the engine until §1.5 is decided, no invented audit results, no live change without the owner's say-so.

---

## Appendix — evidence (commands and files read in this workstream)

- `git log --oneline -3` → head `04318c3` (Workstream F); `git status --short` → only the two untracked 018 files; branch `officerpath-phase2-web`.
- `ls -l web/.env.local` → mode 0600, 390 bytes; `git check-ignore web/.env.local` → ignored.
- `grep -rn "import fitz\|fitz\." app/ --include="*.py"` → 6 files (§1.1); method inventory: `get_text("text"/"dict")`, `get_pixmap`, `get_drawings`, `get_images`, `fitz.Pixmap`, `fitz.Matrix`, `page.blocks/lines/items`, `doc.is_encrypted/metadata/pdf_version`.
- `ls LICENSE*` → **none** (no licence file in the repo).
- `.venv/bin/pip show PyMuPDF` → 1.26.3, "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License".
- Licence scan via `importlib.metadata` (backend) and `node_modules/*/package.json` (frontend) → §2 tables. `pdfplumber` MIT classifier confirmed in its installed METADATA; `pypdf` BSD-3-Clause and `pypdfium2` BSD-3-Clause/Apache-2.0 confirmed from their PyPI records (2026-11-23; pypdf 7.1.1, pypdfium2 5.15.2).
- AGPL §13 text: GNU AGPLv3 §13 (quoted in §1.2); Artifex's licensing position: server-based use requires source disclosure or a commercial licence; Artifex publishes no prices (quote-based).
- `app/schemas/exam.py` — `SessionSnapshotItem` (no `correct_index`/`answer_source`); `app/services/exam.py:147-158` — `_session_snapshot_dict` (only `is_unknown`); `app/api/v1/tests.py:216` — session endpoint returns `ExamSessionResponse`.
- `app/services/tests.py:581-592` — `_snapshot_dict` includes `correct_index` + `answer_source`; `app/services/tests.py:816-831` — `get_test` has **no status guard** (ownership only, `_own_session`); `app/api/v1/tests.py:169` — detail endpoint returns `TestDetailResponse`.
- `web/components/dashboard/exam-client.tsx:125` — exam UI calls `getExamSession` only; grep for `getTest(` in `web/app` → no callers during the exam.
- `app/security/dependencies.py` — `require_admin` (`app_metadata.is_admin is True`, non-admin 404); `app/api/v1/admin.py` — all six routes behind `require_admin`; `app/schemas/admin.py:19` — `AdminUserItem` has no email field.
- `app/integrations/supabase_auth.py` — `verify_jwt` via `client.auth.get_user(token)`; token never decoded locally/logged/stored.
- `app/main.py` — `security_headers` middleware + `role_field_anomaly_log` middleware + `CORSMiddleware` (explicit origin list, credentials allowed, never `"*"`) ; `app/config.py:26,33-35,57` — 100 MB cap, rate limits, CORS default `http://localhost:3000`.
- `grep -i cors render.yaml` → **no match** (CORS key missing — Workstream D's finding re-confirmed).
- `web/next.config.ts` — frontend security headers + `X-Robots-Tag: noindex` on private routes.
- `app/security/rate_limit.py` — in-memory sliding-window limiter (single-process limitation documented in the file); usages in `async_jobs.py`, `review.py`, `routes.py`, `me.py`; 8 routers without it (§3.10).
- `app/api/v1/async_jobs.py:95-110` — 100 MB cap + magic-byte file-type check; `routes.py:51` — batch max 20.
- `supabase/migrations/015_documents_jobs.sql` (RLS + 7 policies) and `016_pdf_documents_bucket.sql` (bucket + 3 policies) — read in full; `public.is_admin()` has no definition in the repo (grep, no hits).
- `npm audit` in `web/` → `403 Forbidden ... policy_denied` (`zz_managed_internal_spaces_package_registries`) — re-confirmed in this workstream.
- `Dockerfile` — installs `requirements.txt` only, non-root `appuser`, `HEALTHCHECK /health`; `.dockerignore` excludes `.env`, `.git`, `.venv`.

**Workstream G conclusion:** the PyMuPDF AGPL question is now fully mapped — the licence, the exact usage, the alternatives, and the four decision options, with the honest caveat that there is currently **no LICENSE file** in the repo, so even the "public repo" mitigation is incomplete until a licence file is added. No other copyleft licence was found (psycopg LGPLv3 noted). The security review verifies the auth/admin/RLS/secrets/headers controls as implemented, confirms the M9 session fix, and finds **one real residual hole: `GET /tests/{test_id}` returns the answer key to the test owner mid-test** — a small, well-scoped fix that should land before the beta. `npm audit` remains blocked on the VM (403, re-confirmed) and is an owner-machine step. Nothing in this report claims a live check or legal clearance.
