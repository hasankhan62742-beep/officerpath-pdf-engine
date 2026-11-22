# Milestone 8 Report — Full Suite, Benchmarks, Docs, Deployment Guide (Phase 1 Final)

**Date:** 2026-11-22
**Branch:** `officerpath-phase1-engine` (local only, no push)
**Gate verdict: MET** — Phase 1 is complete on the VM. No
pipeline behaviour changed in M8 (tests, coverage config,
and docs only); every M7 number was re-measured and
reproduced exactly. The Phase 1 STOP CONDITION (live phone
verification) is still unmet — M8 is local only, same as
M1–M7.

## Gate evidence (actually run, this session)

| Gate | Result |
|---|---|
| pytest (full suite) | **492 passed / 0 failed** (555.6 s) — 489 M7 baseline + 3 new M8 acceptance tests |
| pytest --cov (same suite) | **492 passed / 0 failed** (707.1 s), **coverage 89%** (7,338 stmts, 806 missed) |
| ruff check | clean |
| ruff format --check | clean (186 files; `scripts/benchmark_m8.py` needed one format pass, applied) |
| mypy CI gate (`mypy app/db app/pipeline app/storage`) | **SUCCESS, no issues in 68 source files** |

The broad `mypy app/` errors (~382 in tests + pre-existing
skeleton main.py) remain out of scope per pyproject.toml, as
in M1–M7.

## 1. What M8 built

### A. Acceptance tests through the public API (new gap, now closed)

Until M8 the three acceptance files were exercised only by
the benchmark scripts, never by pytest. New
`app/tests/test_acceptance_api.py` (3 tests) runs them through
the real endpoints with the measured values:

- PPSC-66 PDF via `POST /api/v1/documents/parse`: 200, 7
  pages, 41 questions, 41 answered, 27 pending; every
  answered question carries an evidence trail.
- Computer table photo via `POST /api/v1/documents/
  parse-image`: 200, 0 questions, 2 pending (the honest
  measured outcome — Tesseract does not recover this ruled
  table; a future OCR improvement must update the test with
  a new measurement, not a guess).
- Paper 60 photo via `POST /api/v1/documents/parse-image`:
  200, 4 questions, 4 answered, 9 pending.

The sync parse of a 7-page scan takes ~130 s, so the tests
pass an explicit 900 s TestClient timeout (starlette
deprecates the argument — the warning is silenced locally
with a comment; the timeout is required, not optional). The
review/correction flow was already covered end-to-end
(`test_review_api.py::test_correction_flow`) and was not
duplicated.

### B. Coverage (new in M8)

`pytest-cov` added to `requirements-dev.txt` (7.1.0, the
version actually installed) and `[tool.coverage.run]` /
`[tool.coverage.report]` added to `pyproject.toml`
(source `app`, tests/migrations/`__init__` omitted).
Command: `.venv/bin/python -m pytest --cov=app
--cov-report=term-missing -q`.

| Package | Coverage |
|---|---|
| Overall | **89%** (7,338 stmts, 806 missed) |
| schemas | 100% |
| storage | 100% |
| db | 99.3% |
| database | 97.2% |
| services | 95.3% |
| security | 93.8% |
| layout | 93.8% |
| matching | 93.2% |
| core | 92.9% |
| pdf | 90.4% |
| app-root (config + main) | 89.8% |
| extract | 89.7% |
| preprocess | 88.6% |
| api | 87.1% |
| answers | 86.7% |
| ocr | 86.3% |
| interfaces | 86.3% |
| utils | 83.5% |
| workers | 79.7% |
| ingestion | 77.2% |
| integrations | 51.6% |

Untested areas that matter (one line each):

- `app/integrations/supabase_storage.py` **0%** — the
  signed-URL helper is defined but not yet used by any flow
  (its own header says so); it can only be tested against
  live Supabase, which Phase 1 never touches.
- `app/workers/runner.py` **37%** — `run_forever`'s loop and
  CLI entry are untested (a long-running loop); the
  `run_once` path it calls is fully tested, and the loop is
  wired in `app/main.py` lifespan.
- `app/pipeline/ocr/paddle.py` **56%** — PaddleOCR adapter
  internals; PaddleOCR is VPS-only by design and never runs
  in unit tests (no model download in CI).
- `app/pipeline/ocr/registry.py` **73%** — the PaddleOCR
  registration branches (same reason).
- `app/pipeline/ingestion/validator.py` **68%** — rejection
  branches for malformed/oversize/encrypted inputs; the
  happy paths and the main rejections are tested.
- `app/pipeline/answers/visual_detector.py` **79%** and
  `inline_detector.py` **70%** — visual-mark geometry
  branches and inline-answer edge cases on fixtures that do
  not occur in the golden set.
