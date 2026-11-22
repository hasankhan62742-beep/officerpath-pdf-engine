# Phase 1 Completion Report — OfficerPath AI Document Intelligence Engine

**Date:** 2026-11-22
**Branch:** `officerpath-phase1-engine` (local only — no push yet)
**Status: PHASE 1 COMPLETE (local).** All eight milestones
M0–M8 are built, measured, and parent-verified on the VM.
Nothing is deployed, nothing is live-verified on the owner's
phone: the Phase 1 STOP CONDITION (critical acceptance tests
passing live) is still unmet, and the owner steps in §7 are
still outstanding. This report is the handover the owner uses
to send Phase 2.

All numbers below are measured on the dev VM (1.5 shared CPUs,
6 GB RAM) and labelled VM numbers — **never Render numbers**.
Anything unmeasured is labelled UNVERIFIED.

## 1. What Phase 1 set out to do

From `MASTER_PROMPT_PHASE1_ULTIMATE_2026-11-21.md`: build a
Python FastAPI server engine that turns a student's upload
(PDF or phone photo of a competitive-exam paper) into
structured, traceable, test-ready MCQs — question + 4 options
+ answer + the evidence for that answer — with a truth rule
that governs everything: **never fabricate**; an UNKNOWN
answer is a correct outcome, a guessed answer presented as
correct is the worst failure; answer keys never cross-apply
between papers; originals immutable. The Flutter app becomes
a thin client ("Server parse" toggle); market users need no
Gemini key (the key lives only on the server, and is deferred
by the owner in any case). Hosting: Stage 1 Render free,
Stage 2 Hostinger KVM 1 VPS. Acceptance files throughout:
PPSC-66 PDF, computer table photo, Paper 60 photo — tested on
the owner's own phone before anything is called done live.

## 2. What each milestone delivered

- **M0 — Audit (2026-11-21, gate MET as an audit, no code).**
  The engine was a clean, tested **skeleton only** (FastAPI +
  register/jobs/health; 22/22 pytest; zero OCR/layout/
  extraction code). Deliverables: `docs/audit/
  REPOSITORY_AUDIT.md`, ADR-001 + ADR-002 (both APPROVED by
  the owner 17:03 PKT). The audit established that the
  PPSC-66 phone failure was an input-quality failure at the
  on-device OCR stage, not a parser-logic failure — which is
  why the server engine exists at all.
- **M1 — Schema, ingestion, deploy docs (commit `9a584f0`,
  76 files, pytest 69/0, gate PARTIALLY MET).** SQLAlchemy 2.x
  schema (17 tables), ingestion/validation (magic bytes,
  limits, SHA-256 dedup, per-page classification), storage
  abstraction, upload single+batch endpoints, ADR-003, Render
  deploy docs + `render.yaml`, CI gates. pip-audit 14 vulns →
  0. The gate was partial for one reason only: **the GitHub
  push failed (403 — the Muse GitHub App is not installed on
  the repo)**. Owner step, still outstanding.
- **M2 — PDF analysis + preprocessing (commit `9e20654`, 45
  files, pytest 113/0, gate MET).** PyMuPDF 1.26.3 analysis,
  real per-page classification (PPSC-66 all 7 pages → scanned),
  bounded-DPI rendering, 6 OpenCV preprocessing profiles,
  before/after quality metrics, mark retention 0.997–1.076.
  ADR-004: **PyMuPDF is AGPLv3** — accepted while the repo is
  public; it must be replaced or licensed before closed-source
  distribution.
- **M3 — OCR + layout (commits `5b397ec`, `670df43`,
  `a769157`, `d1e11ac`, pytest 203/0, gate MET).** OCR
  abstraction (digital, Tesseract, PaddleOCR, Gemini-advisory
  disabled by default), layout analysis, golden dataset v1,
  ADR-005. Measured: Tesseract CER 0.068–0.152 on PPSC-66
  pages 1–5 but 0.32–0.54 on the key pages; PaddleOCR worse
  (0.31–0.43) and OOM-killed at 1,775–3,667 MB — **demoted to
  VPS-only**. Layout bug fixed by measurement (CER 0.61 →
  0.0935).
