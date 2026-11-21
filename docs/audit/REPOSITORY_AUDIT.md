# OfficerPath AI — Phase 1 Milestone 0: Repository Audit

- **Date:** 2026-11-21 (PKT, Asia/Karachi)
- **Auditor:** Milestone 0 subagent (read-only audit; no feature code, no migrations applied, no deploys, no paid services)
- **Assignment:** Ultimate Master Prompt (27 sections, M0–M8, received 16:54 PKT) + v2 Master Prompt (22 sections, M1–M9, received 16:55 PKT) — v2 is a second wording of the same assignment, folded into this single audit (see §1.3 for the milestone-numbering reconciliation)
- **Repositories audited:** `~/workspace/officerpath-pdf-engine/` (Python engine) and `~/workspace/officerpath-ai/` (Flutter app + Supabase)
- **Evidence labels used throughout:** **VERIFIED** (executed and observed in this audit) · **ASSUMED** (reasonable, untested) · **UNVERIFIED** (code/file exists, not run or not checked live) · **UNKNOWN** (needs research/access). No accuracy, benchmark, or test number in this document is asserted unless it was observed in this session or is explicitly cited from a named earlier report.

## 0. Verdict in one paragraph

**VERIFIED:** The engine is a small, clean, well-tested **skeleton** — FastAPI + Pydantic v2 + Supabase client, 22/22 pytest passing, boots and answers `/health` honestly — but it contains **zero** OCR, layout, extraction, answer-detection, matching, or scoring code, and no pipeline, queue, SQLAlchemy/Alembic, or plugin interfaces from the master prompt §5. The Flutter app (v2.0.5) is the whole product today: ~11,000 lines of on-device parsing/OCR services, a 5,734-line Dart parser, and Supabase for auth/money only. The PPSC-66 phone failure is an **input-quality failure at the on-device OCR/geometry stage** (ML Kit), not a parser-logic failure — the same parser scores 100/100 on clean Gemini OCR text on the VM (cited, not re-run). The correct Phase 1 shape is therefore: keep the app untouched, build the server engine to receive page images/PDFs, and prove it on the three acceptance files. **Gate 0 is met as an audit, with two decisions owed by the owner** (see §9): approve the Render-free Stage 1 hosting route (ADR-001, PROPOSED) and approve the OCR approach (ADR-002, PROPOSED). No feature code was written in this milestone, per the prompt.

## 1. Scope, sources, and the two master prompts

### 1.1 What was read

**VERIFIED** (files read in this session):

| Source | What was taken from it |
|---|---|
| `officerpath-pdf-engine/` — all non-venv files (see §2.1 inventory) | `app/` source, `requirements*.txt`, `Dockerfile`, `.github/workflows/ci.yml`, `.env.example`, `.gitignore`, `supabase/migrations/015_documents_jobs.sql`, `README.md`, `TEST_REPORT.md`, `CHANGELOG.md` |
| `officerpath-ai/PHASE1_AUDIT_2026-11-20.md` (read in full, §§0–5 + plan start) | Stack inventory, Supabase schema 001–014, workflow map, OCR tiers, PPSC-66 failure analysis — **reused, not re-derived**; figures from it are cited as "2026-11-20 audit" and were not re-measured here |
| `officerpath-ai/PHASE1_DEPLOY_RESEARCH_2026-11-20.md` (§§0–2 read) | Cloud Run free-tier mechanics, VM tooling gaps |
| `officerpath-ai/PPSC66_BASELINE_2026-11-20.md` (key lines grepped) | Gemini 100/100 baseline, recitation-filter blocks on pp. 3/5 |
| `officerpath-ai/pubspec.yaml` | App version 2.0.5+5500, dependency list |
| `MASTER_PROMPT_PHASE1_ULTIMATE_2026-11-21.md` + `MASTER_PROMPT_PHASE1_V2_2026-11-21.md` | The two assignment wordings (summaries, not retypes) |

**UNVERIFIED in this session:** `MASTER_DIRECTIVE_2026-11-20.md`, `TEST_REPORT.md`/`CHANGELOG.md` of the Flutter app, and the tail (§§6–8) of the 2026-11-20 audit were not re-read line by line; their conclusions are cited only where the sections read here confirm them. Live Supabase state (tables, RLS, buckets, Edge Functions) was **not** re-checked — the 2026-11-20 audit verified it live then; this audit is file-based plus local execution only.

### 1.2 GitHub repo state — "do not assume the repository is empty" (v2 §2)

- **VERIFIED:** Neither local directory is a git repository. `git status` in both `~/workspace/officerpath-pdf-engine` and `~/workspace/officerpath-ai` fails with `fatal: not a git repository`. There is no `.git/` directory in either tree.
- **UNVERIFIED (cannot check from this VM in this session):** the actual GitHub state. Per the durable record, `hasankhan62742-beep/officerpath-pdf-engine` exists, is public, and was empty at creation; local engine code has not been pushed. The Flutter repo `hasankhan62742-beep/officerpath-ai` is recorded at main HEAD `5e820936` (2026-11-20 audit, not re-verified here). **No git init, no push, no commit was performed in this audit** — that needs the owner's decision (see §9).
- Consequence: there is **no branch `officerpath-phase1-engine`** yet (both prompts require it), no CI running anywhere (the engine CI workflow exists only as a file), and no version control at all over the code audited here. Creating the repo link + branch is the first M1 action, owner-approved.

