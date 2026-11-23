# Milestone 10 — Complete QA + Deployment Readiness (Phase 2, FINAL)

**Date:** 2026-11-23 (PKT) · **Branch:** `officerpath-phase2-web` ·
**Scope:** the final Phase 2 milestone — defect fixing (carried items),
full QA of the whole product end to end, and deployment readiness as
documentation + config only. **NO deploy, no push, no paid services,
no Phase 3 payments.**

## 1. What was fixed and built

### (A1) Async-jobs re-submit 500 — DECIDED, FIXED, TESTED (M9 §6.5 carry)

The pre-existing M7 edge: re-submitting byte-identical content to
`POST /api/v1/async-jobs/parse` raised
`IntegrityError: UNIQUE constraint failed:
documents.user_id, documents.content_hash` at `async_jobs.py:123`.
The `/documents/upload` path had the M6 dedup; the async path never
got one.

**Decision (documented in `docs/API.md` + doc 02):** return the
ORIGINAL job with **200 + `idempotent_replay: true`** — the same
choice as the register/upload path's contract (`POST
/api/v1/documents/register` returns the original job with
`idempotent_replay: true`, 200 on replay / 201 on fresh). A 409/422
was rejected: the upload path already established replay as the
product's contract, and a 4xx would have made the two upload paths
disagree about the same user action.

**Behaviour:** dedup lookup by `(user_id, content_hash, deleted_at
IS NULL)`; the latest job by `created_at` desc is returned with its
current status (`done` if already finished — never a new document,
never a 500). Soft-deleted documents never block a replay (matches
the M6 partial-index rule); delete-then-re-upload creates a fresh
job. Race guard: `IntegrityError` on flush → rollback → re-lookup →
return the winner's job. A live document with NO job raises 500
`internal_error` (partial write — cannot happen on either endpoint's
happy path; both create doc + job in one transaction).

**Changes:** `app/api/v1/async_jobs.py` (dedup lookup, `JSONResponse`
200 on replay, `IntegrityError` race guard, `get_logger` import),
`app/schemas/async_jobs.py` (additive `idempotent_replay: bool =
False` to `AsyncJobCreatedResponse`). No Alembic migration needed —
no schema change.

**Regression tests** (`app/tests/test_worker_jobs.py`, 3 new):
replay returns the original job with done status + exactly 1
document + 1 job + 1 stored object; replay after soft-delete → fresh
202 with new ids; same bytes from another user → fresh 202.
Targeted run 13/13; full suite 613/0.

### (A2) Lighthouse TBT tuning — Providers split (safe, measurable)

M9 baseline (VM-contended): Home 73 / Features 60, TBT-bound. Code
reading first: Home/Features are server components; the Pakistan-map
watermark is 890 bytes (not a driver); the whole app was wrapped in
root-layout `Providers` (client component: TanStack Query
`QueryClientProvider` + `ToastProvider`); `useQuery`/`useMutation`
are used ONLY under `/dashboard/*` and `/admin/*`, `useToast`
nowhere except the provider itself.

**Change:** `QueryClientProvider` + `ToastProvider` moved out of the
root layout into the dashboard and admin layouts only
(`web/app/layout.tsx`, `web/app/dashboard/layout.tsx`,
`web/app/admin/layout.tsx`, `web/components/providers.tsx` —
comment updated). Public pages no longer download or hydrate the
TanStack Query chunk (16 KB raw): verified directly — the home HTML
references the chunk **0 times** after the change. Header/footer
(client components, auth state + mobile menu) left alone. No visual
change; no route change (34 pages / 37 user routes, unchanged).

**Measured result — honest:** see §5. The chunk removal is real but
its Performance effect is inside this harness's noise floor
(Home 81 → 75, Features 80 → 79 across repeat runs; TBT swings
±300 ms on identical builds). No reliable gain demonstrated, no
regression. Production numbers can only come from the deployed site.

### (A3) `render.yaml` branch — one-line config fix

`render.yaml` still pointed at `officerpath-phase1-engine`. Fixed to
`officerpath-phase2-web` (verified by grep). This is the only
config-code change in (C); everything else in (C) is documentation.

### (B) Full QA — the whole product, end to end

- **Full suite:** pytest 613/0, ruff check + format clean (229
  files), mypy gate SUCCESS (68 files), `tsc` exit 0, `npm run
  build` PASS (34 pages / 37 routes), `npm run lint` 0 problems,
  OpenAPI 49 paths. See §2.
- **API regression sweep (M4–M9 + M10):** 17/17 steps PASS
  (`~/workspace/m10-e2e/api_e2e.py` → `api-proof.json`). See §4.
- **Browser E2E — the three acceptance files through the WEB UI:**
  37/37 steps PASS (`~/workspace/m10-e2e/browser_e2e.mjs` →
  `browser-proof.json`). PPSC-66 41/41/27, table photo 0/0/2,
  Paper 60 4/4/9 — UI counts == engine stored rows. See §4.
- **Walkthroughs:** desktop — all 9 dashboard + all 6 admin pages,
  0 px overflow; student `/admin` → `/dashboard` in the UI. Mobile
  360 px — 7 dashboard + 3 admin/notification pages, 0 px overflow.
- **No other defects surfaced** by the full suite. Triage: none
  silently dropped — the only failures seen were harness-script bugs
  (mine, §6) and environment incidents (restart, disk quota, §7).

### (C) Deployment readiness — docs + config, NOT the deploy

- `docs/phase2/migration-runbook.md` — ordered owner steps: 016
  bucket + 017 partial index via Dashboard SQL Editor (with
  verification queries + failure handling), then Alembic 0001–0009
  via `alembic upgrade head`, then the deploy-time smoke test
  (incl. the STOP CONDITION phone check).
- `docs/phase2/rollback-runbook.md` — Vercel instant rollback
  (Promote to Production); Render Dashboard Rollback; Alembic
  downgrades one revision at a time (0009/0008/0007/0006/0005/0003
  all REFUSE when their tables hold rows, 0004 never refuses, 0002
  drops the column, 0001 drops all 17 engine tables with NO refusal
  guard and must never run on live; 016 down needs an empty bucket,
  017 down fails while live+deleted row pairs share a hash and
  re-introduces the M6 bug, 015 down is destructive).
- `docs/phase2/deployment-checklists.md` — doc 06 executed as
  checklists: backend Render A1–A14 (A1 branch fixed in M10, A12
  Dockerfile never built / no Docker on VM, A13 keep-alive
  DEFERRED, A14 Render-free fit MARGINAL 465 MB vs 512 MB);
  frontend Vercel B1–B8 (B5 canonical domain placeholder
  `https://officerpath.ai` still unconfirmed by owner, B6 preview
  deployments are ENV-ONLY, B7 Vercel not connected);
  database/storage C1–C6 (C2/C3/C4 not applied, C5 blocked on C2,
  C6 owner verifies backups); post-deploy smoke test; 5 known
  deployment risks.
- `CHANGELOG.md` refreshed (was stale since M4): entries [2.10.0]
  M10 down to [2.1.0] M1 + [1.0.0] Phase 1 M8 complete, above the
  existing 0.5.0–0.1.0 entries.
- `TEST_REPORT.md` refreshed (was stale since M0, 22 tests): full
  gate table, per-milestone test counts, the M10 API + browser E2E
  proofs, the Lighthouse table with the honest reading, defects
  fixed, environment incidents, and the honest-gaps list.
- `docs/API.md` + `docs/phase2/02-api-integration-map.md` updated
  for the async-jobs replay behaviour.
- `docs/phase2/PHASE_2_COMPLETION_REPORT.md` — the Phase 2
  completion report (M1–M10 summary, final tables, architecture,
  ADRs, limitations, honest owner-step list).

## 2. Gate table (exact numbers)

| Gate | Result |
|---|---|
| pytest (full suite, re-run after all code changes) | **613 passed, 0 failed** in 299.88 s (610 M9 baseline + 3 new dedup tests; the first full run collected 610 because it started before the new tests were written — the re-run is the authority) |
| ruff check | clean (one UP017 fixed in the new test file first) |
| ruff format | clean, 229 files |
| mypy (CI gate) | SUCCESS, 68 files |
| `tsc` | exit 0 |
| `npm run build` | PASS, 34 pages / 37 user routes |
| `npm run lint` | 0 problems |
| OpenAPI paths | 49 (unchanged from M9) |
| API regression sweep | 17/17 steps PASS |
| Browser E2E | 37/37 steps PASS |
| Lighthouse | Home 81 → 75, Features 80 → 79 (median; see §5) |
| `web/.env.local` | untouched, real values (0600, mtime 2026-11-22 17:45) |
| Secrets scan (web/) | clean — service-role references only server-side in `app/`, as designed |

## 3. Unit tests (3 new, `app/tests/test_worker_jobs.py`)

All in the existing file (13 tests total in file, 13/13):

| Test | What it proves |
|---|---|
| `test_async_parse_replay_returns_original_job` | Identical bytes → 200, `idempotent_replay: true`, same `job_id`/`document_id`, status `done`, exactly 1 document + 1 job + 1 stored object |
| `test_async_parse_replay_after_delete_creates_fresh_job` | Soft-delete the document, re-submit → fresh 202 with new ids |
| `test_async_parse_same_bytes_other_user_creates_fresh_job` | Same bytes from another user → fresh 202 (dedup is per-user) |

## 4. E2E proof (`~/workspace/m10-e2e/`, M9 bank copy — 91 rows)

Harness: stub GoTrue :54399 + local engine :8001 + local web :3000
(next-server pid tracked properly — see §6 for the restart lesson).
Tesseract 5.3.4 (eng/osd/urd/ara) restored by the cell replay after
the 5th wipe.

### (a) API regression sweep — 17/17 (`api-proof.json`)

| Area | Proof |
|---|---|
| M4 dashboard | summary real: documents_total 4; jobs done 2 / failed 2 (live-doc jobs only) |
| M5 bank | total 91 = live bank; `q=capital` → 1; 27 unknown in first 100 |
| M6 builder | availability 64 / 27 / 0; test created (5q, 3600 s) |
| M7 exam | answers before start → 409; session `server_started_at` + `remaining_seconds` 3599, NO `correct_index`/`answer_source` in any snapshot; submit 5.0/5.0 = 100.0%; double submit same result_id |
| M8 results | result == stored row exactly (5.0/5.0/100.0, 5/0/0/0); retry keeps snapshots; history newest-first |
| M9 admin/security | student → 404 `not_found` on all 6 admin routes; admin overview real (users 1, documents 8, jobs 8, questions 91, tests 30, results 14, errors 2, notifications 16); notifications total 14, unread 11; security headers exact; CORS disallowed origin → no ACAO |
| M10 dedup | CA40 re-submit → 200, `idempotent_replay: true`, job_id `30b3992a-5ff3-4a57-803f-261aecdc9d6d`, status `done`, exactly 1 live document for (user, hash) |
| Health | `/health` → 503 **by design** in this harness (GoTrue-only stub, no PostgREST → Supabase probe unreachable); body honest: `degraded`, database `ok`, `ocr_tesseract: available`, disk `ok` |

### (b) Browser E2E — three acceptance files via the WEB UI (`browser-proof.json`)

Each file: real file picker → real Upload button → JobTracker live
→ document detail page counts compared with the engine's stored rows.
PPSC-66: the bank copy was soft-deleted first via the API (setup —
otherwise the M6 dedup replay would swallow the re-upload, exactly
as M9 did for CA40); the other two are fresh parses.

| File | UI counts (questions / answered / pending) | Stored | Verdict |
|---|---|---|---|
| `ppsc_paper_66.pdf` | **41 / 41 / 27** | 68 `extracted_questions` rows — exactly M5's 68 (M6 recovered only 51 after a page-3 Tesseract timeout); parse 224.3 s | PASS — UI == stored |
| `table-computer-q67-81-resent-20261121.jpg` | **0 / 0 / 2** | — | PASS — matches Phase 1 acceptance (0q / 2 pending) |
| `paper60-photo.jpg` | **4 / 4 / 9** | — | PASS — matches Phase 1 acceptance (4q / 4ans / 9 pending) |

Final bank state after the runs: 123 live questions, 6 live
documents, 15 test_results, 24 notifications. (The "unknown" key is
absent from `result_summary` — pending IS the unknown count here:
27 for PPSC-66, matching M5's 27 unknown.)

### (c) Walkthroughs — desktop + mobile 360 px (in the browser E2E)

- Desktop: `/dashboard`, `/dashboard/upload`,
  `/dashboard/documents`, `/dashboard/questions`, `/dashboard/tests`,
  `/dashboard/results`, `/dashboard/mistakes`,
  `/dashboard/notifications`, `/dashboard/profile`, `/admin`,
  `/admin/users`, `/admin/documents`, `/admin/jobs`, `/admin/errors`,
  `/admin/questions` — all 0 px overflow; student `/admin`
  redirects to `/dashboard` in the UI.
- Mobile 360 px: `/dashboard`, `/dashboard/upload`,
  `/dashboard/documents`, `/dashboard/tests`, `/dashboard/results`,
  `/dashboard/mistakes`, `/dashboard/notifications`, `/admin`,
  `/admin/users` — all 0 px overflow.

## 5. Lighthouse 13.6.0 (harness, localhost — NOT production numbers)

Same harness, same pages, before/after the Providers split. Two
after-runs per page (the first after-runs were INVALID — stale
server, §6 — and were discarded and re-measured).

| Page | Run | Perf | A11y | BP | SEO | TBT | LCP | CLS | JS bootup |
|---|---|---|---|---|---|---|---|---|---|
| Home | M9 (VM-contended) | 73 | 96 | 100 | 100 | 1,790 ms | — | — | — |
| Home | M10 before | 81 | 96 | 100 | 100 | 499 ms | 3.1 s | 0 | 1,246 ms |
| Home | M10 after (run 1) | 68 | 95 | 96* | 100 | 373 ms | 0.8 s | 0.688 | 925 ms |
| Home | M10 after (run 2) | 75 | 96 | 100 | 100 | 778 ms | 3.1 s | 0 | 1,350 ms |
| Features | M9 (VM-contended) | 60 | 94 | 100 | 100 | — | — | — | — |
| Features | M10 before | 80 | 94 | 100 | 100 | 440 ms | 3.5 s | 0 | 769 ms |
| Features | M10 after (run 1) | 75 | 94 | 100 | 100 | 143 ms | 0.8 s | 0.688 | 554 ms |
| Features | M10 after (run 2) | 79 | 94 | 100 | 100 | 475 ms | 3.6 s | 0 | 1,018 ms |

\* Home after-1 BP 96 was the stale-server artifact (console 500 +
MIME-type errors for a chunk the old server no longer had on disk) —
that run is discarded for Best Practices.

**Honest reading:** the measured Performance effect is inside this
harness's noise floor. Identical builds swing ±300 ms TBT and ±2.3 s
LCP between back-to-back runs (TBT 373 → 778 ms on the same build;
LCP 0.8 → 3.1 s), and the same M9 code measured 73 in M9 vs 81 here.
The CLS 0.688 in both after-1 runs is a flake: it reproduced as 0
on both repeat runs, with no attributed source nodes, and the change
touches no visual element. Median after vs before — Home 81 → 75,
Features 80 → 79 — is no reliable gain and no regression. The chunk
removal is real (0 references in the home HTML) but its effect is
below what this throttled VM can measure. The pre-tuning TBT
investigation (code reading only) also stands: the big chunks are
the Next.js framework (71 KB transfer) and React (68 KB); the
TanStack chunk is 16 KB raw (~6 KB transfer) — a small, real saving,
not a transformation. Production numbers can only come from the
deployed site.

## 6. What was found by measuring (bugs + fixes + lessons)

1. **Async-jobs dedup 500** — the carried defect, fixed (§1 A1).
2. **Stale-server Lighthouse runs (my process error, caught by
   measuring):** after the rebuild I "restarted" the web server with
   `kill $(cat web.pid)` — but the pid file held the `npx` wrapper's
   pid, not the `next-server` child's. The new server failed with
   EADDRINUSE and the OLD build kept serving while the new `.next`
   had replaced its chunks → 500 + MIME-type console errors in the
   after-runs (BP 96). Caught by reading the failing audits + the
   web log. Fixed by killing the real `next-server` pid and starting
   `./node_modules/.bin/next start` directly; both after-runs
   re-measured. **Lesson (standing):** after any restart, verify the
   serving pid AND the chunk list the page actually references
   before measuring.
3. **Harness-script bugs (mine, all fixed — the product was never at
   fault):** `api_e2e.py` used `search=` on the student bank (it
   takes `q=`), called availability without the required
   `source_type`, compared the summary's job count against ALL jobs
   instead of live-doc jobs, compared UUIDs dashed instead of hex,
   counted soft-deleted CA40 rows as live, and expected `/health`
   200 in a GoTrue-only-stub harness (designed 503).
   `browser_e2e.mjs` read the summary from `GET /api/v1/jobs/{id}`
   (which does not return `result_summary` — it lives on the
   document detail endpoint), looked for a "Pending" label (the UI
   says "Needs review"), and set the file input before hydration
   (the change event was dropped — fixed by waiting for the "Choose
   files" button first). Also fixed: the setup step now tolerates a
   missing live PPSC-66 doc (a previous failed run had already
   deleted it).
4. **No other defects surfaced** in the full suite or the sweep.

## 7. Environment incidents (not code failures)

- **Runtime restart mid-milestone** (the 2nd in M10): wiped system
  tesseract a 5th time and interrupted the harness setup mid-build
  (no confirmed result; state checked before retry: DB copy intact,
  servers dead, no partial writes). The cell's own os-intent replay
  restored tesseract 5.3.4 (eng/osd/urd/ara) after its `apt-get
  update` finished; my own `apt-get update` had failed on the replay
  holding the lock. Harness setup re-run cleanly afterwards.
- **Disk quota (EDQUOT, errno 122):** the overlay upper filled up —
  a 1 MB write failed even though `df` showed 47 G free. Cause: the
  npm cache (`~/.npm` 2.7 G) plus stale npx installs. Fixed by `npm
  cache clean --force` + deleting one failed npx extract (2.7 G →
  883 M). Lighthouse's first npx download and its JSON output both
  failed with the same -122 before the cleanup. The working
  Lighthouse 13.6.0 is M9's npx install
  (`~/.npm/_npx/0f94ee7615faf582/…/cli/index.js` — note: the entry
  is `cli/index.js`, not `cli/bin.js`, which exits silently with
  code 0 and no output).

## 8. Honest limitations

- `npm audit` NOT run (VM registry 403 `policy_denied`) — owner
  step on his machine.
- No email in the admin users list (needs service-role
  `auth.admin.list_users`, out of scope).
- Invalid-token → 401 unit-test-only (stub limitation).
- iPhone Safari / real device unverified.
- Lighthouse = localhost-harness numbers (see §5).
- Urdu preservation not E2E-proven.
- Inferred-answer flag + Q&A-pair card rendering unit-test-only.
- Live Supabase unchanged (016 bucket + 017 unapplied, M3
  auth-loop blocker + unconfirmed test user still owner steps).
- Docker never built (no Docker on VM); GitHub CI never run (no
  push).

## 9. What is NOT done (not M10)

- The deploy itself (Render + Vercel), any paid service, Phase 3
  payments.
- Any live migration application (016/017) — owner steps in the
  migration runbook.
- Live phone verification of the three acceptance files — the STOP
  CONDITION (see the completion report §8).
- `flutter analyze` on the toggle files (owner step, no SDK on VM).
- GitHub App install + push (owner step).

## 10. Files changed

| File | Change |
|---|---|
| `app/api/v1/async_jobs.py` | Dedup lookup, 200 replay, `IntegrityError` race guard |
| `app/schemas/async_jobs.py` | `idempotent_replay: bool = False` (additive) |
| `app/tests/test_worker_jobs.py` | 3 regression tests |
| `web/app/layout.tsx` | Providers removed from root layout |
| `web/app/dashboard/layout.tsx` | Providers added |
| `web/app/admin/layout.tsx` | Providers added |
| `web/components/providers.tsx` | Comment updated (M10 scoping) |
| `render.yaml` | branch → `officerpath-phase2-web` |
| `CHANGELOG.md` | Refreshed M1–M10 |
| `TEST_REPORT.md` | Refreshed through M10 |
| `docs/API.md` | Async-jobs replay behaviour |
| `docs/phase2/02-api-integration-map.md` | Async-jobs replay behaviour |
| `docs/phase2/migration-runbook.md` | NEW — ordered owner steps (016 + 017 + Alembic) |
| `docs/phase2/rollback-runbook.md` | NEW — web + engine rollback, Alembic downgrades |
| `docs/phase2/deployment-checklists.md` | NEW — doc 06 executed as checklists |
| `docs/phase2/PHASE_2_COMPLETION_REPORT.md` | NEW — Phase 2 completion report |
| `docs/phase2/milestones/MILESTONE_10_REPORT.md` | This report |

Harness (never committed): `~/workspace/m10-e2e/` — `setup.sh`,
`gotrue_stub.py`, `api_e2e.py`, `browser_e2e.mjs`,
`api-proof.json`, `browser-proof.json`,
`lighthouse-{home,features}-{before,after,after2}.json`,
`engine.db` (M9 bank copy + M10 runs).
