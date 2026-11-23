# Phase 3 — Payment Workflow (Easypaisa / JazzCash, manual)

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Workstream:** H (Phase 3 architecture ONLY — design, no implementation)
**Date:** 2026-11-23 (PKT)
**Status:** Design only. No endpoint, page, or flow in this document exists yet. Every step below is PENDING implementation.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** This is the complete manual payment procedure. It claims no automation: there is no screenshot verification, no wallet API, and no scraping anywhere in it. The only verification is the owner checking the transaction in his own wallet app. If any step below sounds automatic, re-read it — it is not.

**Related documents (built on, not duplicated):** `docs/phase3/PHASE3_MASTER_ARCHITECTURE.md` (§4), `docs/phase3/PHASE3_DATABASE_DESIGN.md` (§2.3–2.4), `docs/phase3/PHASE3_SECURITY_PLAN.md`, `docs/phase2/PHASE_2_COMPLETION_REPORT.md`.

---

## 1. Actors and receiving accounts

| Actor | Role |
|---|---|
| Student | Selects a plan, pays in the wallet app, submits the TID + proof, waits for approval. |
| Owner / admin (finance role or owner) | Reviews the queue, verifies each payment in the wallet app, approves/rejects/asks for clearer proof. |
| System (engine) | Records claims, proofs, decisions, and history. It never moves money and never verifies money. |

**Receiving accounts (owner-confirmed — changeable only by the owner, in the admin panel; never hardcoded by an agent):**

| Method | Receiving account |
|---|---|
| Easypaisa | **03427717288** |
| JazzCash | **03060853742** |

- The student pays **to** one of these numbers from their own Easypaisa/JazzCash app. The numbers are the owner's public payment-receiving accounts (the same numbers a customer is given when paying by hand); they are not secrets and are shown on the payment instructions page.
- The plan prices (master architecture §2.3): Monthly Rs 600, Two Months Rs 1,200, Yearly Rs 6,000. The student must pay the **exact** amount for the chosen plan — no partial payments, no overpayments accepted (see §6).

## 2. Transaction states

```
                    ┌──────────────┐
                    │   pending    │  created when the student selects
                    │              │  a plan (no money has moved yet)
                    └──────┬───────┘
           ┌───────────────┼────────────────┐
           │ proof         │ admin          │ 72 h without
           │ submitted     │ decision       │ proof (sweep)
           ▼               ▼                ▼
   (stays pending)   approved ──► subscription active
                     rejected ──► terminal (new transaction to retry)
                     info_needed ──► student resubmits ──► pending
                                                        expired (terminal)
```

| State | Meaning | Terminal? |
|---|---|---|
| `pending` | Transaction created; waiting for the student's proof, or proof submitted and waiting for admin review. | No |
| `info_needed` | Admin asked for clearer proof. The student resubmits; the row returns to `pending`. | No |
| `approved` | Admin verified the payment in the wallet app. A subscription was activated in the same transaction. | **Yes** |
| `rejected` | Admin verified the payment does **not** match (wrong amount, no such TID, wrong account, duplicate). Reason required. | **Yes** — the student starts a new transaction to try again; a rejected row is never re-approved. |
| `expired` | 72 hours passed with no proof submitted (set by the daily sweep). | **Yes** — the student starts a new transaction. |

## 3. Student flow (step by step)

1. **Choose a plan** — Pricing page shows the four plans with price, test limit, and duration. The student picks one (Monthly / Two Months / Yearly; Free needs no payment).
2. **Choose a method** — Easypaisa or JazzCash. `POST /api/v1/payments` creates a `payment_transactions` row: status `pending`, a unique reference (e.g. `OP-7K2Q9X4M`), `expires_at` = now + 72 hours. Nothing is charged; no money has moved.
3. **See the instructions** — one screen, exact and complete: method, **exact amount**, receiving account number (from §1), the unique reference, and what to do next. The screen also says plainly: "Pay from your Easypaisa/JazzCash app, then come back here and submit the transaction ID and a screenshot. Your plan activates after the admin checks the payment — usually within 24 hours."
4. **Pay in the wallet app** — the student opens Easypaisa/JazzCash on their own phone, sends the exact amount to the receiving number, and notes the **transaction ID (TID)** from the confirmation screen. (If the wallet app lets them add a note, they may put the reference `OP-…` in it — helpful, not required, because the reference is matched on the proof submission, not in the wallet.)
5. **Submit the proof** — `POST /api/v1/payments/{id}/proof` with: the TID (required, exact as shown by the wallet), the amount paid (required), the date/time paid (required), and a proof file (required: screenshot JPG/PNG or PDF, max 10 MB, stored in the `payment-proofs` bucket). Optional: a short note. The transaction stays `pending`; the student sees "Submitted — waiting for admin review."
6. **Wait** — the student can check the status on the My Subscription / Payments page at any time. If the admin asks for clearer proof (`info_needed`), the student sees exactly what was asked for and resubmits (the old proof stays in history; the new one becomes current).
7. **Activated** — on approval the student gets an in-app notification (`subscription_activated`) and the dashboard shows the plan, tests used/allowed, and days left. The subscription starts at the approval moment, not at the payment moment.