### 1.3 Milestone-numbering reconciliation (Ultimate vs v2) — ONE numbering going forward

**Decision (this audit): use the Ultimate numbering M0–M8, with v2 M9 folded into M8.** Rationale: the Ultimate prompt is the one the owner sent first and the one whose §24 report format this audit follows; v2 adds no milestone that M8 does not already contain.

| Ultimate (M0–M8) | v2 (M1–M9) | Mapping |
|---|---|---|
| M0 Repository audit, branch, baseline, architecture plan | M1 Audit + architecture | Same work. This document is the deliverable. |
| M1 Project structure, config, DB schema, migrations, ingestion, validation, storage | M2 Project setup / M3 Ingestion (v2 split) | v2 M2+M3 = Ultimate M1 |
| M2 PDF analysis, page classification, rendering, adaptive preprocessing | M4 PDF/preprocessing | Same |
| M3 OCR abstraction, engines, digital extractor, layout analysis | M5 OCR + layout | Same |
| M4 MCQ and option extraction | M6 Extraction | Same |
| M5 Answer detection (key, inline, style, visual, handwriting) | M7 Answer detection | Same |
| M6 Matching, validation, confidence scoring, reports, review APIs | M8 Matching/scoring/review | Same |
| M7 Background jobs, security hardening, observability, performance | (v2 folds into M8/M9) | v2 has no separate M7-equivalent; its job/queue content sits in its M8 |
| M8 Full test suite, benchmarks, docs, deployment guide, completion report | M9 Testing/benchmarking/docs/deployment | Same; v2 M9 = Ultimate M8 |

All later documents must use **M0–M8** and cite this mapping when quoting v2. Nothing in v2 changes scope: its §17 admin/review APIs are already Ultimate §16 (review/correction APIs + audit trail); its §11 optional-AI interface is Ultimate §15; its per-milestone rhythm ("explain → implement → test → fix → document → limitations → preserve stability") is adopted as the working rhythm for M1–M8 (§8).

## 2. Stack inventory

### 2.1 Engine repo — `officerpath-pdf-engine/` (VERIFIED by file listing, 21 Nov 2026)

```
officerpath-pdf-engine/
├── app/
│   ├── main.py                    104 lines — FastAPI app, request-id middleware, error handlers
│   ├── config.py                   49 lines — Pydantic Settings (env-only config)
│   ├── api/health.py               70 lines — GET /health, GET /version
│   ├── api/v1/routes.py           ~90 lines — POST /documents/register, GET /jobs/{id}, POST /jobs/{id}/retry
│   ├── core/errors.py              35 lines — ApiError + error envelope
│   ├── database/supabase_client.py 46 lines — anon + service-role clients (lazy, None when unconfigured)
│   ├── database/repositories.py   104 lines — DocumentRepository, JobRepository over supabase-py
│   ├── integrations/supabase_auth.py 49 lines — JWT verify via auth.get_user
│   ├── integrations/supabase_storage.py 33 lines — storage helper (stub-level; see §4)
│   ├── schemas/documents.py        98 lines — Pydantic v2 request/response models
│   ├── security/dependencies.py    36 lines — auth dependency
│   ├── security/rate_limit.py      38 lines — in-memory sliding-window limiter
│   ├── services/jobs.py           154 lines — register/status/retry business rules
│   ├── utils/logging.py            57 lines — structured JSON logging
│   ├── workers/processor.py        37 lines — process_job raises NotImplementedError; claim_next_job returns None
│   └── tests/ (conftest + 4 test files, 146+33+110+122+51 lines)
├── supabase/migrations/015_documents_jobs.sql  155 lines — documents + jobs + pdf-documents bucket (NOT applied)
├── requirements.txt               fastapi==0.115.6, uvicorn[standard]==0.34.0, pydantic==2.10.4,
│                                  pydantic-settings==2.7.1, supabase==2.15.3, httpx==0.28.1
├── requirements-dev.txt           pytest==8.3.4, httpx==0.28.1 (httpx duplicated — see §7, D3)
├── Dockerfile                     python:3.12-slim, multi-stage, non-root, HEALTHCHECK /health
├── .github/workflows/ci.yml       pytest + docker build on push/PR to main (never run — no repo)
├── pytest.ini, .env.example, .gitignore, .dockerignore
├── README.md, TEST_REPORT.md, CHANGELOG.md, MASTER_PROMPT_*_2026-11-21.md (2 prompt summaries)
└── .venv/ (76 MB, Python 3.12.3, deps installed — see §6.1)
```

**Total application code: ~1,100 lines** (excluding tests, venv, docs). There is **no** `app/pipeline/`, no `app/ai/`, no `app/db/` (SQLAlchemy/Alembic), no queue/worker runtime, no OCR/PDF dependency, no `pyproject.toml`, no `ruff.toml`, no `.pre-commit-config.yaml`, no mypy/ruff config of any kind.

