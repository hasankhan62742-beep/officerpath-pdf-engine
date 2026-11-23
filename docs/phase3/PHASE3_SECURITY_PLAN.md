# Phase 3 — Security Plan

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Workstream:** H (Phase 3 architecture ONLY — design, no implementation)
**Date:** 2026-11-23 (PKT)
**Status:** Design only. No control in this document has been implemented or tested. Every control below is PENDING.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** This plan is research and design, not a security audit of built code (nothing is built yet) and not legal advice. Where it cites an existing finding, the source workstream is named. Where it prescribes a control, the control is specified precisely enough to implement and test — but it does not exist until the build phase creates it.

**Related documents (built on, not duplicated):** `docs/phase3/PHASE3_MASTER_ARCHITECTURE.md`, `docs/phase3/PHASE3_DATABASE_DESIGN.md`, `docs/phase3/PHASE3_PAYMENT_WORKFLOW.md`, `docs/deployment/07-security-and-licensing-report.md` (the findings this plan carries forward), `docs/deployment/04-render-backend-deployment.md`, `docs/deployment/05-vercel-frontend-deployment.md`, `docs/phase2/05-security-architecture.md`.

---

## 1. Threat model

| # | Threat | Who benefits | Impact if it succeeds | Control (design) |
|---|---|---|---|---|
| T1 | **Activation-code guessing / brute force** — an attacker tries codes at random. | Free premium access. | Stolen plan value; codes meant for paying students get used by strangers. | §4: codes are 16 chars from a 32-char alphabet (~80 bits of entropy); only the SHA-256 hash is stored; generic error messages (no code-existence oracle); rate limits per user and per code; every attempt logged; single-use enforced by a partial unique index, not just by code. |
| T2 | **Payment-proof forgery** — a fake screenshot and a made-up TID. | Free premium access. | A subscription activated without payment. | §5: the screenshot is never the verification; approval requires the TID + amount + date to exist in the owner's own wallet app (§5 of the payment workflow). A forged screenshot cannot pass the wallet check. |
| T3 | **TID replay** — one real payment submitted by two accounts, or re-submitted after approval. | Two subscriptions for one payment. | Revenue loss. | §5: partial unique index on `(method, transaction_id) WHERE status = 'approved'`; the admin queue flags pending duplicates; the approval path re-checks the index inside the approval transaction. |
| T4 | **Plan-limit bypass** — a student calls the API directly, tampers with the frontend, or races two requests to create tests beyond the limit. | Unlimited free tests. | The paywall is meaningless. | §3: enforcement is server-side, in the same transaction as test creation, with a row lock on the subscription/usage row; the frontend's numbers are display-only; no limit is ever read from a client-supplied value. |
| T5 | **Test-key exposure** — a student reads the answer key of an in-progress test. | Cheating on paid (and free) tests. | Test results are meaningless; paying students are cheated out of a fair product. | §2.1: the Workstream G finding MUST be fixed before the beta (see below). |
| T6 | **Admin privilege abuse** — a finance admin approves their own fake payment, or a support admin escalates to owner. | Free access, or control of the system. | Direct revenue loss; loss of admin integrity. | §3.2: role separation (owner/finance/support); role assignment is owner-only; every admin action is written to `admin_audit_logs` with before/after; an admin cannot approve a payment submitted by their own account (self-approval is rejected in code). |
| T7 | **Account sharing** — one paid account used by many students. | Free premium access for the sharers. | Revenue loss. | Accepted limitation in v1 (§8): no device/session limits. Recorded honestly, not silently "solved". A later phase may add concurrent-session limits. |
| T8 | **Code / payment enumeration via error messages** — probing the API to learn whether a code or TID exists. | Information for T1/T3. | Turns blind guessing into targeted guessing. | §4: all redemption and payment errors return the same generic message to the caller; the specific reason lives only in the admin-side audit tables. |
| T9 | **Admin session / token theft** — a stolen admin JWT. | Full admin access. | Same as T6, without needing a role. | §3.1: JWTs are verified server-side via Supabase `auth.get_user` (the Phase 2 pattern — never decoded locally); admin routes 404 for non-admins (no existence leak); no admin credential is ever stored in the repo or the frontend. |
| T10 | **Proof-file abuse** — a student uploads malware or a huge file as "proof". | Storage abuse, or an attack on the admin's machine. | Storage exhaustion; a malicious file opened by an admin. | §6: proof files are images/PDF only (validated by magic bytes, the Phase 2 upload pattern), 10 MB cap, stored in the private `payment-proofs` bucket (never executed, never served inline with a content type the browser will run); the admin downloads them; the bucket has no public access. |
| T11 | **Plan tampering** — a student edits the price of the plan they are buying. | Cheaper premium access. | Revenue loss. | §3: plan prices are read from the `plans` table on the server at transaction creation; the client sends only the plan slug; the price is snapshotted server-side and never taken from the request. |
| T12 | **Notification spoofing** — a fake "payment approved" message. | Social engineering. | A student believes they are premium when they are not (or vice versa). | Notifications are created only by server-side flows in the same transaction as the event; the dashboard always shows the live subscription state from the backend, never from a notification. |

