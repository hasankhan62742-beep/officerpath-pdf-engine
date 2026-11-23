# Workstream F — Live Acceptance Testing Plan

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Repository (local):** `~/workspace/officerpath-pdf-engine`, branch `officerpath-phase2-web`
**Repository (GitHub):** `hasankhan62742-beep/officerpath-pdf-engine`
**Report date:** 2026-11-23 (PKT)
**Auditor:** Workstream F subagent (read-only inspection; no file modified except this report)
**Scope:** The live acceptance plan — the STOP CONDITION procedure, prerequisites, the three acceptance files with their local baselines, the phone procedure, the comparison method, smoke checks, and beta rollout criteria.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** Nothing is deployed yet — no Render service exists, no Vercel project exists. **No live test was run in this workstream and none is claimed.** Every result in this report is PENDING. The baselines in §3 are local M10 results, marked VERIFIED (locally) — they are the numbers the live test must reproduce, not live results. Live facts cited from earlier workstreams are marked parent-reported and were not re-checked here (this workstream has no live access of any kind).

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` (Workstream A), `docs/deployment/02-github-ci-report.md` (Workstream B), `docs/deployment/03-supabase-migration-runbook.md` (Workstream C), `docs/deployment/04-render-backend-deployment.md` (Workstream D), `docs/deployment/05-vercel-frontend-deployment.md` (Workstream E), `docs/phase2/milestones/MILESTONE_10_REPORT.md`, `docs/phase2/deployment-checklists.md` (§D, §E), `docs/PHASE_1_COMPLETION_REPORT.md` (the STOP CONDITION), `test-fixtures/ppsc66/PROVENANCE_2026-11-21.md` (in `~/workspace/officerpath-ai/test-fixtures/ppsc66/`).

---

## 1. The STOP CONDITION — stated plainly

**No fix is "done" until the owner's own phone proves it on the three acceptance files, through the live web upload UI, and the stored rows match the expected values.**

This rule has stood since Phase 1 (`docs/PHASE_1_COMPLETION_REPORT.md` §7) and is repeated in every milestone report since. It means:

- Local test suites (pytest 613/0), local E2E harnesses (API 17/17, browser 37/37), and local builds do **not** satisfy it. They are necessary evidence, not the acceptance itself.
- The proof must come from the owner's **real Android phone**, on the **live deployed site** (Vercel frontend + Render backend + live Supabase), using the **real file picker and Upload button** — not from the VM, not from a local server, not from a screenshot of a local run.
- The proof is the numbers: the UI counts shown on the document detail page **and** the stored rows in the database must both match the expected values in §6, exactly.
- **Until that happens, phone acceptance is BLOCKED, and this report's result section stays PENDING.** No agent may mark it complete on the owner's behalf, and no partial result ("two of three files passed") counts as acceptance.

---

## 2. Current state — what exists and what does not

| Item | State | Status |
|---|---|---|
| GitHub push, branch `officerpath-phase2-web`, head `461c9a2` | Pushed by the owner from his PC, 2026-11-23 ~12:34 PKT | COMPLETED (parent-reported) |
| First CI run on GitHub Actions | Never run; owner must check the Actions tab | PENDING |
| Supabase migration 015 (tables) | Live since M3 (2026-11-22) | COMPLETED (parent-reported) |
| Supabase migration 016 (bucket `pdf-documents`) | Applied + verified live 2026-11-23 | COMPLETED (parent-reported) |
| Supabase migration 018 (add `deleted_at` column) | Written, **not applied, not committed** | PENDING |
| Supabase migration 017 (partial unique index) | **FAILED live 2026-11-23** (`ERROR 42703: column "deleted_at" does not exist`); re-run blocked until 018 is applied and the Step 0 index check is done | BLOCKED |
| Alembic 0001–0009 on live Postgres | **Never run** (SQLite only, in tests and local harnesses) | PENDING |
| Render backend service | **Does not exist** — no service created, no deploy | PENDING |
| Vercel frontend project | **Does not exist** — no project created, no deploy | PENDING |
| Canonical production domain | Placeholder `https://officerpath.ai` unconfirmed as owned | REQUIRES OWNER APPROVAL |
| Render `CORS_ALLOWED_ORIGINS` | Missing from `render.yaml`; value depends on the domain decision | PENDING |
| Supabase redirect-URL allowlist | Not conclusively proven (localhost callback + production URL) | PENDING |
| Unconfirmed M3 test user `officerpath.m3.test@gmail.com` | Still exists in live Auth; must be deleted, **not** used for the phone test | PENDING |
| `npm audit` | Never run (VM registry 403); owner-machine step | PENDING |
| Dockerfile build | Never built anywhere; first CI `docker-build` job is the proof | PENDING |
| **Live phone acceptance** | **Not run — nothing is deployed yet** | **BLOCKED** |