### 2.2 Flutter app — `officerpath-ai/` (VERIFIED: file listing + pubspec; code details cited from 2026-11-20 audit)

- **Version VERIFIED:** `2.0.5+5500` in `pubspec.yaml` (Dart SDK `>=3.7.0 <4.0.0`, Flutter `>=3.35.0`).
- **Tests VERIFIED (count only):** 93 `*_test.dart` files under `test/` (100 files total). Pass counts are **cited, not re-run**: v2.0.4 reported 882 passed / 5 skipped / 0 failed; v2.0.5 reported 915 passed / 5 skipped / 0 failed (per memory; `flutter` is not installed on this VM — see §6.2).
- **Parsing/OCR services (line counts VERIFIED by `wc`):**

| File | Lines | Role |
|---|---|---|
| `lib/services/mcq_parser.dart` | 5,734 | MCQ parser (the engine's logic to port, not copy blindly) |
| `lib/services/pdf_text_extractor.dart` | 1,954 | Hand-rolled PDF text-layer extractor |
| `lib/services/answer_key.dart` | 1,535 | Key parsing + application + paper-identity gate |
| `lib/services/pdf_import_service.dart` | 924 | Upload → classify → OCR tiers → parse orchestration |
| `lib/services/urdu_ocr.dart` | 618 | ML Kit column-split + table reconstruction + OCR routing |
| `lib/services/gemini_client.dart` | 213 | Gemini Developer API client (user key, secure storage) |
| `lib/services/image_preprocess.dart` | 52 | Phone-photo preprocessing |

- **Key dependencies (VERIFIED in pubspec):** `supabase_flutter ^2.9.0`, `google_mlkit_text_recognition 0.16.0` (Latin only), `tesseract_ocr ^0.6.0` (eng+urd), `pdfx 2.11.0`, `pdf 3.12.0`, `file_picker ^8.0.0`, `sqflite ^2.4.0`, `firebase_core ^4.0.0` + `firebase_messaging ^16.0.0`, `google_sign_in ^7.0.0`, `flutter_secure_storage ^10.3.4`.
- **Supabase (file-based, cited from 2026-11-20 audit):** project `officerpath-ai`, ref `gliebuyyjguxrwdfuakz`, Postgres 17, Free plan, Singapore (`ap-southeast-1`); migrations 001–014 in-tree; 5 Edge Functions (`redeem-code`, `issue-code`, `delete-account`, `send-notification`, `payment-alert`); 1 private bucket (`payment-proofs`, receipts only). **No server-side PDF/OCR/parsing exists today.**
- **Other subsystems (cited):** admin panel in `admin/` (static web app, `officerpath-admin.pages.dev`); in-app updater via GitHub Releases; Current Affairs RSS; manual Easypaisa/JazzCash payments (no payment SDK).

### 2.3 Architecture diagram (as-is, VERIFIED structure)

```mermaid
flowchart TB
    subgraph PHONE["Flutter app v2.0.5 (the whole product today)"]
        UI[Upload / Test / History screens]
        IMP[pdf_import_service: classify pages, OCR tiers]
        OCR[ML Kit Latin → Tesseract eng+urd → Gemini vision (user key)]
        PAR[mcq_parser + answer_key: 7,000+ lines Dart]
        DB[(sqflite officerpath.db — sources/questions/attempts)]
        UI --> IMP --> OCR --> PAR --> DB
    end
    subgraph SUPA["Supabase Free (auth + money + sync only)"]
        AUTH[Auth email/Google]
        PG[(Postgres 17: profiles, payments, activation_codes, test_results, waitlist)]
        EF[Edge Functions x5]
        ST[Storage: payment-proofs bucket only]
    end
    subgraph ENG["Python engine (skeleton, local only)"]
        API[FastAPI: /health, /version, /api/v1/documents/register, /jobs]
        REP[Repositories over supabase-py]
        WK[workers/processor.py — NotImplementedError]
        API --> REP
        API -.-> WK
    end
    PHONE -->|test_results insert, profile reads| SUPA
    ENG -.->|would use, NOT connected live| SUPA
    PHONE -.->|no link yet — Flutter change is M1/M6 work| ENG
```

The dotted lines are the point of Phase 1: the engine is not connected to anything live, and the phone does not call it.

## 3. What is reusable vs what must be replaced

### 3.1 Reusable (keep, build on)

| Asset | Why it is reusable | Evidence |
|---|---|---|
| Engine skeleton: FastAPI app, Pydantic v2 schemas, error envelope, request-id middleware, structured JSON logging, health/version | Clean, tested, honest failure modes (503 when unconfigured/unreachable, never crashes) | VERIFIED: 22/22 tests; live boot §6.1 |
| `services/jobs.py` rules: ownership (own folder only), idempotency (key + same-path replay), 404-for-others, retry only from failed/cancelled | Correct security posture; matches prompt's idempotency + auth requirements | VERIFIED: read + covered by 9 register + 8 job tests |
| Migration 015 (documents + jobs + `pdf-documents` bucket, RLS) | Additive-only, narrow client policies, service-role writes, immutable uploads | VERIFIED: read in full; NOT applied live |
| `mcq_parser.dart` + `answer_key.dart` (~7,300 lines) as a **specification** | Encodes years of hard-won rules: category separation (digits-only in number slots, letters-only in option markers), sequence validation, paper-identity gate, answer precedence, unmatched-never-dropped | VERIFIED counts; behaviour cited from 2026-11-20 audit + PPSC66 baseline |
| `urdu_ocr.dart` geometry ideas (column split, table reconstruction) | The only column/table geometry in the system; the server layout module (M3) must reproduce and improve it with real boxes from all engines | Cited from 2026-11-20 audit §4.2 |
| Golden fixtures in `test-fixtures/ppsc66/` | Page images (p-1..p-7, crops), Gemini OCR text per page, Tesseract OCR text per page, table photos + Gemini text, Paper 60 OCR text — a ready-made M3/M4 benchmark seed | VERIFIED: directory listing (see §3.3) |
| CI workflow shape (pytest + docker build, no deploy) | Right gates; needs a repo to run in | VERIFIED: file read |
| Dockerfile (multi-stage, slim, non-root, healthcheck) | Sound shape; comments reference Cloud Run (stale — see §7 D6) but the image itself is platform-agnostic | VERIFIED: read |

### 3.2 Must be replaced / must be built (not present, or wrong layer)

| Item | Why | Prompt section |
|---|---|---|
| On-device OCR as the **primary** route (ML Kit Latin-first) | Proven failure on PPSC-66 phone test: 1/100, stems jumbled, option markers in wrong columns (see §5). ML Kit has no Urdu script, no style info, and its geometry helpers only run on ML Kit boxes | §8, §11 |
| `workers/processor.py` stub | `process_job` raises `NotImplementedError`; `claim_next_job` returns `None`. No queue, no worker runtime, no retries, no progress | §17 |
| supabase-py repositories as the **only** persistence layer | Works for register/jobs, but the prompt requires SQLAlchemy 2.x + Alembic for the full §14 schema (questions, options, evidence, reports, audit). Keep supabase-py for Auth verification; add SQLAlchemy for engine-owned tables, or justify keeping PostgREST-only with an ADR | §5, §14 |
| In-memory rate limiter | Correctly documented as single-process only; breaks at >1 replica | §16, §17 |
| `health.py` Supabase check (`table("documents").select…`) | Returns 503 `degraded` until migration 015 is applied live — correct behaviour, but it means "healthy" is unachievable until M1 applies 015 | §19 |
| Dockerfile/README Cloud Run deploy docs | GCP billing is PAUSED (3–4 cards rejected); Cloud Run requires a billing account even inside the free tier. Docs must be rewritten for Render Stage 1 (ADR-001) | §22, ADR-001 |
| Flutter upload flow (server route) | No server-parse option exists in the app; adding it is M1/M6 work, additive only, behind a toggle — the on-device path must keep working | §16 |

### 3.3 Golden fixtures available now (VERIFIED listing)

`~/workspace/officerpath-ai/test-fixtures/ppsc66/` contains: page renders `p-1.png` … `p-7.png` plus crops (`p-3-a/b/L/R/top/bot/q1/q2`, `p-3-bL1/L2a/L2b`), table photos `table-computer-q67-81.jpg`, `table-interjection-q230-257.jpg`, Gemini OCR text per page (`ocr-p1.txt` … `ocr-p7.txt`, `ocr-table-*.txt`, `paper60_gemini_ocr.txt`, `table_photo_gemini_ocr.txt`), Tesseract OCR text per page (`ocr-tess-p1.txt` … `ocr-tess-p7.txt`, `ocr-tess-table-*.txt`), `gemini_vision_ocr.py`, and `sample_mcq_bank.docx`. **This is the M3/M4 benchmark seed — do not regenerate it; version it as the golden set in M3.** Missing and needed in M3: ground-truth annotations (question/option/answer JSON per fixture) — none exist yet (UNKNOWN whether any annotation file exists elsewhere; none was found in the fixture dir).

## 4. Integration points the new engine will use

| # | Integration point | Current state | Engine's use in Phase 1 |
|---|---|---|---|
| I1 | Supabase Auth (JWT) | Live; engine verifies via `auth.get_user` (never decodes locally) | All `/api/v1` routes already require it (VERIFIED in code + tests). Unchanged. |
| I2 | `documents` + `jobs` tables (migration 015) | Written, **not applied live** (UNVERIFIED live). File-reviewed only. | M1: apply 015 (owner go-ahead) + extend with §14 tables via Alembic. Health check depends on `documents` existing. |
| I3 | Storage bucket `pdf-documents` (private, 100 MB cap, PDF/TXT/DOCX/JPG/PNG) | Defined in 015, not created live. MIME list lacks WebP/TIFF (prompt wants them) — M1 fix. | Upload target: phone uploads file → registers → engine downloads page images/PDF from here. |
| I4 | Flutter upload flow (`upload_screen.dart` → `pdf_import_service.dart`) | On-device only; no server call exists. | M1/M6: add additive "Server parse" option (toggle, default off until proven). App sends file bytes or storage path + idempotency key; polls `GET /jobs/{id}`; saves returned questions into sqflite exactly like a local parse. |
| I5 | Parser rules (Dart) | Proven on clean text (100/100); proven recovery of isolated digit/marker corruption on VM probes. | M4/M5: port as the reference implementation — same precedence (answer line > key > tick > bold > star > AI), same paper-identity gate, same 7 document statuses, same "unmatched, never discarded" reporting. |
| I6 | Gemini Developer API (`gemini-3.5-flash-lite`, vision OCR) | Client-side today, user's own key in secure storage. Server key: **deferred** by owner ("baad ki bat"). | M3: optional `AIAssistProvider`, disabled by default, suggestions only, never a verified answer (ADR-002). No server key is provisioned in Phase 1 without explicit approval. |
| I7 | Supabase Free limits | 500 MB DB, Edge Function invocations; project pauses after 7 days inactivity (keep-alive exists in-app) | Engine must not assume the DB is always warm; health must report honestly; Render keep-alive ping is a Stage-1 decision (ADR-001). |
| I8 | Admin/review (v2 §17) | Admin panel exists for payments/codes only; no document review UI. | M6: engine exposes review/correction/verification/reprocess APIs + full audit trail; admin UI is a later (post-Phase-1 or M6-stretch) surface, not a Phase 1 deliverable. |

## 5. PPSC-66 failure mode (why the server engine is the fix)

Cited from the 2026-11-20 audit + PPSC66 baseline (not re-measured in this session):

- **The file:** 7-page CamScanner scan, 5.9 MB, no text layer; 100 MCQs, two-column, (A)–(D) 2×2; answers ONLY in trailing key (`ANSWER KEY: Model Paper 66`, p6–p7, incl. two Urdu-script answers Q83/Q84); Paper 67 starts mid-p7.
- **VM, Gemini vision text → parser: 100/100, key 100/100 matched** (baseline, after heading fix). **Phone v2.0.4, ML Kit → parser: 1/100** (key found: 39 entries, 0 matched; 146 blocks skipped). Computer table photo on same re-test: 4 questions, 2 answered, stems jumbled, option markers in wrong columns.
- **Root cause (VERIFIED by VM probes cited in the audit):** synthetic digit-noise + column-interleave applied to the same clean Gemini text collapses the same parser 100 → 8 — same parser, same PDF, only OCR text degraded. Digit misreads (1→I, 0→O, 5→S, 8→B) kill question numbers and option markers; interleaved columns destroy reading order. v2.0.4 category-separation recovery lifts synthetic models (digit-noise 85→98, option-markers 23→100) but the combined/interleave model stalls at 52 and the phone's real ML Kit text was never captured — the phone read is worse than the synthetic models.
- **Design consequence (the single most important audit finding):** the engine must receive **page images (or the PDF, rendered server-side) — never the phone's already-degraded ML Kit text**. Any design that accepts phone OCR text as input repeats the failure. Gemini vision on the server is the proven-quality route (100/100 on this file); its blockers are the deferred server key and the recitation filter (blocked on p3/p5 in the VM baseline — a server route needs the same mitigation plan: page crops + `[?]` marking, already in the app's prompt).
- **Tesseract ceiling (cited):** real Tesseract 5.3.4 text on PPSC-66 parses 14–20/100 — a lower bound, not a primary route. PaddleOCR PP-OCRv5 Arabic-script model officially lists Urdu (Baidu claims 81.27% on a 2,676-image Arabic-script set) but Nastaliq quality is **UNPROVEN** — must be benchmarked on the fixtures before any claim (ADR-002).

