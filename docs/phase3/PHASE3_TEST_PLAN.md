# Phase 3 — Test Plan

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Workstream:** H (Phase 3 architecture ONLY — design, no implementation)
**Date:** 2026-11-23 (PKT)
**Status:** Design only. No test in this document has been written or run. Every scenario below is PENDING.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** This plan describes how Phase 3 *will* be tested when it is built. It claims no test result. The acceptance criteria in §8 are all PENDING, and the phone verification in §9 has not happened. A scenario listed here is a requirement, not a pass.

**Related documents (built on, not duplicated):** `docs/phase3/PHASE3_MASTER_ARCHITECTURE.md`, `docs/phase3/PHASE3_DATABASE_DESIGN.md`, `docs/phase3/PHASE3_PAYMENT_WORKFLOW.md`, `docs/phase3/PHASE3_SECURITY_PLAN.md`, `docs/deployment/06-live-acceptance-report.md` (the STOP CONDITION pattern this plan continues), `docs/deployment/02-github-ci-report.md` (the CI gates Phase 3 tests must pass).

---

## 1. Test levels and where they run

| Level | What it covers | Where it runs |
|---|---|---|
| Unit | Plan-limit arithmetic (used vs allowed, expiry math, unlimited handling), code generation format + hashing, reference generation uniqueness, state-machine transitions (illegal transitions rejected), money formatting (paisa ↔ Rs). | pytest, SQLite (CI). No live service, no wallet. |
| Integration (API) | Every new endpoint against the real service layer with a test database: plan check on test creation, payment create/proof/approve/reject/info-needed, code generate/redeem, admin role checks, notification creation, audit rows. | pytest, SQLite in CI; the same suite against a Postgres instance before any deploy (the Phase 2 rule — SQLite-only is not proof for Postgres-only features like partial unique indexes). |
| Concurrency | Two simultaneous test creations at the limit (one must win, one must get 402); two simultaneous redemptions of the same code (one must win); two approvals of the same TID (one must win). These **must** run on Postgres — SQLite's locking does not prove the row-lock behaviour. | Postgres pre-deploy suite. |
| E2E (browser) | The student journey in the web UI: Pricing → instructions → proof submission → waiting state → activated dashboard; the admin journey: queue → checklist → approve → student sees the plan. | The M10 browser harness pattern (local build) + the owner's phone after deploy (§9). |
| Manual acceptance (phone) | The full paid flow on the owner's real Android phone (§9). | Owner's phone, live deploy. |

**Test data rule:** no real wallet transaction is ever used in an automated test. All payment tests use fabricated TIDs (e.g. `TEST-…`) against the service layer; the only real money movement in the whole programme is the owner's own phone acceptance (§9), with his explicit go-ahead.

## 2. Plan-limit scenarios

| # | Scenario | Expected |
|---|---|---|
| P1 | Free student (no subscription) creates tests 1, 2, 3. | All three succeed; usage = 3. |
| P2 | Same student creates a 4th test. | 402, plan = free, used = 3, allowed = 3, upgrade link present. **Nothing is created** (no template, no session, no snapshots). |
| P3 | Monthly student (20 tests) creates a 20th test. | Succeeds; usage = 20. |
| P4 | Same student creates a 21st test. | 402 with the Monthly figures. |
| P5 | Yearly student (unlimited) creates a 100th test. | Succeeds; usage counter still increments (analytics), no limit check applied. |
| P6 | Monthly student retries a test (new session). | Counts as a new test (usage +1). |
| P7 | Monthly student creates a from-mistakes test. | Counts as a new test (usage +1). |
| P8 | Student creates a test, never starts it, creates another. | Both count (usage +2). Abandoned tests are not refunded. |
| P9 | Two simultaneous creations at the limit (Monthly, usage = 19). | Exactly one succeeds; the other gets 402; usage ends at 20, never 21. (Postgres only.) |
| P10 | Free student's 3 tests were created **before** the Phase 3 deploy. | Usage starts at 0 after deploy (no retroactive counting — database design §6). The student gets 3 fresh tests. |
| P11 | Subscription expires mid-test (session `in_progress`). | The session submits normally (grace rule); the result is stored; the **next** creation is blocked. |
| P12 | Student buys while a plan is active. | Rejected with a clear message naming the current plan and its end date; no second subscription, no second charge. |
| P13 | Expired subscription, student creates a test. | Falls back to Free: if free tests remain (they will not, for a paying student who used them — but the logic must still be tested with a fresh account), allowed; otherwise 402. |

## 3. Payment-flow scenarios