- `app/api/health.py` **79%** — the `unreachable` branches
  (a configured-but-down database) need a live database to
  exercise; the `not_configured` path is tested.
- `app/utils/metrics.py` **79%** — gauge/counter edge paths.

No test was deleted and no flaky test was found: the suite
passed 492/0 twice in this milestone (plain + coverage runs)
and the benchmark re-ran the same paths a third time.

### C. Final benchmark — M7 reproduced exactly

`scripts/benchmark_m8.py` →
`docs/benchmarks/m8-benchmark-2026-11-22.json` +
`BENCHMARK_M8_2026-11-22.md`. Full tables in the benchmark
doc; the headline:

| Fixture | M7 | M8 | Change |
|---|---|---|---|
| TestPoint Q / answers | 0.98/1.0/0.9899 / 1.0s | same | none |
| Computer Q&A Q / answers | 0.8846/0.6948/0.7783 / 0.991 | same | none |
| CA40 | 1.0s | same | none |
| Urdu NOA Q / answers | 1.0/0.7778/0.875 / 1.0s | same | none |
| PPSC-66 live single | 41 q, 41 ans, 40/100, 40/40 correct | same | none |
| PPSC-66 live multi | 62 q, 62 ans, 53/100, 61/62 correct | same | none |
| Paper 60 live | 1/20, answers 1.0 on matched | same | none |
| Key region | 0.9756/0.80/0.8791 → 1.0/0.84/0.913 | same | none |
| Calibration ECE | 0.0003 / 0.0003 (1,559 pairs) | same | none |
| TestPoint FP | 28 | 28 | none |
| Job pipeline / security / observability | all reproduced | same | none |

Latency caveat (honest): M8 latencies are ~2.3–2.4× M7's
(PPSC-66 single 297.3 s vs 127.9 s; multi 859.6 s vs
358.5 s; TestPoint 49.7 s vs 20.9 s) because the VM was under
heavy contention from other agents during the M8 run — the
M8 suite itself took 555 s vs M7's 90 s. No pipeline code
changed in M8, and the factor is uniform across independent
paths. **M7 latencies remain the clean baseline; M8's are
the contended re-measurement.** Memory reproduced in the
same band (worst tree peak 465 MB vs 461 MB), so the
**Render-free fit verdict stands: fits, marginally (47 MB
headroom)**.

One harness note: the M8 observability sample shows
`supabase: not_configured` where M7's showed `ok`, because
the M8 benchmark imports `benchmark_m6` first (which imports
the app before `benchmark_m7`'s dummy-env `setdefault`
runs). The check is correct in both cases — it reports the
actual configuration.

### D. Documentation (the permanent record)

- **`docs/PHASE_1_COMPLETION_REPORT.md`** (new) — the Phase
  1 completion report: what Phase 1 set out to do, one
  paragraph per milestone M0–M8 with gate verdicts and
  commits, final accuracy/latency/memory tables, architecture
  as built (text diagram), ADR-001…ADR-010 one line each,
  honest limitations, owner steps in order, and the exact
  interfaces Phase 2 can rely on.
- **`README.md`** (rewritten) — the real entry point: what
  the engine is, local quick start (including the system
  tesseract install, with the M7 lesson), tests + gates,
  API usage with curl examples, env-var table, database and
  deploy status, security rules, Flutter toggle state,
  project layout, and what Phase 1 does NOT do. Every
  command was verified by running it (uvicorn boot,
  `/health` 200 degraded, `/version` with commit `1051fe4`,
  `/metrics` counters, unauthenticated parse 401).
- **`docs/deploy-render.md`** (rewritten, verified against
  the M8 code) — every env var exists in `app/config.py`,
  the start command is the Dockerfile `CMD`, the health
  path is `render.yaml`'s `healthCheckPath`, and the memory
  numbers are the M7/M8 measurements. Drift fixed: the old
  doc said Stage-1 OCR is "Gemini-vision" (no such adapter
  exists — Gemini is advisory-only, disabled, no key) and
  "M7 designs" the in-process worker (M7 built it); the
  keep-alive decision is still DEFERRED (M6/M7 did not decide
  it). Docker is stated as verified by config only (no Docker
  on the VM).
- **`docs/API.md`** (new) — every endpoint from the actual
  routes (verified by listing them), with method, path, auth,
  request, response, and error codes; plus job states and the
  "what Phase 1 does NOT expose" list.
- **Docs drift audit:** read the ADRs and milestone reports;
  no milestone-report number was proven wrong by the M8
  re-runs (all reproduced), so no dated corrections were
  needed. The only drift found was in `deploy-render.md`
  (above) and the `README.md` (M1-era: it said the upload
  endpoint does "No OCR yet" and listed M7–M8 as future) —
  both rewritten.

### E. Clean-up + release readiness