## 4. Admin review flow (step by step)

1. **Open the queue** — Admin → Payment approvals lists `pending` transactions, oldest first, with plan, amount, method, reference, TID, proof thumbnail, and any duplicate-TID warning (see §6).
2. **Verify in the wallet app** — the admin opens the **owner's own Easypaisa/JazzCash app** and checks the three things that matter (the checklist in §5). The screenshot is supporting evidence only; it is **never** the verification.
3. **Decide** — one of:
   - **Approve** (`POST /api/v1/admin/payments/{id}/approve`): activates the subscription in the same transaction (subscription row + usage window + notification + audit row). The approval is atomic — either everything commits or nothing does.
   - **Reject** (`…/reject`, reason required): the student is notified with the reason and must start a new transaction. The row stays in history.
   - **Ask for clearer proof** (`…/info-needed`, message required): the student is notified with the exact request and resubmits.
4. **Done** — the queue item leaves the pending list. The full history (transaction, proofs, decision, admin, time) remains in Transactions forever.

## 5. The admin approval checklist (exact — no approval without it)

Every approval must pass **all** of these, checked in the owner's own wallet app:

- [ ] **TID exists** — the transaction ID the student submitted appears in the wallet app's history for the receiving account.
- [ ] **Amount matches exactly** — the wallet amount equals the plan price (Rs 600 / 1,200 / 6,000). A different amount is a rejection, not an approval with a note.
- [ ] **Date is plausible** — the wallet transaction date is on or after the transaction's creation time and within the 72-hour window (a TID from last month does not approve today's purchase).
- [ ] **Method matches** — the wallet transaction is on the method the student selected (Easypaisa TID in the Easypaisa app, JazzCash TID in JazzCash).
- [ ] **TID not already used** — the system flags it if the TID already approved another transaction (the partial unique index in the database also blocks it); if flagged, reject and investigate.
- [ ] **Receiving account is ours** — the wallet transaction's recipient is the §1 account for that method (a payment sent to a wrong number is not our payment).

If any box cannot be ticked, the admin does **not** approve. The options are: ask for clearer proof (if the TID is unreadable) or reject with the reason (if the payment does not match).

## 6. Duplicates, wrong amounts, and fraud handling

| Situation | Handling |
|---|---|
| Same TID submitted twice while the first is still pending | The second submission is accepted (the student may have double-tapped) but the admin queue shows a **duplicate-TID warning**; only one can ever be approved (the unique index on approved TIDs). |
| Same TID already approved once | The system refuses a second approval at the database level (partial unique index). The admin rejects the duplicate with reason `duplicate_tid`. |
| Amount paid ≠ plan price (underpaid) | Reject with reason `amount_mismatch`. The student must pay the exact amount in a new transaction. The underpayment is not topped up and not refunded by the system (the owner may refund by hand outside the system if he chooses; that is recorded as an admin note, not a system flow). |
| Amount paid > plan price (overpaid) | Reject with reason `amount_mismatch` (same rule — exact amounts only). The owner may choose to approve by hand after contacting the student; if so, the approval records the overpayment in the review note and the subscription still activates at the plan price (no credit is carried forward). |
| TID does not exist in the wallet app | Reject with reason `tid_not_found`. |
| Proof screenshot is unreadable / cropped / wrong file | `info_needed` with a specific message ("Please upload a clear screenshot showing the transaction ID and amount"). Do not reject for a bad screenshot alone — the wallet check is what matters. |
| Student paid to the wrong number | Reject with reason `wrong_recipient`. The money went elsewhere; the system cannot recover it. |
| Pending transaction with no proof after 72 hours | Daily sweep sets status `expired`. The student starts a new transaction. |
| Admin approves by mistake | The approval is corrected by a **separate action**: deactivate the subscription (reason required) + audit row + notification to the student. The approved transaction row is **not** edited or deleted — history is append-only. |
| Suspicious pattern (many failed proofs, many codes, rapid redemptions) | Rate limits (§6 of the security plan) slow it down; the admin sees the attempt history and may deactivate the account's subscriptions. There is no automatic account ban in v1 — banning is an owner decision, recorded in the audit log. |