## 2. Prerequisites carried from Workstream G (not optional)

### 2.1 The `GET /tests/{test_id}` answer-key exposure — MUST be fixed before the beta

- **Finding (parent-verified in code, Workstream G):** `GET /tests/{test_id}` returns full snapshot items **with** `correct_index` + `answer_source` to the test owner with **no status guard** (`app/services/tests.py:816` → `_snapshot_dict:581`). The M9 exam-session fix is real (the exam endpoint withholds the key while `in_progress`, `app/services/exam.py:147–148`) — but `get_test` bypasses it. A student can fetch their own in-progress test's key with a deliberate API call (curl/devtools). The normal UI never calls it mid-test, so this is a cheating hole, not a data breach — but a paid product whose tests can be cheated by one API call is not a product.
- **Required fix (before the beta, not before the paid launch — the beta is already too late):** withhold `correct_index` and `answer_source` in `get_test` while the session status is `in_progress` (return them as `null` / omitted, the same way the exam endpoint does), plus a regression test that creates a session, starts it, calls `get_test`, and asserts no key is present — and then submits and asserts the key appears. The fix is a Phase 2 code change, not a Phase 3 feature; it is recorded here because Phase 3's paid tests inherit the hole if it is not fixed.
- **Status:** PENDING (audit only in Workstream G — not implemented). **Blocks the beta.**

### 2.2 The PyMuPDF AGPLv3 decision — MUST be made before the paid launch

- **Finding (Workstream G):** PyMuPDF 1.26.3, dual AGPLv3/commercial, used in 6 files for text extraction **and** page rendering; no `LICENSE` file in the repo (verified) — "public repo = compliant" is shaky; the only single-library alternative covering both roles is pypdfium2 (BSD/Apache), candidate only, needs a benchmark.
- **Options (owner decision):** A) keep PyMuPDF + add the AGPLv3 `LICENSE` file and a source offer ($0, cheapest honest path for the free beta); B) buy a commercial licence (quote first — Artifex publishes no prices); C) replace with pypdfium2 (dedicated migration milestone + re-benchmark); D) defer — allowed only while the service stays free and public.
- **Status:** REQUIRES OWNER APPROVAL. **Blocks the paid launch** (a closed-source commercial service on AGPLv3 without A/B/C is not a decision this plan can make).

## 3. Authentication and authorisation

### 3.1 What stays (Phase 2, VERIFIED)

- Supabase Auth email+password; confirm-email gate (M3 verified the gate works).
- JWT verified server-side via Supabase `auth.get_user` — never decoded locally, never logged, never stored.
- Admin via `app_metadata.is_admin` only, enforced by `require_admin`; non-admins get 404 on all admin routes (no existence leak).
- Every user-owned row carries `user_id`; every query filters by it; another user's rows 404 (never 403-with-existence).