- **`render.yaml` updated:** added `WORKER_ENABLED=true`
  (without it async jobs never run on Render), `WORKER_STAGE_
  TIMEOUT_SECONDS=1800` (M7 finding: the 600 s default
  would fail every 7-page job at 0.1 CPU), and
  `TESSERACT_TIMEOUT_SECONDS=300` (explicit, was code
  default only).
- **`Dockerfile` fixed:** the runtime install line now
  explicitly includes `tesseract-ocr-eng` and
  `tesseract-ocr-osd` (previously only `tesseract-ocr` +
  `urd` + `ara`, while the comment claimed eng+urd+ara).
  The explicit list now matches the set the M7 suite passes
  against on the VM. No image was built (no Docker on the
  VM) — the first CI build after the push verifies it.
- **Dead-code check:** ruff clean (no unused imports);
  coverage-driven pass found **no dead code to remove**.
  The lowest-coverage files are live paths, not dead ones:
  `supabase_storage.py` is intentionally-kept scaffolding
  (its header says "defined, not yet used"), `runner.py`'s
  `run_forever` is wired in `main.py` lifespan + CLI,
  `paddle.py` is registered by the router for VPS profiles.
  Nothing was deleted.
- **Run logs:** the 2 M6 run logs stay uncommitted, as in
  M6/M7 — they are intermediate stdout dumps; the JSON +
  markdown are the deliverables. They are now also in
  `.gitignore` (`docs/benchmarks/*.log`) so the tree is
  clean and the files stay on disk locally.
- **Flutter toggle state (confirmed):** exactly 3 files
  touched in `~/workspace/officerpath-ai/` on 2026-11-22 —
  `lib/services/server_parse_service.dart` (new, `parsePdf`
  + `parseImage`), `lib/services/pdf_import_service.dart`
  (`importPdf` + `importImage` route to the server when ON),
  `lib/screens/ai_settings_screen.dart` (SwitchListTile,
  default OFF, not-deployed-yet warning). No `.git`, so no
  branch exists (intended:
  `officerpath-server-parse-toggle`). No APK, no release, no
  version bump. `flutter analyze` still needs the owner (no
  SDK on the VM).

## 2. Incidents during the milestone (honest record)

1. **Runtime restart wiped system tesseract + /tmp — twice
   in one milestone.** The restart at the start of M8 removed
   the tesseract the M7 agent had reinstalled; a second
   restart mid-milestone (during the coverage run) removed
   it again and killed the coverage run with no output. Both
   times the agent reinstalled tesseract-ocr 5.3.4 +
   eng/urd/osd via apt (the second reinstall took only ~80 s
   because the package lists were cached; the first took
   ~14 min). All M8 files survived (they live in
   `~/workspace`, which persists); only `/tmp` artefacts were
   lost (the coverage log, re-created by re-running). Lesson,
   again: system packages are VM-ephemeral; the deploy must
   install tesseract in the image, never rely on the VM.
   (Recorded in README + deploy guide, not just here.)
2. **Coverage run interrupted by the restart** (above) — the
   run was re-started from scratch after the reinstall and
   completed 492/0 with 89% coverage. No result was taken
   from the interrupted run.

## 3. Files changed (engine, local only)

- New: `app/tests/test_acceptance_api.py`,
  `scripts/benchmark_m8.py`, `docs/API.md`,
  `docs/PHASE_1_COMPLETION_REPORT.md`,
  `docs/benchmarks/BENCHMARK_M8_2026-11-22.md`,
  `docs/benchmarks/m8-benchmark-2026-11-22.json`, this report.
- Modified: `README.md` (rewrite), `docs/deploy-render.md`
  (rewrite), `render.yaml` (worker settings), `Dockerfile`
  (explicit tesseract langs), `pyproject.toml` (coverage
  config), `requirements-dev.txt` (pytest-cov 7.1.0),
  `.gitignore` (benchmark logs), `docs/benchmarks/
  m6-calibration.json` (rewritten from this run's 1,559
  points — same fit as M6/M7, ECE 0.0003/0.0003; git shows
  no diff because the content is identical).
- Untracked logs (ignored, not committed):
  `docs/benchmarks/m6-benchmark-run.log`,
  `m6-psm-experiment-run.log`.

## 4. What is NOT done / carried to Phase 2

- No live Supabase (migration 015 still unapplied — owner
  step), no Render deploy, no Gemini key, no push. STOP
  CONDITION still unmet: no live phone verification (M8 is
  local only).
- No worker restart policy / per-job subprocess isolation.
- No page-parallel OCR; no 150 DPI; no TestPoint FP fix
  (all measured and rejected with reasons in M7).
- `flutter analyze` + APK/release: owner steps.
- PyMuPDF AGPLv3 (ADR-004) unresolved for closed-source
  distribution.
- **Phase 1 is complete as a local milestone.** The owner
  sends Phase 2 next (his words, 2026-11-21).