| # | Scenario | Expected |
|---|---|---|
| M1 | Student selects Monthly + Easypaisa. | Transaction created: status `pending`, unique reference, amount 60000 paisa, `expires_at` = now + 72 h. Instructions show the exact amount and the receiving account. |
| M2 | Student submits proof (TID + amount + date + screenshot). | Proof row created; transaction stays `pending`; admin queue gains one item; admin gets a `payment_received` notification. |
| M3 | Admin approves with the checklist ticked. | Subscription activates (status `active`, `starts_at` = now, `ends_at` = now + 30 days, snapshots correct); student notified (`payment_approved` + `subscription_activated`); audit row written; all in one transaction. |
| M4 | Admin rejects (wrong amount). | Status `rejected`, reason stored, student notified with the reason; no subscription; the row stays in history. |
| M5 | Admin asks for clearer proof. | Status `info_needed`, student notified with the exact message; student resubmits → status back to `pending`; old proof retained with `is_current = false`. |
| M6 | Rejected transaction, admin tries to approve it. | Rejected (terminal) — the API refuses; the student must start a new transaction. |
| M7 | Pending transaction, no proof for 72 hours. | Daily sweep sets status `expired`; student notified (or sees it on the payments page); a new transaction is required. |
| M8 | Same TID submitted on two transactions; admin approves the first. | Second approval is refused by the database (partial unique index) and by the service; the second transaction is rejected as `duplicate_tid`. |
| M9 | Student pays Rs 500 for a Rs 600 plan and submits proof. | Admin checklist fails on amount; rejected with `amount_mismatch`. No subscription. |
| M10 | Student pays Rs 600 but submits the TID of a payment made last month. | Admin checklist fails on date; rejected (the TID belongs to an old transaction). |
| M11 | Student uploads a 20 MB proof file. | Rejected by validation (10 MB cap) before any row is written. |
| M12 | Student uploads an `.exe` as "proof". | Rejected by magic-byte validation (images/PDF only). |
| M13 | Admin approves, then realises it was a mistake. | Deactivate subscription (reason required) + audit row + notification; the approved transaction row is **not** edited. |
| M14 | Admin tries to approve their own payment. | Rejected by the self-approval ban; the attempt is logged. |

## 4. Activation-code scenarios

| # | Scenario | Expected |
|---|---|---|
| C1 | Admin generates one code for Monthly. | Code row created with `code_hash` (never the plaintext), status `unused`, `expires_at` = +90 days; plaintext shown once. |
| C2 | Admin generates 50 codes in one bulk action. | 50 rows, one `batch_id`, one audit row for the batch; CSV export contains each plaintext once. |
| C3 | Student redeems a valid unused code. | Atomic: code → `redeemed`, redemption row, subscription activated, notification, audit row — all or nothing. |
| C4 | Same code redeemed twice (second attempt, same or different student). | Second attempt fails with the **generic** message; the code stays redeemed to the first student; a `failed` redemption row is recorded. |
| C5 | Two simultaneous redemptions of the same code. | Exactly one succeeds (partial unique index). (Postgres only.) |
| C6 | Student redeems an expired code. | Fails with the generic message; a `failed` row records `expired`. |
| C7 | Student redeems a revoked code. | Fails with the generic message; a `failed` row records `revoked`. |
| C8 | Student redeems a code while their paid plan is active. | Fails; the code stays unused (the student may use it after expiry). |
| C9 | Student guesses codes rapidly (6 wrong attempts in 15 min). | 6th attempt gets 429 (rate limit); the attempts are logged. |
| C10 | Admin revokes an unused code. | Status `revoked`, reason required, audited; redemption afterwards fails with the generic message. |
| C11 | Admin tries to revoke a redeemed code. | Refused — the subscription must be deactivated instead. |
| C12 | Code generated for Monthly is redeemed; the subscription shows Monthly limits. | Snapshot correct (20 tests, 30 days from redemption). |
| C13 | The stored code value is checked directly in the database. | Only the hash is present — no plaintext anywhere in any table. |

## 5. Expiry scenarios

| # | Scenario | Expected |
|---|---|---|
| E1 | Subscription ends in 7 days. | Daily sweep sends `subscription_expiring` (7-day notice). |
| E2 | Subscription ends in 3 days, then 1 day. | Both notices sent (no duplicates — the sweep records which notices were sent). |
| E3 | Subscription passes `ends_at` with no renewal. | Daily sweep flips status to `expired`, sends `subscription_expired`, student falls back to Free. |
| E4 | Expiring-soon list in the admin panel. | Shows subscriptions expiring in 7/3/1 days with correct counts. |
| E5 | A test created before expiry is submitted after expiry. | Submits normally (grace rule, §2 P11). |

## 6. Admin scenarios