## 6. Baseline results — actually run in this audit (21 Nov 2026)

### 6.1 Engine (VERIFIED — executed this session)

| Check | Command | Observed result |
|---|---|---|
| Python version | `python3 --version` | **Python 3.12.3** |
| Installed deps | `.venv/bin/python -m pip list` (filtered) | fastapi 0.115.6, uvicorn 0.34.0, pydantic 2.10.4, pydantic-settings 2.7.1, supabase 2.15.3, httpx 0.28.1, pytest 8.3.4 — all match `requirements*.txt`. **No** PyMuPDF, OpenCV, Pillow, NumPy, PaddleOCR, Tesseract, SQLAlchemy, Alembic, Celery/Redis installed or listed. |
| Test suite | `.venv/bin/python -m pytest -q` | **22 passed, 0 failed in 0.22s** (2 warnings: Starlette `BlockingPortal` deprecation; `gotrue` package deprecated in favour of `supabase_auth`). Reproduces the 20 Nov result exactly. |
| Boot + `/health` | `uvicorn app.main:app --port 8123` (no Supabase env) + `curl /health` | **HTTP 200**, body `{"status":"degraded","service":"officerpath-pdf-engine","version":"0.1.0","environment":"development","checks":{"config":"ok","supabase":"not_configured"}}` |
| OpenAPI docs | `curl /docs` | **HTTP 200** (FastAPI auto-docs served) |
| Docker build | — | **NOT RUN** — Docker is not installed on this VM (see §6.3). Dockerfile validated by reading only. |
| Live Supabase / migration 015 | — | **NOT RUN** — not applied, no live calls made in this audit (owner go-ahead required). |