---

## 3. The three acceptance files — what they are, and the local baselines

The files live in `~/workspace/officerpath-ai/test-fixtures/ppsc66/` (md5-verified copies; originals never modified). The **exact** files below must be used for the phone test — not older versions of the same pages.

| # | File | What it is | Size |
|---|---|---|---|
| 1 | `ppsc_paper_66.pdf` | Model Paper 66, Tehsildar BS-16 2021. 7-page CamScanner scan, 100 MCQs; answers only in the trailing key (page 7). md5 `0cd49fedff8ee83d620da29c729817d1`. | 5,911,945 bytes |
| 2 | `table-computer-q67-81-resent-20261121.jpg` | Computer table photo, Q67–81 (MS Word table, "Page 5 of 71"), 1504×2674. The **re-sent 2026-11-21** version — do NOT use the older `table-computer-q67-81.jpg`. | 1,076,655 bytes |
| 3 | `paper60-photo.jpg` | "PAPER 60 — DATA ENTRY OPERATOR (Police)", Q1–Q21, star-marked answers (e.g. Q1 (C) F5*). Infinix X6881 photo, 2160×3840, taken 2026-11-19 15:18. | 3,475,937 bytes |

### Local baselines — M10 browser E2E through the WEB UI (VERIFIED locally)

These numbers come from `docs/phase2/milestones/MILESTONE_10_REPORT.md` §4(b) (`browser-proof.json`): real file picker → real Upload button → JobTracker live → document detail page counts compared with the engine's stored rows. They are the **expected values** for the live phone test.

| File | UI counts (questions / answered / pending) | Stored rows | Verdict (local) |
|---|---|---|---|
| `ppsc_paper_66.pdf` | **41 / 41 / 27** | 68 `extracted_questions` rows — exactly M5's 68 | PASS — UI == stored |
| `table-computer-q67-81-resent-20261121.jpg` | **0 / 0 / 2** | — (table questions, no options) | PASS — matches Phase 1 acceptance (0q / 2 pending) |
| `paper60-photo.jpg` | **4 / 4 / 9** | — | PASS — matches Phase 1 acceptance (4q / 4ans / 9 pending) |

Reading the numbers:

- **"answered"** = questions with a known correct option (`correct_index` set). **"pending"** = questions whose answer is unknown (`correct_index = -1`); M10 notes the `result_summary` carries no separate "unknown" key — **pending IS the unknown count** (27 for PPSC-66, matching M5's 27 unknown).
- **PPSC-66 took 224.3 s to parse on the local VM** (1.5 CPUs). On Render free (0.1 CPU) the same 7-page OCR job is estimated at **~20 min** (M7 estimate, recorded in Workstream D §3.6 and deployment-checklists E4). The phone procedure (§5) is built around the async job model for exactly this reason — nobody waits on a sync call for 20 minutes.
- **The table photo and Paper 60 are single images** and parse far faster than the 7-page PDF (M7/M8 measured the acceptance photos at 294–370 MB peak memory, well inside the 512 MB budget). Allow several minutes each anyway; do not assume instant.
- **M10's PPSC-66 run needed setup first:** the bank copy was soft-deleted via the API before the upload, because otherwise the M6 dedup replay would swallow the re-upload and return the old job instead of a fresh parse (the same behaviour M9 proved for CA40). The phone procedure (§5 step 6) carries this rule forward.
- **Other M10 local baselines the phone test is compared against:** API regression sweep **17/17** steps PASS; browser E2E **37/37** steps PASS; desktop walkthrough (15 pages) and mobile 360 px walkthrough (9 pages) with **0 px overflow** everywhere. Final local bank state after the M10 runs: 123 live questions, 6 live documents, 15 test_results, 24 notifications (local harness bank — **not** live data, and not a live expectation).

---

## 4. Prerequisites — all must be true before the phone test starts

Do not start §5 until every row below is COMPLETED. A phone test run against a half-deployed system produces numbers that prove nothing and waste the owner's time.

| # | Prerequisite | Owner / workstream | Status |
|---|---|---|---|
| P1 | Supabase migration **018 applied** + column verified (`deleted_at`, `timestamp with time zone`) | Owner, Dashboard SQL Editor (Workstream C §5 Steps 0–1) | PENDING |
| P2 | Supabase migration **017 re-applied** + indexdef verified (must contain `WHERE deleted_at IS NULL`) | Owner, Dashboard SQL Editor (Workstream C §5 Step 2) | BLOCKED (needs P1) |
| P3 | **Alembic 0001–0009 on live Postgres**, `alembic_version` = `0009_m9_notifications`, 8 Phase-2 tables present | Owner machine with live `DATABASE_URL` (Workstream C §5 Step 3) | PENDING |
| P4 | **Render backend deployed** and `GET /health` → 200 `ok` (not `degraded`), `ocr_tesseract: available`, `ocr_paddleocr: disabled` | Owner, Render Dashboard (Workstream D §10) | PENDING |
| P5 | **Vercel frontend deployed** from branch `officerpath-phase2-web`, Root Directory `web`, four `NEXT_PUBLIC_*` Production variables set | Owner, Vercel Dashboard (Workstream E §8) | PENDING |
| P6 | **Canonical domain decided** and `NEXT_PUBLIC_SITE_URL` set to the real production origin (not the placeholder) | Owner decision (Workstream E §4) | REQUIRES OWNER APPROVAL |
| P7 | **Render `CORS_ALLOWED_ORIGINS`** set in the Dashboard to the exact production frontend origin | Owner, Render Dashboard (Workstream D §5.1) | PENDING (needs P6) |
| P8 | **Supabase redirect allowlist** includes the production callback URL (`https://<production-domain>/auth/callback`) **and** `http://localhost:3000/auth/callback` | Owner, Supabase Dashboard (Workstream C §8.3) | PENDING |
| P9 | **Test account ready** — a real registered account the owner will use on his phone (email confirmed; see §5 step 3). The unconfirmed M3 test user must be deleted, not used. | Owner | PENDING |
| P10 | **CI first run checked** (all six jobs green) — the deploy baseline is proven, not just pushed | Owner, GitHub Actions tab (Workstream B §7) | PENDING |
| P11 | **The three fixture files on the phone** — the exact files in §3, transferred to the phone (USB, Drive, or WhatsApp — any transfer that does not recompress the images; verify the PDF opens and the photos are the re-sent versions) | Owner | PENDING |

---

## 5. Phone procedure — one screen at a time

Read this whole section before starting. The owner runs it on his **real Android phone**, on the **live production URL** (from P6). Nothing here is done by any agent.

### Step 0 — Before opening the site

- Phone charged, stable internet (Wi-Fi or mobile data — the uploads are megabytes; a flaky connection looks like a failed upload).
- The three files from §3 are on the phone and open correctly (PDF opens in a viewer; both photos show the right pages).
- **Know the two timings in advance so they are not mistaken for failures:**
  - **Cold start:** Render free sleeps after 15 min without inbound traffic. The first request after sleep takes **~30–60 s** to wake. A slow first page load is the service waking, not a broken site — wait, do not tap repeatedly.
  - **PPSC-66 parse time:** ~20 min at Render free's 0.1 CPU. The upload itself is quick; the *job* is long. Use the async job model and poll — never wait on a sync call.

### Step 1 — Open the live site

- Chrome on the phone → the production URL.
- **Screenshot 1:** the home page, showing the tagline "Prepare Smarter. Practice Better. Become Exam Ready." and no console errors visible.
- If the page is slow to appear, wait up to a minute (cold start, Step 0). If it still does not load after a minute, stop and report the exact behaviour — do not proceed to login.

### Step 2 — Log in

- Go to `/login` and sign in with the test account from P9.
- If registering a new account instead: register → confirmation email arrives → tap the link → it lands on `/auth/callback` and then `/dashboard/profile`. (This also proves P8's allowlist entry works.)
- **Screenshot 2:** the dashboard after login, showing real values from the account (documents/jobs counts — no invented numbers).

### Step 3 — Upload file 1: PPSC-66 PDF

- Dashboard → Upload → file picker → select `ppsc_paper_66.pdf` → Upload.
- The JobTracker shows the job: queued → processing → done. **Poll; do not wait on a sync call.** Expect the job to take on the order of ~20 min.
- **Screenshots 3–5:** job at queued, job at processing, job at done (or the JobTracker state at each check).
- When the job is done, open the document detail page.
- **Screenshot 6:** the detail page with its counts (questions / answered / pending).
- **Record the numbers** in the §6 table (actual column): questions, answered, pending.

### Step 4 — Upload file 2: computer table photo

- Same flow as Step 3 with `table-computer-q67-81-resent-20261121.jpg`. Allow several minutes for the job.
- **Screenshot 7:** the detail page with its counts. Record the numbers in §6.

### Step 5 — Upload file 3: Paper 60 photo

- Same flow with `paper60-photo.jpg`. Allow several minutes for the job.
- **Screenshot 8:** the detail page with its counts. Record the numbers in §6.

### Step 6 — The re-upload rule (read before any second attempt)

- If a file was **already uploaded once**, uploading the SAME file again does **not** re-parse it: the M6 dedup returns the original job (`idempotent_replay: true`). That is correct behaviour, not a failure — but it means a re-test must first **delete the document** (dashboard delete → soft-delete), then re-upload. M10 proved this in its own setup.
- If a job **fails** (status `failed`, not just slow): record the exact error shown, screenshot it, and stop that file's test — do not retry blindly. A failed job is a finding, not something to hide by retrying.

### Step 7 — Smoke checks (same session, §8)

- Run the §8 checklist in the same phone session, while logged in. Screenshot anything that fails.

### Step 8 — Report back

- Send the parent agent: the three detail-page screenshots (6, 7, 8), the actual numbers for §6, and any failure screenshots from §8.
- The parent (not the owner) then verifies the **stored rows** for each document (via the API or the SQL Editor) and updates §6 and §7 of this report with the verified results. The owner's phone numbers and the stored rows must agree — that agreement is the pass.

---

## 6. Expected-results table — all PENDING

Fill in the **Actual** columns from the phone test (§5). **Expected** values are the M10 local baselines from §3 — VERIFIED locally, not live.

| File | Expected (questions / answered / pending) | Expected stored rows | Actual (questions / answered / pending) | Actual stored rows | UI == stored? | Verdict |
|---|---|---|---|---|---|---|
| `ppsc_paper_66.pdf` | **41 / 41 / 27** | 68 `extracted_questions` rows | — | — | — | PENDING |
| `table-computer-q67-81-resent-20261121.jpg` | **0 / 0 / 2** | — (no options) | — | — | — | PENDING |
| `paper60-photo.jpg` | **4 / 4 / 9** | — | — | — | — | PENDING |

**Overall phone acceptance:** PENDING — not complete until all three rows are PASS.

---

## 7. How to compare — what counts as a pass

- **Pass for one file:** the Actual UI counts match the Expected counts **exactly** (all three numbers), AND the stored rows match the Expected stored rows (where stated), AND the UI counts equal the stored counts (UI == stored, as M10 proved locally).
- **The stored-row check is the parent's job, not the owner's.** The owner records the phone UI numbers and screenshots; the parent verifies the database rows afterwards (API review endpoint or SQL Editor: count `extracted_questions` rows for the document, split by answered vs unknown). The owner cannot query the database from his phone, and must not be asked to.
- **On a mismatch:** do NOT mark the file complete. Record the actual numbers, keep the screenshots, and investigate — the mismatch itself is the finding. Common causes to check first:
  - A different file version was uploaded (the older table photo instead of the re-sent one; a re-compressed copy from a chat app).
  - The re-upload rule (§5 step 6): the numbers shown are from the dedup replay of an earlier upload, not a fresh parse.
  - A live-only failure (Render OOM at 512 MB — the 47 MB headroom in Workstream D; a Tesseract timeout at 0.1 CPU; a migration not yet applied — P1–P3).
  - A real engine difference between the local harness and the live server (different Tesseract version, missing language data, worker timeout).
- **A mismatch in any one file blocks the whole acceptance.** Two of three passing is not acceptance. The report stays PENDING and the failing file is re-tested only after its cause is found and fixed — with the fix recorded, not silently retried.

---

## 8. Smoke checks around the acceptance — all PENDING

Run in the same phone session as §5, after the three uploads. Each item is a checklist entry; all are PENDING until the phone test runs.

| # | Check | Expect | Status |
|---|---|---|---|
| S1 | Home page loads at the production URL | 200, tagline visible, no console errors | PENDING |
| S2 | `/login`, `/register`, `/pricing`, `/features` load | 200; `X-Robots-Tag: noindex, nofollow` on `/login` and `/register` | PENDING |
| S3 | `/dashboard` while logged out | 307 → `/login?next=/dashboard` | PENDING |
| S4 | Register a real account → confirmation email → click link | Lands on `/auth/callback`, then `/dashboard/profile` (proves the P8 allowlist entry) | PENDING |
| S5 | Dashboard loads after login | Real values from the database (documents/jobs counts for this account); upload page reachable | PENDING |
| S6 | Upload one file through the web upload | Job queued → done; counts shown on the detail page | PENDING |
| S7 | Create a test from the question bank (5 questions), take the exam, submit | Submit returns a result; result page shows the score (server-calculated, +1 / −0.25 / 0) | PENDING |
| S8 | Results page + mistake notebook | Result matches the stored row; mistakes listed; retry works from the original snapshot | PENDING |
| S9 | Notifications | A "job done" notification appears in-app after each upload completes | PENDING |
| S10 | No horizontal overflow at phone width | Pages scroll vertically only; no sideways scroll (M10 local baseline: 0 px overflow at 360 px) | PENDING |
| S11 | Forgot-password flow | Email arrives; reset link lands on `/auth/callback?type=recovery` and the reset page works | PENDING |
| S12 | API call from the production origin | Succeeds (proves the P7 CORS value is set); a preflight failure here means the Render value is missing, not a frontend bug | PENDING |

---

## 9. Beta rollout criteria

The **20–30 student free beta** may begin **only after all of the following are true**:

1. All three rows in §6 are PASS (phone acceptance complete — the STOP CONDITION met).
2. All §8 smoke checks are PASS (or any failure is recorded with its cause and an explicit owner decision to proceed anyway).
3. No prerequisite in §4 remains PENDING or BLOCKED.
4. The domain decision (P6) is settled and `NEXT_PUBLIC_SITE_URL` matches the live origin (canonical/OG/sitemap point at the real domain, not the placeholder).

**Until then the site stays unannounced.** No social post, no group share, no waitlist invite that points at the production URL — the beta is not announced on a hope.

**Hosting note for the beta (not a gate):** the free beta is non-commercial and fits Vercel Hobby (Workstream E §7). The **paid Phase 3 launch cannot stay on Hobby** (non-commercial term) — Pro ($20/seat/month) or another host must be decided before the commercial launch, not after it. That decision is Phase 3 work, not a beta blocker.

---

## 10. What this report does NOT claim

- **No live result is claimed anywhere in this report.** Every result cell is PENDING and every smoke check is PENDING. The only VERIFIED numbers are the M10 local baselines in §3, labelled as local.
- **No live check was run in this workstream.** No Render service, no Vercel project, no live Supabase query, no phone — this workstream read files only.
- **The phone test cannot be delegated.** No agent can run it; only the owner on his own phone can. If the owner cannot run it (no phone access, no time), acceptance stays BLOCKED — it is never waived by an agent.
- **A re-run of the local M10 harness is not a substitute.** Re-running the VM harness would only re-prove the local numbers. The STOP CONDITION is specifically about the live system on the owner's device.

---

## Appendix — evidence (files and commands read in this workstream)

- `git log --oneline -1` → head `1a7f868` (Workstream E), branch `officerpath-phase2-web`; `git status --short` → only the two untracked 018 files (by design, Workstream C)
- Read in full: `docs/deployment/01-repository-safety-audit.md`, `02-github-ci-report.md` (skimmed for gates), `03-supabase-migration-runbook.md` (§2 live state, §5 execution order), `04-render-backend-deployment.md` (§3 memory fit, §9 cold start, §10–§11 deploy + smoke), `05-vercel-frontend-deployment.md` (§8–§9 deploy + smoke, §4 domain, §7 Hobby)
- `docs/phase2/milestones/MILESTONE_10_REPORT.md` §4(b) — the three acceptance files via the web UI: PPSC-66 **41/41/27**, 68 rows, parse 224.3 s; table photo **0/0/2**; Paper 60 **4/4/9**; API sweep **17/17**; browser E2E **37/37**; walkthroughs 0 px overflow (desktop 15 pages, mobile 360 px 9 pages); final bank 123 live questions, 6 live documents, 15 test_results, 24 notifications
- `docs/phase2/deployment-checklists.md` §D (post-deploy smoke) and §E (known risks: 47 MB headroom, Dockerfile unbuilt, ~20 min PPSC-66 at 0.1 CPU, no alerting)
- `docs/PHASE_1_COMPLETION_REPORT.md` §7 — the STOP CONDITION as originally stated (live phone verification: PPSC-66 PDF, computer table photo, Paper 60 photo)
- Fixture provenance: `~/workspace/officerpath-ai/test-fixtures/ppsc66/PROVENANCE_2026-11-21.md` — PPSC-66 md5 `0cd49fed…`, Paper 60 (Infinix X6881, 2160×3840, star-marked answers), re-sent table photos (computer Q67–81, 1504×2674; interjection Q230–257, 1886×3354)
- Fixture presence confirmed: `ls ~/workspace/officerpath-ai/test-fixtures/ppsc66/` — `ppsc_paper_66.pdf`, `paper60-photo.jpg`, `table-computer-q67-81-resent-20261121.jpg` all present; repo copies in `app/tests/fixtures/ppsc66/` (page PNGs p-1–p-7, both table photos)

**Workstream F conclusion:** the acceptance plan is written and ready to execute, and nothing in it is yet executed. The STOP CONDITION stands: the three files must be proven on the owner's own Android phone through the live web upload, with UI counts and stored rows matching the M10 local baselines exactly (PPSC-66 41/41/27 with 68 stored rows; table photo 0/0/2; Paper 60 4/4/9). Eleven prerequisites (§4) must all be COMPLETED first — today, four of them are PENDING or BLOCKED (018, 017, Alembic, and the two deploys plus the domain decision). When the phone test runs, §6 and §8 of this report are filled in with the actual numbers and screenshots; until then they stay PENDING, and the beta stays unannounced.