### 3.2 What Phase 3 adds (roles)

- After `require_admin` passes, a second check reads the caller's role from `admin_users` (cached per request, never from the JWT — the JWT carries only the boolean). Endpoints declare the roles they accept; a role mismatch returns 404 (the same "does not exist" response as a non-admin, so roles are not enumerable).
- **Self-approval ban:** an admin cannot approve, reject, or info-needed a payment submitted by their own account, and cannot redeem a code they generated for themselves. The code rejects it with a generic error; the attempt is logged.
- **Role assignment is owner-only** and is itself audited (`role.assign`, with before/after). The owner role cannot be assigned by anyone except an existing owner; the bootstrap (first owner self-assignment) is a one-time logged event.
- **Least privilege default:** an admin with no role row is treated as `support`.

## 4. Activation-code controls

| Control | Specification |
|---|---|
| Entropy | 16 characters from a 32-character unambiguous alphabet (no 0/O, 1/I/l) → ~80 bits. Generated with `secrets.choice` (CSPRNG). |
| Storage | Only `SHA-256(code)` is stored (`code_hash`, unique). The plaintext is shown once at generation (and once in a bulk CSV export) and then unrecoverable — even the owner cannot retrieve it later. |
| Single-use | Partial unique index on `activation_redemptions.code_id WHERE status = 'redeemed'` + the redemption transaction checks-then-inserts atomically. Two simultaneous redemptions of the same code: one wins, one fails with the generic message. |
| Expiry | `expires_at` (default generation + 90 days). The daily sweep flips expired unused codes to `expired`. An expired code is indistinguishable from a wrong code to the caller. |
| Revocation | An admin (finance or owner) may revoke an **unused** code (`status → revoked`, reason required, audited). A redeemed code cannot be revoked — the subscription it created must be deactivated instead. |
| Rate limiting | 5 failed attempts / 15 min per user; 10 failed attempts / 1 hour per code hash; 20 code-generation requests / hour per admin. Limits use the existing in-memory limiter (see §7). |
| Attempt logging | Every attempt (success and failure) is a row in `activation_redemptions` with the failure reason; failures are also visible in the admin code view. |
| Error messages | One generic message for all redemption failures: "This code is not valid, or has already been used." No distinction between wrong / used / expired / revoked is ever returned to the caller. |

## 5. Payment controls

| Control | Specification |
|---|---|
| No money through the server | The server stores claims and proofs only. No wallet credential, no payment API key, no webhook secret exists anywhere in the system. |
| Amount integrity | The amount is read from the `plans` table server-side at transaction creation; the client sends only the plan slug and method. The approval checklist requires the wallet amount to equal the plan price exactly. |
| TID uniqueness | Partial unique index on `(method, transaction_id) WHERE status = 'approved'`; the admin queue warns on pending duplicates. |
| Proof validation | Magic-byte validation (the Phase 2 upload pattern), JPG/PNG/PDF only, 10 MB cap, private bucket, never served inline. |
| Approval is human | No endpoint, job, or script can approve a payment except the admin's explicit API call. There is no auto-approve path, no threshold, and no "trusted student" shortcut. |
| Approval atomicity | Approval activates the subscription, writes the notification, and writes the audit row in one transaction. A failure anywhere rolls everything back — no half-activated subscription. |
| History is append-only | No payment row, proof, or audit row is ever edited or deleted. Mistakes are corrected by new rows (deactivation + audit). |

## 6. Data protection