- **M4 — MCQ extraction (commit `111f3f2`, 76 paths, pytest
  316/0, gate MET).** A verbatim port of the Flutter Dart
  parser (`app/pipeline/extract/`, 12 files), 5 format paths
  incl. first-class `qa_pair`, golden dataset v2 (38 entries),
  ADR-006 (deployment-aware OCR routing). Overall digital MCQ
  Q P/R/F1 0.7976/0.9104/0.8503, options 1.0/0.9977/0.9989,
  answers 1.0/1.0/1.0. Programmatic ground truth (never
  hand-typed): TestPoint 1,375 rows, Computer Q&A 960 pairs,
  CA40 40/40, Urdu NOA 135, monthly CA 125 with answers
  UNKNOWN, Pak Study 1,032 numbers with no answer marking.
- **M5 — Answer detection (commit `a430297`, 27 files, pytest
  377/0, gate MET).** `app/pipeline/answers/` (9 files — key,
  inline, style, visual, handwriting detectors + precedence
  resolver), positional fix in tables. Per-detector P/R/F1:
  trailing key on ideal text 1.0s, live PPSC-66 OCR
  0.9744/0.38/0.5468; inline TestPoint and Computer Q&A 1.0s;
  style star on live photo 0.8333/0.25/0.3846. **TestPoint FP
  248 → 28.** PPSC-66 single-path recovery 41/100 (OCR-bound;
  Q1–9 numbers physically clipped at the page edge, ceiling
  ≤ 91/100). Handwriting answer-mark class UNVERIFIED.
- **M6 — Matching, validation, calibration, review APIs
  (commit `9db0fc0`, 34 files, pytest 448/0, gate MET).**
  `app/pipeline/matching/` (9 files), review APIs (parse,
  review list, corrections with audit trail, report),
  ADR-007 (promotion rule) + ADR-008 (no quality-driven PSM
  routing — `select_psm` always returns PSM 3). PPSC-66 live
  promotion **14 → 41 answered**; key-region location
  **80 TP/2 FP → 84 TP/0 FP**. Calibration ECE 0.0003 before
  AND after (detectors already calibrated; below 1.0
  UNVERIFIED). One real bug found by measuring and fixed:
  number-only verdict join gave TestPoint end-to-end answers
  0.5084 — fixed by occurrence pairing, now 1.0. Flutter
  "Server parse" toggle prepared only (no branch possible —
  no `.git` in the Flutter repo; no `flutter analyze`; no
  APK/release).
- **M7 — Background jobs, security, observability,
  performance (commit `1051fe4`, 32 files, pytest 489/0, gate
  MET).** `app/workers/` (async pipeline, atomic claim,
  per-stage 600 s timeout, cancel, retry, in-process worker +
  CLI runner, ADR-009), security (per-user 404s, 422
  `file_too_large` everywhere, rate limit 10/min → 429,
  secrets grep 0 offenders in 101 files), observability (JSON
  logs, real `/health` truthfully degraded, `/metrics`),
  performance (Tesseract ~93% of a PPSC-66 parse; render-once
  for multi-pass ~17 s saved; 150 DPI rejected; page-parallel
  OCR rejected for 0.1 CPU). Union merge KEPT as optional
  mode (40 → 53 numbers, 41 → 62 questions, 61/62 correct,
  ADR-010); section identity fixed; server image endpoint
  (`POST /api/v1/documents/parse-image`) + Flutter
  `importImage` wired. Render-free fit measured: **marginal,
  ~50 MB headroom**. Incident (not a code defect): a runtime
  restart wiped system tesseract + /tmp mid-milestone; the
  agent reinstalled it — the deploy must install tesseract in
  the image, never rely on the VM.
- **M8 — Full suite, benchmarks, docs, deployment guide
  (this milestone, gate MET).** Acceptance tests through the
  public API (the three acceptance files — previously only
  exercised by benchmark scripts), coverage config
  (pytest-cov) + per-package figures, final benchmark
  (M7 numbers reproduced exactly), `docs/API.md`,
  `docs/deploy-render.md` (verified against the M8 code),
  `README.md` rewrite, this completion report, `render.yaml`
  updated (worker settings + 1800 s stage timeout),
  `Dockerfile` fixed (explicit `tesseract-ocr-eng` + `osd`).
  No pipeline behaviour changed in M8.