### 6.2 Flutter app (NOT RUN — toolchain absent)

- `flutter` / `dart`: **command not found** on this VM. `flutter analyze` and `flutter test` were **not run**; the 915-passed v2.0.5 figure is cited from memory/report, not verified here.
- **VERIFIED by file inspection instead:** `pubspec.yaml` version `2.0.5+5500`; 93 `*_test.dart` files; service line counts (§2.2). No Flutter source was modified in this audit.

### 6.3 VM tooling (VERIFIED)

| Tool | Result |
|---|---|
| Python 3.12.3, pip3 | Present |
| Docker, gcloud, supabase CLI, ruff, mypy | **Not installed** (`which` finds none) — Docker image build, `gcloud run deploy`, lint/typecheck all unavailable locally; CI must do them |
| CPU / RAM | 4 vCPU, ~8 GB RAM (VM); disk 150 GB, 56 GB free |
| Git | Present as a binary, but **no repo** in either working tree (§1.2) |

## 7. Known defects and gaps (numbered for the plan)

| # | Defect / gap | Severity | Evidence |
|---|---|---|---|
| D1 | **No OCR, parsing, layout, extraction, or answer code at all.** `process_job` raises `NotImplementedError`; `claim_next_job` returns `None`. | Critical — the product | VERIFIED: read `workers/processor.py` |
| D2 | **No plugin interfaces** (`OCREngine`, `LayoutAnalyzer`, `QuestionDetector`, etc.), no pipeline state machine (prompt §5.3 states UPLOADED→…→COMPLETED; `jobs.status` has only 6 values and no per-page/stage history), **no ADRs** before this audit | Critical — architecture | VERIFIED: no such modules exist; `jobs` CHECK constraint in 015 lists `queued, uploading, processing, done, failed, cancelled` only |
| D3 | **No lint/typecheck/dependency-audit tooling.** No `pyproject.toml`, ruff, mypy, pre-commit, pip-audit; CI runs pytest + docker build only. `httpx` duplicated across `requirements.txt` and `requirements-dev.txt`. | Medium | VERIFIED: file listing + CI read |
| D4 | **No SQLAlchemy/Alembic.** Persistence is supabase-py only; the prompt's §14 schema (questions, options, evidence, reports, corrections, audit) has no models or migrations. | High | VERIFIED |
| D5 | **No queue.** No Celery/RQ/Postgres-queue, no retries/backoff, no dead-letter, no progress reporting, no cancellation beyond the client-side `cancelled` status (which the engine never acts on — no worker polls it). | High | VERIFIED |
| D6 | **Stale Cloud Run deploy docs.** `README.md` "Deploy (Cloud Run)" + `Dockerfile` comments assume Cloud Run; GCP billing is PAUSED and Cloud Run needs a billing account. Must be rewritten for Render Stage 1. | Medium | VERIFIED: grep found Cloud Run refs in `Dockerfile:6`, `README.md:77–127` |
| D7 | **Migration 015 gaps vs the prompt:** `file_type` CHECK omits `webp`/`tiff` (prompt §1 inputs); no `DOWN`/reversible migration; no Alembic; no stage/page tables; `page_count` cap 100 mirrors the app but is untested server-side. | Medium | VERIFIED: read 015 |
| D8 | **`/health` can never report healthy until 015 is applied** (it selects from `documents`). Correct honest behaviour, but M1 must sequence apply-then-verify. | Low | VERIFIED: read `health.py` |
| D9 | **No structured per-document correlation IDs in logs** beyond the per-request UUID; no metrics, no error taxonomy, no debug bundle/overlay tool (prompt §19–20 absent). | Medium | VERIFIED: read `utils/logging.py`, `main.py` |
| D10 | **No secret scanning in CI; `.gitignore` has no `*.keystore`/`*.jks`/`key.properties` entries** (engine repo; the Flutter repo's `.gitignore` does cover them). Low risk today (no secrets in the engine repo — §8), but the gap matters once a repo exists. | Low | VERIFIED |
| D11 | **Flutter phone path still fails on the acceptance files** (PPSC-66 1/100 on v2.0.4; v2.0.5 phone proof still pending). This is the problem Phase 1 exists to solve, not a defect of this audit — but no Phase 1 milestone may claim "done" until the phone proves it on the three files. | Critical — acceptance | Cited from 2026-11-20 audit + memory; v2.0.5 phone test pending |

## 8. Security findings

**No secret values are reproduced anywhere in this document.** Findings are names/presence only.

1. **Engine repo — clean (VERIFIED).** Grep for key/token/secret patterns across the repo (excluding `.venv`, `__pycache__`): matches are only env-var *names* (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) in `config.py` / `supabase_client.py` / comments, placeholders (`your-*-key-here`) in `.env.example`, and a test asserting forbidden strings are absent from responses. **No `.env` file exists** in the engine repo. No `sbp_`, `eyJ…`, `sk-`, `AIza` values found.
2. **Flutter repo — one live publishable key in the working tree (VERIFIED, value NOT reproduced).** `admin/config.js` (line 16) contains a real Supabase **anon/publishable JWT** for the project, alongside the project URL. The anon key is publishable by design (it ships in every client build) and RLS is the real enforcement — but: (a) the 2026-11-20 audit described `config.js` as "local only, gitignored", yet the file is present in the working tree and the `.gitignore` lines read here do not list `admin/config.js`; (b) whether it is tracked on GitHub **cannot be verified here** (no git repo locally, no GitHub access in this session). **Action before any push:** verify tracked-vs-ignored status; if tracked, rotate the anon key and switch the admin panel to `config.example.js` + deploy-time injection. The service-role key is correctly absent (the file's own comments forbid it).
3. **Keystore (UNVERIFIED content, no values observed).** `KEYSTORE_SETUP_2026-11-20.md` mentions "password" 15 times but contains no `password = <value>` pattern; per the doc, the only on-disk password copy is a sealed file under `~/workspace/officerpath-ai-keystore/` (outside both repos). The keystore itself is not in either repo. No keystore material was opened.
4. **`send-notification` Edge Function (file pattern only).** It loads a Firebase service-account private key from the `FIREBASE_SERVICE_ACCOUNT` Edge Function secret at runtime — correct pattern (secret, not code). Whether the secret is set in the Dashboard was not verified here (same as the 2026-11-20 audit).
5. **`google-services.json` exists** at `android/app/google-services.json` — client config only (no server key) per the 2026-11-20 audit; **not re-verified** in this session.
6. **Engine auth posture (VERIFIED, good):** JWT verified server-side via `auth.get_user`; tokens never decoded locally, never logged, never stored; service-role client used only server-side from env; ownership enforced on storage path + job reads (404 for others); rate limits on register/retry; error bodies leak no internals; secret-redaction in logging; `test_security.py` asserts no secret material in any response.
7. **`.gitignore` coverage (VERIFIED):** engine covers `.venv/`, `__pycache__/`, `*.pyc`, `.env`, `.pytest_cache/` — adequate for the skeleton, missing `*.keystore`/`*.jks`/`key.properties` (D10). Flutter covers `.env`, `*.keystore`, `*.jks`, `key.properties`, `build/`, `*.apk` — adequate, subject to the `admin/config.js` question above.
8. **Threat notes carried forward (from the prompt §18, not yet implemented):** uploads are untrusted — file-type/size/page-count validation exists only as *metadata* checks at register time (no magic-byte, decompression-bomb, or content validation exists yet — the file bytes are never seen by the engine today); no sandboxing, no signed expiring download URLs, no retention/deletion policy, no dependency audit. All are M1/M7 work.

## 9. Risks and decisions owed by the owner

| # | Risk / decision | Impact if undecided |
|---|---|---|
| R1 | **GitHub repo + branch.** Local code is not in any git repo. Pushing to `hasankhan62742-beep/officerpath-pdf-engine` (public, was empty) and creating branch `officerpath-phase1-engine` needs the owner's go-ahead — and the `admin/config.js` check in §8.2 must happen first. | No CI, no version control, no deploy source. Blocks M1. |
| R2 | **Hosting (ADR-001, PROPOSED).** Render free Stage 1 vs Cloud Run (blocked: GCP billing paused) vs Hostinger VPS (needs payment). Render free = 512 MB / 0.1 CPU / sleeps after 15 min idle / ~30–60 s wake (web-verified 21 Nov 2026 — see ADR-001). Consequence: PaddleOCR-class local OCR is likely too heavy/slow there; Gemini-first is the viable Stage-1 route. | Deploy target decides Dockerfile, worker shape, and OCR choice. Blocks M1 deploy step. |
| R3 | **OCR approach (ADR-002, PROPOSED).** Gemini-advisory-first (proven 100/100 on PPSC-66 VM) vs offline-first PaddleOCR/Tesseract (unproven on Nastaliq; Tesseract ceiling 16–20/100 cited). Needs the server Gemini key question settled on the owner's terms — key is deferred ("baad ki bat"), do not keep asking. | Decides M3's first engine + the M3 benchmark. |
| R4 | **Migration 015 apply.** Needs owner go-ahead via Dashboard SQL Editor (VM has no SQL access). Until applied, `/health` cannot be healthy and no end-to-end register flow is possible live. | Blocks M1 gate. |
| R5 | **Gemini recitation filter.** Blocked VM baseline pp. 3/5 on PPSC-66; a server route inherits it. Mitigation (page crops, `[?]` marking) is designed in the app's prompt but unproven server-side. | M3 benchmark must measure it, not assume it away. |
| R6 | **Render free + Supabase free fragility.** Render sleeps (15 min idle); Supabase pauses after 7 days inactivity; Render free Postgres (not used — Supabase is the DB) is irrelevant, but the 750 instance-hours/month quota covers exactly one always-on service. Keep-alive pings are a deliberate trade-off (they consume the quota and can mask real outages). | Stage-1 reliability; must be documented, not silently assumed. |
| R7 | **Scope creep risk.** Both master prompts describe a very large system (§§1–27 / §§1–22). The M1–M8 plan below sequences it, but each gate must be allowed to *fail honestly* — a failed gate with a documented owner decision is a valid outcome; silent scope-cutting is not. | The "Ultimate Edition" must not become a checklist that is ticked without evidence. |

## 10. Phase 1 plan — Milestones M1–M8 (Ultimate numbering; v2 mapping in §1.3)

Per-milestone rhythm (adopted from v2 §22): **explain → implement → test → fix → document → limitations → preserve stability**. At each gate: state the plan, implement real code, run tests, fix failures, document, list limitations, confirm the existing app is unaffected. Do not advance past a failed gate without documenting the failure and the owner's decision.

| Milestone | Objective | Gate (must be demonstrated) |
|---|---|---|
| **M1** — Project structure, config, DB schema, migrations, ingestion, validation, storage | GitHub repo linked, branch `officerpath-phase1-engine`, SQLAlchemy 2.x + Alembic, §14 schema (documents/pages/jobs/stages + OCR/evidence tables), ingestion + validation (magic bytes, size/page/DPI limits, SHA-256 dedup, per-page classification), storage abstraction, lint/typecheck/secret-scan in CI; rewrite Cloud Run deploy docs for Render | Upload works end to end (local + staging); malformed files rejected with reasons; migrations up/down pass on a copy of realistic data; `GET /health` healthy against staging Supabase |
| **M2** — PDF analysis, page classification, rendering, adaptive preprocessing | PyMuPDF/pdfplumber digital extraction; page render at bounded DPI; OpenCV adaptive preprocessing profiles with mark-preservation checks (ticks/stars/circles/highlights survive; colour copy kept) | Quality metrics per page; marks preserved on fixtures; before/after metrics recorded |
| **M3** — OCR abstraction, engines, digital extractor, layout analysis | `OCREngine`/`LayoutAnalyzer` plugin interfaces + registry; adapters: digital extractor, Tesseract, PaddleOCR (benchmarked), Gemini-advisory (disabled by default, suggestions only); column/reading-order/table detection; golden dataset v1 with ground-truth annotations from `test-fixtures/ppsc66/` | Engine benchmark report (CER/WER per engine per fixture class, incl. Nastaliq + recitation-filter behaviour); reading order correct on multi-column fixtures |
| **M4** — MCQ and option extraction | Port of the Dart parser rules as the reference implementation (category separation, sequence validation, paper-identity gate); candidate scoring, not regex-only; duplicates flagged, never deleted | Precision/recall/F1 measured on the golden set; PPSC-66 from **server OCR** (not phone text) parsed and reported honestly |
| **M5** — Answer detection (key, inline, style, visual, handwriting) | Per-source detectors (key tables, inline, digital style, visual marks, handwriting) with measured precision/recall; evidence records per answer; precedence manual > key > inline > digital style > visual > inferred | Per-detector precision/recall measured on fixtures; conflicts preserved, never silently resolved |
| **M6** — Matching, validation, confidence scoring, reports, review APIs | Document-scoped deterministic matcher; validators; calibrated confidence; extraction report; review/correction/verification/reprocess APIs with full audit trail (v2 §17 admin/review backend); Flutter "Server parse" toggle (additive, default off) | Conflicts + unmatched entries preserved with reasons; calibration report; phone end-to-end on the 3 acceptance files via the server route |
| **M7** — Background jobs, security hardening, observability, performance | Queue (ADR: Celery+Redis vs RQ vs Postgres-backed — decide by evidence + cost), retries/backoff/dead-letter, idempotent stages, progress, cancellation; security tests (malicious files); structured logs + correlation IDs + metrics + debug overlay tool; load/memory tests | Load + memory tests pass on stated hardware; security tests pass; measured pages/minute + memory/worker |
| **M8** — Full test suite, benchmarks, docs, deployment guide, completion report (= v2 M9) | Full suite + coverage gate on core modules; benchmark regression check in CI; deployment guide (Render Stage 1, Hostinger Stage 2 path); runbook; honest prototype-vs-production assessment | All gates met or honestly reported; Phase 1 completion report; **STOP CONDITION: no Phase 2 until every critical Phase 1 acceptance test passes live on the owner's phone** |

**Acceptance files for every milestone from M4 onward:** PPSC-66 PDF, computer table photo, Paper 60 photo — the same three files the owner will use for the phone proof. A milestone is not "done" if it only passes on synthetic fixtures.

## 11. What this audit did NOT do (honest limits)

- No feature code written; no files in `officerpath-ai/lib/` touched; no migrations applied; no deploys; no paid services; no git operations.
- Flutter `analyze`/`test` not run (no toolchain on VM). Live Supabase not queried. GitHub repo state not verified live (no access in this session). Docker image not built (no Docker). OCR engines not installed or benchmarked (M3 work). No accuracy numbers were measured in this audit — every accuracy figure herein is cited from a named earlier report.
- The 2026-11-20 audit's §§6–8 (plan detail, guessed/unverified list) were not re-read in full; this document relies on its §§0–5, which were read.

## Appendix A — Evidence-label index

Every important statement above carries a label inline (VERIFIED / ASSUMED / UNVERIFIED / UNKNOWN / cited). Statements without a label are either structural (headings, tables of file names) or explicitly marked as cited from the 2026-11-20 audit / PPSC66 baseline. If a future reader finds an unlabelled factual claim, treat it as UNVERIFIED until checked.