| # | Scenario | Expected |
|---|---|---|
| A1 | Support admin opens the payment queue. | 404 (support cannot approve payments — and the 404 does not reveal that the endpoint exists). |
| A2 | Finance admin approves a payment. | Succeeds; audit row records the finance role. |
| A3 | Finance admin tries to assign a role. | 404 (owner-only). |
| A4 | Owner assigns `finance` to a user. | Succeeds; audit row records before/after; the user can now approve payments. |
| A5 | Non-admin user calls any `/admin/*` endpoint. | 404 (the Phase 2 pattern — no existence leak). |
| A6 | Admin with `is_admin=true` but no role row. | Treated as `support` (least privilege). |
| A7 | Owner edits the Monthly price (Rs 600 → Rs 700). | The plan row changes; **existing** Monthly subscriptions keep Rs 600 in their snapshots; new transactions use Rs 700. The edit is audited with before/after. |
| A8 | Owner deactivates a plan (`is_active = false`). | New purchases of that plan are refused; existing subscriptions run to expiry. |
| A9 | Usage analytics: tests per plan per day. | Numbers match the `subscription_usage` + `test_sessions` tables exactly (computed, never invented). |

## 7. Regression (what must not break)

- The full existing suite stays green (613 tests in M10, parent-verified — the build phase re-runs it and the count must not drop; new Phase 3 tests are **added**, existing tests are not weakened to pass).
- The `GET /tests/{test_id}` fix from the security plan §2.1 ships with its own regression test (key absent while `in_progress`, present after submit) — and the existing test suite must still pass around it.
- The Phase 2 contracts are unchanged: upload → parse → bank → test → exam → results produces the same results on the same fixtures (PPSC-66 41/41/27, table photo 0/0/2, Paper 60 4/4/9 — the M10 baselines).
- CI gates (pytest, ruff, mypy, tsc, lint, build, pip-audit, detect-secrets, Alembic up/down) all pass before any Phase 3 merge — the same bar as Workstream B.
- `npm audit` is run on the owner's machine before the paid launch (the standing owner step from Workstreams B and G).

## 8. Acceptance criteria (all PENDING)

| # | Criterion | Status |
|---|---|---|
| AC1 | All scenarios in §2–§6 pass on Postgres (not SQLite-only) before merge. | PENDING |
| AC2 | Concurrency scenarios (P9, C5, M8) pass on Postgres. | PENDING |
| AC3 | No existing test regresses; the suite count only grows. | PENDING |
| AC4 | CI is green on the Phase 3 branch (including the first GitHub Actions run). | PENDING |
| AC5 | The `get_test` key-exposure fix is merged with its regression test. | PENDING |
| AC6 | The PyMuPDF licence decision is recorded (A/B/C) and implemented if it is A or C. | PENDING |
| AC7 | The paid-launch hosting decision is made (Vercel Pro or another host — Hobby is not permitted for commercial use). | PENDING |
| AC8 | Phone acceptance (§9) passes on the owner's own phone. | PENDING |
| AC9 | No Phase 3 feature is claimed done without the evidence in §8's table filled in with real results. | PENDING |

## 9. Phone verification before launch (the STOP CONDITION continues)

The Workstream F rule continues into Phase 3: **no launch is "done" until the owner's own phone proves it.** The phone acceptance procedure for Phase 3 (to be executed after deploy, with the owner's explicit go-ahead at the time — it moves real money, even though it is the owner paying himself):

1. **Buy a Monthly plan on the phone** — the owner, on his real Android phone, selects Monthly (Rs 600), chooses Easypaisa, receives the instructions, pays Rs 600 from his own wallet to the receiving account (03427717288), and submits the TID + screenshot through the web UI. (The money moves from one of his accounts to his own receiving account; it is a real-money test of the real flow, and it needs his go-ahead at the time.)
2. **Approve it in the admin panel on the phone** — the owner opens the admin payment queue on the same phone, runs the §5 checklist in his wallet app, and approves. The dashboard must then show Monthly, 0/20 tests used, and the correct end date.
3. **Use one test** — the owner creates and takes one test on the phone; usage must show 1/20.
4. **Redeem a code on the phone** — the owner generates a Yearly code in the admin panel, then (on a second account, or after the Monthly subscription is deactivated by hand) redeems it on the phone and verifies the Yearly plan activates with unlimited tests.
5. **Check the limits on the phone** — with a free account, create 3 tests, then confirm the 4th is refused with the 402 message and the upgrade link.

Each step is recorded with the actual numbers and screenshots in `docs/deployment/06-live-acceptance-report.md` (extended for Phase 3) — and until all five pass, the paid launch stays unannounced. A local harness run is not a substitute for any of these steps.