## 3. Final measured results (M8, VM numbers)

### Accuracy — end-to-end resolved MCQs

| Fixture | Q P/R/F1 | Answers | Answered |
|---|---|---|---|
| TestPoint (1,375 GT) | 0.98 / 1.0 / 0.9899 | **1.0 / 1.0 / 1.0** | 1,403 / 0 pending |
| Computer Q&A (960 GT) | 0.8846 / 0.6948 / 0.7783 | 0.991 | 667 matched (qa_pair) |
| CA40 (40 GT) | 1.0 / 1.0 / 1.0 | **1.0** | 40 / 0 |
| Urdu NOA (135 GT) | 1.0 / 0.7778 / 0.875 | **1.0** | 105 / 2 pending |
| PPSC-66 live single-path | 41 q, 41 answered | 40/100 distinct numbers, 40/40 correct | 27 pending |
| PPSC-66 live multi-pass (optional) | 62 q, 62 answered | 53/100, 61/62 correct | 89 pending |
| Paper 60 live | Q 0.25 / 0.05 / 0.0833 (1/20) | 1.0 on the 1 matched | 4 q / 4 ans / 9 pending |
| Key region (live key) | whole-blob 0.9756/0.80/0.8791 → region **1.0/0.84/0.913** (84 TP, 0 FP) | | |
| Promotion (ADR-007) | 14 → 41 answered, 54 → 27 pending (27 promoted) | | |
| Calibration (1,559 pairs) | ECE 0.0003 before AND after (identity mapping) | Below 1.0 UNVERIFIED | |

### Latency + memory (VM; M7 clean baseline, M8 contended re-measurement)

| Fixture | M7 clean (s) | M8 contended (s) | Tree peak (MB) |
|---|---|---|---|
| PPSC-66 single-path | 127.9 | 297.3 | 400–441 |
| PPSC-66 multi-pass | 358.5 | 859.6 | 461–465 |
| TestPoint digital | 20.9 | 49.7 | — |
| CA40 digital | 0.1 | 0.1 | — |
| Computer table photo | 14.3 | 29.6 | 294–298 |
| Paper 60 photo | 31.1 | 63.1 | 363–370 |

