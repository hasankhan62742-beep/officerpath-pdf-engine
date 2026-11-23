# Phase 3 — Master Architecture

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Workstream:** H (Phase 3 architecture ONLY — design, no implementation)
**Date:** 2026-11-23 (PKT)
**Status:** Design only. Every Phase 3 feature in this document is PENDING implementation. Nothing here exists in code, and nothing here was tested.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** This document designs the commercial layer (plans, manual payments, activation codes, admin modules). It claims no implementation, no test result, and no live behaviour. Where it cites an existing fact (a table, an endpoint, a prior finding), the source is named. Where it makes a design decision, it is labelled as a decision with its rationale, so the owner can disagree before anything is built.

**Related documents (built on, not duplicated):** `docs/deployment/01-repository-safety-audit.md` … `docs/deployment/07-security-and-licensing-report.md`, `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `docs/phase2/01-repository-findings.md`, `docs/phase2/02-api-integration-map.md`, `docs/phase2/03-database-extension-plan.md`, `docs/phase2/05-security-architecture.md`, `docs/adr/ADR-001-hosting-baseline.md`, `docs/adr/ADR-003-persistence.md`, `docs/adr/ADR-011-dual-job-store-resolution.md`.

---

## 1. Goals and non-goals

**Goals:**
- Let a student pay for a plan with Easypaisa or JazzCash **manually** (the owner verifies the payment in his own wallet app and approves it) and get a working subscription with a server-enforced test limit.
- Let the owner sell access without being online at the moment of payment, via **single-use activation codes**.
- Give the admin a complete picture: students, subscriptions, payments, codes, usage, expiry, and a full audit trail.
- Add all of this **without breaking any existing Phase 1/2 contract** (upload → parse → bank → test → exam → results keeps working exactly as it does today).

**Non-goals (explicitly out of scope — see also §8):**
- No automated payment verification of any kind (no screenshot OCR, no wallet API, no scraping).
- No payment gateway, no card handling, no auto-renewal, no saved payment methods.
- No change to the free experience: the free tier keeps working exactly as it does in Phase 2 (3 tests, no payment step).
- No merge with the Flutter app's Supabase `profiles` table (see §2.4).

---

## 2. System overview

### 2.1 Where Phase 3 sits

```
Student (browser / phone)
  └─ Next.js web app (Vercel) ── NEXT_PUBLIC_API_URL ──► FastAPI engine (Render)
        │                                                     │
        │  /api/v1/plans        (new)                        │  engine DB (Postgres)
        │  /api/v1/payments     (new)                        │  plans, subscriptions,
        │  /api/v1/codes        (new)                        │  payment_transactions,
        │  /api/v1/admin/*      (extended)                   │  payment_proofs,
        │  /api/v1/tests        (existing — GATED, §4)       │  activation_codes,
        └──────────────────────────────────────────────────►│  activation_redemptions,
                                                             │  subscription_usage,
                                                             │  admin_roles, admin_users,
                                                             │  admin_audit_logs
                                                             │  notifications (reused, M9)

Money movement (OUTSIDE the system — never through the server):
Student ── Easypaisa / JazzCash wallet app ──► Owner's wallet
        (the server only records the claim + the proof;
         verification happens in the owner's wallet app)
```

The single most important architectural fact: **money never touches the server.** The server records a payment *claim* (transaction reference + proof), and the owner verifies the *money* in his own wallet app. There is no payment API, no webhook, and no credential for any wallet stored anywhere in the system. If a wallet changes its app, the flow still works — the student pays in the wallet app, the owner checks in the wallet app.

### 2.2 What changes, and what does not

| Area | Change |
|---|---|
| Engine DB | 10 new tables (see `PHASE3_DATABASE_DESIGN.md`); `notifications` CHECK constraint extended with payment types; nothing existing is dropped, renamed, or re-typed. |
| Engine API | New routers: plans, payments, codes, admin extensions. One existing behaviour changes: `POST /tests` (and `POST /tests/from-mistakes`) gains a server-side plan check before creating a session (§4). No other existing endpoint changes. |
| Web app | New pages: Pricing (now with real plans), Checkout/Payment instructions, My Subscription, Admin payment queue, Admin code generation, Admin usage analytics. Existing pages unchanged except the dashboard showing plan + usage. |
| Auth | Unchanged (Supabase Auth email+password, confirm-email gate). Admin stays `require_admin` (JWT `app_metadata.is_admin`); Phase 3 adds a **role layer on top** (§7), never a replacement. |
| Upload/parse/bank/exam/results | Unchanged. Phase 3 never touches the pipeline. |

### 2.3 The four plans (the authority — do not invent others)

| Plan | Price | Test limit | Duration | Who it is for |
|---|---|---|---|---|
| Free | Rs 0 | 3 tests (lifetime, see §4.3) | No expiry | Every account, by default |
| Monthly | Rs 600 | 20 tests | 30 days from activation | Regular preparation |
| Two Months | Rs 1,200 | 50 tests | 60 days from activation | Intensive preparation |
| Yearly | Rs 6,000 | Unlimited tests | 365 days from activation | Serious long-term aspirants |

- Prices are stored in **paisa (integer)** in the database (Rs 600 = 60000) — never floats. Display formatting is a frontend concern.
- Plans are **data rows** (`plans` table, seeded by migration), not code constants. The owner can edit a plan's price or limit in the admin panel; existing subscriptions are unaffected because each subscription **snapshots** the plan's name, price, and test limit at activation time.
- Durations count from **activation** (the moment the admin approves the payment or a code is redeemed), never from purchase or payment.

### 2.4 The Flutter `profiles` table — an explicit non-merge

The Flutter app has its own Supabase `profiles` table with `plan`, `premium_until`, and `is_admin`. The engine never writes it (Phase 2, doc 03 §2.1/§2.7). **Phase 3 does not change that.** Web subscriptions live in the engine DB (`subscriptions` table); the Flutter table stays the Flutter app's own data. A web subscription does **not** write `profiles.premium_until`, and a Flutter premium flag does **not** grant web tests. If the owner later wants one account across web + Flutter, that is a separate decision (data mapping + migration), not a silent Phase 3 copy. This is recorded here so nobody "fixes" it by merging the two during the build.

---

## 3. Plan enforcement (server-side only)

### 3.1 The rule

**The frontend never decides whether a student may create a test. The backend does, on every creation request, in the same database transaction that creates the test.**

Enforcement points (the only places a test session is created):

| Endpoint | Enforcement |
|---|---|
| `POST /api/v1/tests` (create_test) | Check active subscription + remaining tests **before** creating template/session/snapshots. If the limit is reached, return 402 with the plan name, tests used, tests allowed, and the upgrade link. Nothing is created. |
| `POST /api/v1/tests/from-mistakes` | Same check — a from-mistakes test is a new session and counts as a new test. |
| `POST /api/v1/tests/{test_id}/retry` | Same check — a retry creates a new session and counts as a new test. |
| Exam start / submit / save | **No check.** Once a session exists, it runs to completion. Cutting off a live exam would be worse than the abuse it prevents (§3.4). |

All other flows (upload, parse, bank browsing, corrections, collections, results viewing) are **not** gated by plan. A free student can upload and build a bank; the gate is only on *taking* tests. This is deliberate: the free tier must stay useful enough to convert, and the paywall sits exactly where the value is.

### 3.2 How the check works (atomic reserve)

1. Load the student's active subscription (status `active`, `ends_at` in the future), locking the row (`SELECT … FOR UPDATE`) so two simultaneous requests cannot both pass the limit.
2. If no active subscription exists, the student is on **Free**: limit = 3 lifetime tests.
3. Count the student's used tests for the current period from `subscription_usage` (free: lifetime count; paid: count within this subscription's period).
4. If `used >= limit` (and the plan is not unlimited), reject with 402.
5. Otherwise, in the **same transaction**, create the template + session + snapshots **and** increment the usage counter. Either everything commits or nothing does — a test is never created without being counted, and never counted without being created.

### 3.3 What counts as one test

- One **created test session** = one test consumed, regardless of whether the student starts it, finishes it, or abandons it. Creation freezes snapshots and is the billable action; counting at submit would let a student create unlimited tests and abandon them to dodge the limit.
- A retry is a new session → counts. A from-mistakes test is a new session → counts. A test created and never started still counts.
- The free limit is **3 tests per account, lifetime, never resetting**. (Design decision — the spec says "Free = 3 tests" with no period. Alternative considered: 3 per month. Lifetime was chosen because it is the simplest honest reading and the hardest to game; the owner may change it to monthly by editing the Free plan row, but that is a policy decision for the owner, not a silent build-time choice.)

### 3.4 Expiry and grace

- A subscription ends at `ends_at`. After that, new test creation is blocked (the student falls back to Free — which is already exhausted if they used their 3 free tests, so in practice they must renew).
- **Grace rule:** if a subscription expires while a session is `in_progress`, that session continues to submit normally. The expiry is enforced at creation time only, never mid-exam.
- Buying while a paid plan is still active is **rejected** with a clear message ("You already have an active plan until <date>"). The student buys again after expiry. This prevents double-charging confusion. (Alternative considered: queue the new plan to start at old expiry. Rejected for v1 as added complexity; the owner may revisit it.)
- Redeeming a code while a paid plan is active follows the same rule: rejected, and the code stays unused.

### 3.5 What the student sees

- Dashboard: current plan name, tests used / allowed, days left, and the upgrade path. All values come from the backend (`GET /api/v1/me/subscription`); the frontend displays them, never computes them.
- On a 402: the exact reason (limit reached), the plan that would fix it, and the payment flow entry point. No silent failure, no invented number.

---

## 4. Manual payment flow (end to end)

Full step-by-step procedure (student side, admin side, states, proof rules, fraud handling) is in `PHASE3_PAYMENT_WORKFLOW.md`. This section is the architecture summary.

```
Student selects plan
  → POST /payments → creates payment_transactions row (status: pending)
        + a unique reference (OP-XXXXXXXX) shown to the student
  → Student sees payment instructions (method, amount, receiving
        account, reference) and pays in the Easypaisa/JazzCash app
  → Student submits TID + proof file (POST /payments/{id}/proof)
        → status stays pending; admin queue gains one item
  → Admin opens the queue, checks TID + amount + date in the
        owner's OWN wallet app (the only verification that counts)
  → Admin approves → subscription activates (status: active,
        starts_at = now, ends_at = now + plan duration)
        + notification to the student + audit row
     OR admin rejects (reason required) → status: rejected (terminal)
        + notification to the student + audit row
     OR admin asks for clearer proof → status: info_needed
        → student resubmits → back to pending
```

- **States:** `pending` → `approved` | `rejected` | `info_needed`; `info_needed` → `pending`; `approved` and `rejected` are terminal. A rejected payment is never re-approved; the student starts a new transaction.
- **Pending transactions expire after 72 hours** without proof (status → `expired`, automatic by the daily sweep). The student starts a new transaction.
- **One TID, one approval:** a partial unique index on `(method, transaction_id) WHERE status = 'approved'` guarantees the same wallet transaction can never activate two subscriptions, even under race.
- **Full history is retained:** no payment row, proof, or audit row is ever deleted. A mistaken approval is corrected by a separate action (deactivate the subscription + audit row + notification), never by editing history.

## 5. Activation codes

- **Format:** `OP-XXXX-XXXX-XXXX` (16 characters from an unambiguous alphabet — no 0/O, 1/I/l). Generated with a CSPRNG (`secrets` module); the plaintext is shown to the admin **once**, at generation, and never stored — only its **SHA-256 hash** is stored (`code_hash`, unique index).
- **Properties:** plan-linked (the code buys exactly one plan), single-use (a partial unique index on `activation_redemptions.code_id WHERE status = 'redeemed'` guarantees it at the database level), expiring (`expires_at`, default 90 days from generation, settable by the admin), transaction-associated (a code may be linked to the payment transaction that funded it, or generated standalone by the admin for giveaways — both are recorded).
- **Redemption is atomic:** in one transaction — check the code (hash lookup, unused, unexpired, plan not already active for this student) → mark redeemed → create the redemption row → activate the subscription → notify → audit. Any failure rolls everything back.
- **Abuse controls:** rate limiting (5 failed attempts / 15 min per user, 10 / hour per code), every attempt logged (success and failure) in `activation_redemptions`, generic error messages (a wrong code and an already-used code return the same message, so the endpoint is not a code-existence oracle).
- **Admin generation:** bulk generation (e.g. 50 codes for a campaign) is one admin action producing one audit row per batch + one row per code; each code's plaintext is exported once (CSV download) and then never retrievable again.

## 6. Admin surface

New and extended admin modules (all under the existing `/api/v1/admin/*` router, all behind `require_admin` + the Phase 3 role check — see §7 and `PHASE3_SECURITY_PLAN.md`):

| Module | What it does |
|---|---|
| Students | List/search students (from `student_profiles` + Auth data the engine already holds), view a student's plan, usage, subscriptions, and payment history. |
| Subscriptions | List/active/expired subscriptions, deactivate a subscription (with reason + audit), view usage per subscription. |
| Payment approvals | The queue: pending transactions with proof, approve/reject/info-needed, the verification checklist, duplicate-TID warnings. |
| Code generation | Generate single or bulk codes, set plan + expiry, export plaintext once, list codes with status (unused/redeemed/expired/revoked), revoke an unused code. |
| Plans | View/edit plan price, test limit, duration, active flag. Edits never touch existing subscriptions (they snapshot at activation). |
| Usage analytics | Tests created per plan per day/week/month, conversion (free → paid), revenue per method (Easypaisa vs JazzCash), expiring-soon counts. All computed from the tables; no new analytics pipeline. |
| Transactions | Full payment history (every state, every proof, every admin decision) with filters. |
| Expiry monitoring | Subscriptions expiring in 7/3/1 days; the daily sweep sends the notifications and flips expired rows. |
| Notifications | The existing in-app notifications (reused); admin can send a manual notification to a student (e.g. payment clarification). |
| Admin roles | Assign/revoke roles (owner / finance / support — §7); owner-only. |
| Audit logs | Read-only view of `admin_audit_logs` (every admin action, with before/after). Append-only; no admin can edit or delete it. |

## 7. Admin roles (a layer, not a replacement)

The existing admin mechanism is a single boolean: `app_metadata.is_admin` in the Supabase JWT, enforced by `require_admin`. Phase 3 **does not replace it** — a role applies only to a user who already passes `require_admin`. The role refines what that admin may do:

| Role | May do |
|---|---|
| owner | Everything, including role assignment and plan edits. |
| finance | Approve/reject/info-needed on payments, generate codes, view transactions and subscriptions. Cannot assign roles, edit plans, or deactivate subscriptions. |
| support | View students/subscriptions/transactions, send notifications. Cannot approve payments, generate codes, or change anything financial. |

- Roles live in `admin_roles` (seeded) + `admin_users` (user_id → role_id). A user with `is_admin=true` but no role row is treated as **support** (least privilege) until the owner assigns a role.
- **Bootstrap:** the existing admin (the owner) self-assigns the `owner` role on first login to the admin panel after the Phase 3 deploy; the bootstrap is written to `admin_audit_logs`. No role is ever assigned by a non-owner.
- Role changes are themselves audited (who assigned what to whom, when).

## 8. Explicitly out of scope

1. **No automated payment verification.** No screenshot OCR, no wallet API, no scraping of any wallet or bank. The manual check in the owner's wallet app is the verification.
2. **No payment gateway integration** (Stripe, etc.) — not in this phase, not implied by any endpoint name.
3. **No auto-renewal, no saved payment methods, no card data.** No card number, CVV, or wallet PIN ever enters the system (and the API must reject any payload that contains one — see `PHASE3_SECURITY_PLAN.md`).
4. **No refunds automation.** Manual payments are non-refundable by policy; the remedy for a mistake is deactivation + audit, not a money-back flow.
5. **No device limits / account-sharing prevention in v1.** One paid account shared between students is not prevented by design in this phase; it is recorded as an accepted limitation (§9 of the security plan), not silently "solved".
6. **No change to the Flutter app.** The Flutter client keeps its own flow; web subscriptions do not appear in it.
7. **No price or plan changes without the owner.** Plan edits are an owner-only admin action, audited.

## 9. Dependencies on the deployment programme (what Phase 3 assumes)

Phase 3 is designed on top of the deployment state recorded in workstreams A–G. These are **not** Phase 3's job to fix, but the paid launch cannot happen until they are resolved:

| Dependency | Status (2026-11-23) | Phase 3 impact |
|---|---|---|
| `GET /tests/{test_id}` answer-key exposure (Workstream G) | FAILED — must be fixed before the beta | A paying student could read any in-progress test's key. **Blocks the beta, not just the paid launch.** |
| PyMuPDF AGPLv3 decision (Workstream G) | REQUIRES OWNER APPROVAL (keep+LICENSE / commercial licence / pypdfium2 / defer) | Blocks the **paid launch** (closed-source commercial service). The free beta may proceed once the LICENSE file exists (option A). |
| Render free memory: 47 MB headroom (Workstream D) | MARGINAL — VERIFIED | Phase 3 adds small tables + a few endpoints; negligible memory impact. The daily expiry sweep runs in the existing in-process worker (ADR-009) — no new service. If the free tier proves too tight, the Stage 2 VPS (ADR-001) is the answer, not a Phase 3 redesign. |
| Vercel Hobby is non-commercial only (Workstream E) | VERIFIED | The **paid launch cannot stay on Hobby** — Pro ($20/seat/mo) or another host before commercial launch. The free 20–30 student beta fits Hobby. |
| Domain decision (Workstream E) | REQUIRES OWNER APPROVAL | Payment instruction pages, CORS, and the Supabase redirect allowlist all depend on the final domain. |
| Supabase 017/018 + Alembic 0001–0009 live (Workstream C) | PENDING / BLOCKED | Phase 3 migrations (0010–0013) run **after** the Phase 2 migrations are live; the chain must be linear. |
| CI first run (Workstream B) | PENDING | Phase 3 adds tests; they must run in CI before any Phase 3 merge. |
| Phone acceptance (Workstream F) | PENDING | The STOP CONDITION continues: the owner proves the paid flow on his own phone before launch (see `PHASE3_TEST_PLAN.md` §9). |

## 10. Recommended rollout order

1. **Free beta first** (20–30 students, Free plan only) — after phone acceptance (Workstream F), the `get_test` fix, and the domain decision. No money moves.
2. **Paid plans open** — after the PyMuPDF decision, the hosting decision for the paid launch (Vercel Pro or another host), and a full phone end-to-end of the manual payment flow (owner pays himself Rs 600 and approves it — see test plan §9).
3. **Activation codes** — after the payment flow has run live for at least one real approval, so the code path is exercised against a working subscription system, not a theoretical one.

## 11. Open decisions (all REQUIRES OWNER APPROVAL)

| # | Decision | Design default in this document | Alternative |
|---|---|---|---|
| D1 | Free limit: lifetime 3 or 3/month? | Lifetime 3 per account (§3.3) | 3 per calendar month |
| D2 | Buying while a plan is active | Rejected with a message (§3.4) | Queue the new plan to start at old expiry |
| D3 | Pending transaction expiry | 72 hours (§4) | 24 / 48 hours, or no expiry |
| D4 | Code default expiry | 90 days from generation (§5) | 30 / 180 days, or no expiry |
| D5 | Payment receiving accounts | Easypaisa 03427717288, JazzCash 03060853742 (see payment workflow §1) | Changeable only by the owner, in the admin panel |
| D6 | PyMuPDF licence path | See Workstream G (A/B/C/D) | — |
| D7 | Paid-launch hosting | Vercel Pro or another host (§9) | Stay on Hobby (not permitted for commercial use) |
| D8 | Account sharing | Accepted limitation in v1 (§8.5) | Device/session limits in a later phase |

---

**Phase 3 master architecture conclusion:** the commercial layer is a thin, server-enforced addition on top of Phase 2: four plan rows, a manual payment claim + proof + approval flow in which money never touches the server, single-use hashed activation codes, and an admin surface built on the existing `require_admin` guard with a role layer on top. Nothing existing is rewritten; the free tier keeps working; the paid launch is gated on the deployment programme's open items (§9), not on Phase 3 design work.