- **No card data, no wallet PINs, no CVVs — ever.** The API must reject any payment payload containing card-like fields (a validator that returns 422 on `card_number`, `cvv`, `pin`, `otp`, or a 16-digit number in a free-text field). This is a deliberate tripwire: if a future frontend ever tries to collect card data, the backend refuses it.
- **TIDs** are transaction references, not secrets; visible to the owning student and to admins only.
- **Proof files** live in the private `payment-proofs` bucket (per-user policies: users upload/view their own, admins view all — the 016 pattern). No public access, no signed URL without an ownership check.
- **PII minimised:** the payment flow needs no new personal data beyond `student_profiles`. The student's phone (if on the profile) appears in the admin queue for reference only.
- **Audit rows are never edited or deleted** (`admin_audit_logs`, `audit_log`, `activation_redemptions`, proof history). Corrections happen by new rows.
- **Secrets:** no new secrets are introduced by Phase 3. The four Render secrets and the four Vercel variables are unchanged; no wallet credential is ever added to either.

## 7. Rate limiting (new endpoints)

The existing in-memory per-process limiter (`app/security/rate_limit.py`, sliding window) is reused — the same documented limitation applies: state lives in one process, which is acceptable on the single Render free instance (ADR-001) and requires a distributed limiter (e.g. Redis) if the backend ever runs more than one replica.

| Endpoint | Limit |
|---|---|
| `POST /api/v1/codes/redeem` | 5 failed attempts / 15 min per user; 10 / 1 hour per code |
| `POST /api/v1/payments` (create) | 10 / 1 hour per user (prevents queue spam) |
| `POST /api/v1/payments/{id}/proof` | 5 submissions / 1 hour per transaction |
| `POST /api/v1/admin/payments/{id}/approve` (and reject / info-needed) | 60 / 1 hour per admin (generous — the limit is abuse protection, not a workflow throttle) |
| `POST /api/v1/admin/codes` (generate) | 20 / 1 hour per admin |
| `POST /api/v1/tests` (create) | Unchanged from Phase 2 — but note the Workstream G finding that exam save/submit currently have **no** rate limiting; the build phase should extend the limiter to the exam endpoints alongside Phase 3, since paid tests raise the abuse incentive. |

Rate-limit responses are 429 with a retry message; repeated triggering is visible in the admin audit view (the limiter's rejections are logged, not silent).

## 8. Accepted limitations (recorded, not hidden)

1. **Account sharing is not prevented in v1.** One paid account can be shared between students (same login, many people). No device limit, no concurrent-session limit. The cost is bounded (the test limit is per account, so sharing splits the same 20/50 tests), and the owner may add session limits in a later phase. This is a deliberate v1 trade-off, not an oversight.
2. **Manual review is the bottleneck.** Approval speed depends on the owner being available. The instructions page must say so honestly ("usually within 24 hours"). There is no SLA in v1.
3. **The in-memory rate limiter does not survive a restart and does not span replicas.** Acceptable on the single free instance; a Redis-backed limiter is a Stage 2 (VPS) decision.
4. **No automated fraud detection.** Suspicious patterns are visible to the admin (attempt history, duplicate warnings) but nothing auto-bans. Banning is an owner decision, recorded in the audit log.
5. **The AGPLv3 question (§2.2) is unresolved until the owner decides.** This plan does not resolve it.

## 9. Incident handling (design)

| Situation | Response |
|---|---|
| Suspected code abuse (many failed attempts on one code) | The code's attempt history is in `activation_redemptions`; the admin revokes the code if unused, or deactivates the subscription it created. No automatic action. |
| Suspected payment fraud (a TID that looks reused, a forged proof) | Reject the transaction with the reason; if a subscription was already activated, deactivate it with the reason and notify the student. All steps are audit rows. |
| Admin account compromised | The owner revokes the admin's role (owner-only action) and, if needed, removes `is_admin` in the Supabase Dashboard (the JWT flag is the outer gate). The audit log shows everything that admin did. |
| Subscription wrongly activated | Deactivate with reason + audit + notification (the correction-by-new-row rule). The payment row is not edited. |
| Data leak (proof files exposed) | The bucket is private with per-user policies; exposure would require a policy or key failure. Response: rotate the service-role key, review the bucket policies, notify affected students, record the incident in `admin_audit_logs`. (No such incident has occurred; this is a plan, not a report.) |