## 7. Notifications at each step

All in-app only (the Phase 2 rule — no email is claimed sent). Types are the extended set from the database design §3.

| Event | Recipient | Type | When |
|---|---|---|---|
| Proof submitted | Admins (finance + owner) | `payment_received` | Student submits TID + proof. The queue gains an item. |
| Admin asks for clearer proof | Student | `payment_info_needed` | Includes the admin's exact message. |
| Payment approved | Student | `payment_approved` + `subscription_activated` | In the same transaction as activation. |
| Payment rejected | Student | `payment_rejected` | Includes the rejection reason. |
| Subscription expiring in 7 / 3 / 1 days | Student | `subscription_expiring` | Daily sweep. |
| Subscription expired | Student | `subscription_expired` | Daily sweep flips the status. |
| Code redeemed | Student | `code_redeemed` | Redemption transaction commits. |
| Subscription deactivated by admin | Student | `subscription_change` | The generic type — the body explains why. |

## 8. Audit trail (what is recorded, where)

| Event | Where |
|---|---|
| Transaction created | `payment_transactions` row (created_at, reference, plan snapshot). |
| Proof submitted / resubmitted | `payment_proofs` row (immutable; resubmission flips the previous row's `is_current` to false). |
| Admin decision (approve / reject / info-needed) | `payment_transactions` status change **+** `admin_audit_logs` row (admin, role, before/after, reason). |
| Subscription activated / expired / deactivated | `subscriptions` row **+** `admin_audit_logs` row (for admin actions; expiry is recorded with `admin_id` NULL and action `subscription.expire` — the sweep is a system action, and the audit row says so). |
| Code generated / redeemed / revoked | `activation_codes` + `activation_redemptions` + `admin_audit_logs` (for admin actions). |
| Plan edited | `plans` row change **+** `admin_audit_logs` row (before/after price and limit). |

No audit row is ever edited or deleted. A correction is a new row.

## 9. Edge cases (decided now, so the build does not re-decide them)

1. **Student pays, never submits proof** → the transaction expires after 72 hours. The money stays with the owner (the student paid without completing the flow); if the student later contacts support, the admin can verify the TID by hand and create the subscription through the admin panel (a manual activation, recorded as `activated_by = 'admin'`). The system does not auto-match late proofs to expired transactions.
2. **Student submits proof for the wrong plan** (paid Rs 600 but selected Yearly) → the admin rejects with `amount_mismatch`; the student starts a new transaction for the right plan.
3. **Two students share one TID** (one pays, both submit) → whoever is approved first wins; the second is rejected as `duplicate_tid`. The payer and the submitter must be the same account — the TID is checked against the submitting student's transaction, and the admin queue shows the submitter's identity.
4. **Admin is offline for days** → pending transactions wait; the 72-hour expiry applies to **proof submission**, not to admin review. A proof submitted in time stays pending until an admin reviews it (no auto-rejection for slow review). The student sees "waiting for review" with the submission time.
5. **Owner changes the receiving number** → old pending transactions keep the old instructions (they snapshot the account at creation); new transactions use the new number. The number is an admin-panel setting, not a code constant.
6. **Plan price changes mid-queue** → a pending transaction keeps its snapshot price; approval activates at the snapshot price. New transactions use the new price.

## 10. What is never claimed

- **No automated screenshot verification.** The system never reads the proof image to verify a payment. The image is evidence for a human.
- **No wallet API, no bank API, no scraping.** No credential for any wallet exists in the system, and none will be added.
- **No instant activation.** The fastest path is "admin reviews quickly". The instructions page must say this honestly ("usually within 24 hours"), never "instant".
- **No payment is ever taken by the website.** The website has no card form, no wallet login, and no payment button that moves money. The only money movement is the student paying in their own wallet app.