M8 latencies are ~2.3–2.4× M7's because the VM was under
heavy contention from other agents during the M8 run (the
M8 suite itself took 555 s vs M7's 90 s). Accuracy and
memory reproduced exactly, so the M7 latencies remain the
clean baseline. **Render-free fit: fits, marginally** —
worst fresh-process tree peak 465 MB vs 512 MB (47 MB
headroom). One parse at a time on Render free.

### Test suite (M8, parent-verified pattern)

pytest **492 passed / 0 failed** (M7's 489 + 3 new
acceptance tests), ruff check + format clean, mypy CI gate
`mypy app/db app/pipeline app/storage` SUCCESS (68 files).
Coverage: see the M8 report for per-package figures.
Full suite takes ~9 min (the 3 acceptance tests run real
OCR, ~3 min of that).

## 4. Architecture as built

```
Flutter app (v2.0.5) ── "Server parse" toggle (OFF by default)
        │  multipart PDF / JPEG-PNG, Supabase JWT
        ▼
FastAPI (app/main.py) ── middleware: request-id + JSON logging,
        │  size limit (422 file_too_large), error model
        ├─ GET  /health /version /metrics (no auth)
        ├─ POST /api/v1/documents/register|upload|upload/batch
        ├─ GET|POST /api/v1/jobs/{id} (+ retry)
        ├─ POST /api/v1/documents/parse[?multi_pass] (sync)
        ├─ POST /api/v1/documents/parse-image (sync, photo)
        ├─ GET  /api/v1/jobs/{id}/review
        ├─ POST /api/v1/documents/{id}/questions/{qid}/corrections
        ├─ GET  /api/v1/documents/{id}/report
        └─ POST /api/v1/async-jobs/parse (202)
            GET|POST /api/v1/async-jobs/{id} (+ cancel, retry)
        ▼
Worker (app/workers/, ADR-009) — in-process by default,
        │  or `python -m app.workers.runner` (VPS)
        │  atomic claim → stages → done/failed/cancelled
        ▼
Pipeline (per document)
  ingest → classify → render (200 DPI, PyMuPDF) → OCR
  (digital text first; Tesseract eng+urd PSM 3; PaddleOCR
  gated off render-free; Gemini advisory disabled)
  → layout → extract (Dart-port parser) → answers
  (5 detectors + precedence) → matching (promotion,
  key-region, validation, calibration) → report
        ▼
Persistence (M1 schema, SQLAlchemy + Alembic 0001/0002)
  documents, jobs, pages, stages, ocr blocks, questions,
  options, answers, evidence, reports, manual_corrections,
  review_history, errors, audit log, rule sets
  (Supabase: auth + documents/jobs tables + pdf-documents
  bucket — migration 015, NOT applied live yet)
```

## 5. Decisions (ADR-001 … ADR-010, one line each)

- **ADR-001 — Hosting baseline:** Render free Stage 1,
  Hostinger KVM 1 VPS Stage 2; GCP/Cloud Run parked (billing
  paused). APPROVED by the owner 2026-11-21.
- **ADR-002 — OCR engine approach:** digital text first,
  Gemini-advisory when a server key exists, PaddleOCR/
  Tesseract fallback. APPROVED by the owner 2026-11-21.
- **ADR-003 — Persistence:** SQLAlchemy + Alembic for engine
  tables; supabase-py kept for Auth + documents/jobs.
- **ADR-004 — PDF + preprocessing:** PyMuPDF, OpenCV-headless,
  Pillow, NumPy. PyMuPDF is AGPLv3 — replace/license before
  closed-source distribution.
- **ADR-005 — OCR engine evaluation (M3):** PaddleOCR demoted
  to VPS-only (OOM at 1.8–3.7 GB); Tesseract is the Render-free
  OCR path.
- **ADR-006 — Deployment-aware OCR routing:** the router never
  selects PaddleOCR on a profile whose memory budget is below
  its measured peak.
- **ADR-007 — Pending-question promotion rule:** promote only
  on key/inline/style verdicts, confidence ≥ 0.9, no conflicts,
  exactly 4 options; never on `inferred` alone.
- **ADR-008 — Per-page PSM, no quality-driven routing:**
  `select_psm` always returns PSM 3 — no M2 quality metric
  separates the one page that wants PSM 4.
- **ADR-009 — Background jobs:** in-process worker, jobs table
  as the queue — no Redis/celery, no new paid dependency.
- **ADR-010 — Union merge, optional mode, kept:** multi-pass
  gains +13 numbers / +21 questions at 2.8–3.1× time; 200 DPI
  kept; Render-free fit is marginal.

## 6. Honest limitations — what Phase 1 does NOT do

- **No live deployment, no live phone verification.** The
  STOP CONDITION is unmet: every number in this report is a
  VM measurement. No milestone is "done live" until the
  owner's phone proves it on PPSC-66 / table photo /
  Paper 60.
- **PPSC-66 live recovery is OCR-bound:** 40/100
  single-path (53/100 multi-pass). Q1–9 numbers are
  physically clipped at the page edge (ceiling ≤ 91/100).
- **Paper 60 live is 1/20 via Tesseract.** The two-column
  photo defeats Tesseract segmentation. It needs Gemini-vision
  OCR (key deferred) or better segmentation — Phase 2 work.
- **Render-free fit is marginal:** ~50 MB headroom, one
  parse at a time; a long-lived worker accumulates RSS with
  no restart policy wired (VPS-stage work).
- **Calibration below confidence 1.0 is UNVERIFIED** — the
  measured detectors almost never emit below 1.0 on these
  fixtures (1,558 of 1,559 pairs are at 1.0).
- **TestPoint residual 28 FPs** (numberless split-row
  fragments; never a wrong answer) — assessed and left
  deliberately in M7.
- **Handwriting answer-mark class UNVERIFIED** — no fixture
  has a verified handwritten answer mark; Paper 60's note was
  correctly classified as marginalia.
- **Monthly Current Affairs answers UNKNOWN** — the 5 monthly
  PDFs carry no answer marking in text; their 2 images per
  page were never OCR'd for marks.
- **No Gemini OCR.** The advisory adapter is disabled by
  default; no key is provisioned; no Gemini API call has ever
  been made.
- **No worker restart policy / per-job subprocess isolation.
  No page-parallel OCR, no 150 DPI** (both measured and
  rejected with reasons). **No `flutter analyze`** (no SDK on
  the VM — owner must run it).
- **PyMuPDF AGPLv3** (ADR-004) must be resolved before
  closed-source distribution.

## 7. Owner steps still outstanding (in order)

1. **GitHub App install** — add `officerpath-pdf-engine` at
   https://github.com/apps/meta-muse-ai/installations/new,
   then push (`git push -u origin
   officerpath-phase1-engine` from
   `~/workspace/officerpath-pdf-engine`). Until then: no CI
   has ever run on GitHub, and Docker has never been built
   (verified by config only — no Docker on the VM).
2. **Migration 015 live apply** — via Supabase Dashboard SQL
   Editor (steps + verification queries in
   `docs/migration-015-apply.md`), then `alembic upgrade
   head` with `DATABASE_URL` set. Until applied, `/health`
   can never report healthy.
3. **Render deploy** — connect the repo, confirm Free plan +
   Docker runtime, set the Dashboard secrets
   (`SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
   `ENVIRONMENT=production`). `render.yaml` already carries
   the non-secret values. Full procedure:
   `docs/deploy-render.md`.
4. **Gemini server key** — deferred by the owner ("baad ki
   bat"); nothing in Phase 1 needs it.
5. **Flutter `flutter analyze`** on the toggle changes
   (prepare-only, uncommitted files, intended branch
   `officerpath-server-parse-toggle`), then review — no APK
   or release until the server is deployed.
6. **Live phone verification** — the STOP CONDITION: PPSC-66
   PDF, computer table photo, Paper 60 photo through the
   toggle on the owner's phone.

## 8. What Phase 2 builds on (stable interfaces)

- **Endpoints** (`docs/API.md`): sync parse + parse-image,
  async jobs (submit/poll/cancel/retry), review list,
  corrections, report, health, metrics. Response shapes are
  in `app/schemas/review.py` and `app/schemas/async_jobs.py`.
- **Job states:** `queued` → `processing` →
  `completed` / `failed` / `cancelled`; stages with
  per-stage seconds; cancel via `result_summary`
  (`cancel_requested`); retry re-queues with `retry_count` +1.
- **Review/correction flow:** pending/unknown items listed
  per job; corrections are top of precedence, never overwrite
  originals, carry an audit trail (`manual_corrections` +
  `review_history`), and re-run validation.
- **Resolved-MCQ shape:** `number`, `text`, `options` (4 or
  `[]` for `qa_pair`), `correct_index` (−1 = UNKNOWN),
  `correct_letter`, `answer_source`, `confidence`,
  `raw_confidence`, `verified`, `inferred`, `status`, `kind`,
  `answer_text`, `page`, `paper` — plus `pending` items with
  reasons, `validation_issues` with codes, `promotion`
  report, and `evidence_trail` per answered question.
- **Answer precedence (standing):** manual verification >
  explicit key > inline answer > digital style > visual >
  inferred. Keys never cross-apply between papers.
- **Config surface:** `app/config.py` (all env vars, with
  defaults); `render.yaml` (Render values);
  `DEPLOYMENT_PROFILE` gates PaddleOCR; `WORKER_ENABLED` +
  `WORKER_STAGE_TIMEOUT_SECONDS` (1800 s on Render).
- **Golden dataset:** `app/tests/fixtures/golden/
  dataset.json` (38 entries) + `ppsc66/` fixtures; benchmark
  scripts `scripts/benchmark_m2.py` … `benchmark_m8.py`
  reproduce every number in this report.
