# Phase 3 — Database Design

**Project:** OfficerPath AI — Phase 1 Document Intelligence Engine + Phase 2 Web Application
**Workstream:** H (Phase 3 architecture ONLY — design, no implementation)
**Date:** 2026-11-23 (PKT)
**Status:** Design only. No migration in this document has been written, applied, or tested. Every table below is PENDING.

**Status vocabulary (only these are used):** VERIFIED / COMPLETED / PENDING / BLOCKED / FAILED / REQUIRES OWNER APPROVAL.

**Honesty note:** The existing schema was reviewed first-hand in `app/db/models.py` (28 tables, Alembic 0001–0009). Every reuse/conflict decision in §1 was checked against that file. The new tables in §2 are a design — column types and constraints are specified here so the build phase can write the migrations without re-deciding them, but they have not been validated by running a migration.

**Related documents (built on, not duplicated):** `docs/phase3/PHASE3_MASTER_ARCHITECTURE.md`, `docs/phase2/03-database-extension-plan.md` (the extension rules this design follows: extend, never rewrite; one Alembic revision per milestone; upgrade + downgrade; seed data idempotent), `docs/phase2/PHASE_2_COMPLETION_REPORT.md`, `app/db/models.py`.

---

## 1. Existing schema — reviewed first, reused where possible

### 1.1 Full existing table list (VERIFIED from `app/db/models.py`)

| Table | Owner | Phase 3 relevance |
|---|---|---|
| `documents`, `jobs` | Supabase 015 (mirrored) | None — untouched. |
| `student_profiles` | Alembic 0003 | **Reused** for the Students admin module (display data only). No new students table. |
| `subjects`, `topics`, `question_subjects` | Alembic 0005 | None. |
| `document_pages`, `processing_stages`, `ocr_blocks` | Alembic 0001 | None. |
| `extracted_questions`, `question_options`, `question_assets`, `extracted_answers`, `answer_evidence`, `answer_sources`, `extraction_reports` | Alembic 0001 | None — the bank is never copied for Phase 3. |
| `manual_corrections`, `review_history`, `processing_errors`, `audit_log`, `rule_set_versions` | Alembic 0001 | `audit_log` stays the document/pipeline audit trail (see §1.3). |
| `marking_configs`, `test_templates`, `test_sessions`, `test_question_snapshots`, `student_responses`, `test_results` | Alembic 0006/0007 | **Read** by the usage counter (`test_sessions` creation is the billable event). No column is added to any of them. |
| `student_question_collections` | Alembic 0008 | None. |
| `notifications` | Alembic 0009 | **Reused and extended** (§3). No new notifications table. |

### 1.2 Conflicts found and how they were resolved

| # | Apparent conflict | Resolution (decision) |
|---|---|---|
| C1 | The brief proposes a `notifications` table, but `notifications` **already exists** (M9, Alembic 0009), with types including `subscription_change`. | **Reuse.** No second table. Phase 3 extends the existing table's CHECK constraint and the `NOTIFICATION_TYPES` allowlist in `app/services/notifications.py` with payment types (§3). A duplicate table would split the student's inbox in two. |
| C2 | The brief proposes `admin_audit_logs`, but `audit_log` already exists (append-only). | **Both, with distinct purposes.** `audit_log` stays the document/pipeline trail (user_id, document_id, action, target_type, target_id, detail, correlation_id). `admin_audit_logs` is new and records **admin** actions with admin identity, role at the time, and before/after state — fields `audit_log` does not have. Cross-reference via `correlation_id`. No duplication: the two tables never record the same event. |
| C3 | The brief proposes `admin_users`/`roles`, but admin today is a single JWT boolean (`app_metadata.is_admin`). | **Layer, not replacement.** `admin_users` maps an Auth user id to a role **only for users who already pass `require_admin`**. If `is_admin` is false, no role applies. This avoids a second, conflicting source of admin truth (see master architecture §7). |
| C4 | The brief proposes a students module, but `student_profiles` already exists. | **Reuse.** No new students table. Payment/subscription data never goes into `student_profiles` (it holds display/profile data only). |
| C5 | The Flutter app's Supabase `profiles` table has `plan` / `premium_until`. | **Do not touch, do not merge.** Phase 3 subscriptions live in the engine DB only. The engine never writes the Flutter table (Phase 2 rule, unchanged). |
| C6 | No existing table is named `plans`, `subscriptions`, `payment_transactions`, `payment_proofs`, `activation_codes`, `activation_redemptions`, `subscription_usage`, `admin_roles`, `admin_users`, or `admin_audit_logs`. | **No name collision.** All ten new tables are genuinely new (verified against the §1.1 list). |
| C7 | `test_sessions.status` has no CHECK constraint in the model (doc 03 describes values `created`/`in_progress`/`submitted`/`abandoned`/`expired`). | **No change.** Phase 3 reads `status` and `created_at` only; it does not add a constraint to an existing table. |

### 1.3 Conventions this design follows (from doc 03)

- Every new table: `id` UUID PK, `created_at` (+ `updated_at` where the row is ever edited), `user_id` UUID NOT NULL on user-owned rows, explicit `ondelete` on every FK, index on `(user_id, created_at)` on user-owned tables.
- Foreign keys to `auth.users` are **not** enforceable from the engine DB (different connection path) — `user_id` is a plain UUID, uniqueness/ownership enforced in code (the same pattern as `student_profiles`).
- Money in **paisa (integer)**, never floats, never `Numeric` for money (marks use `Numeric(10,2)`; money does not).
- Audit tables are append-only by design (no update/delete API).
- Timestamps are timezone-aware (`DateTime(timezone=True)`).

---

## 2. New tables (10)

All ten live in the **engine DB** (SQLAlchemy + Alembic), never in Supabase migrations — the same ownership split as Phase 2. `user_id` throughout means the Supabase Auth user id.

### 2.1 `plans`

One row per sellable plan. Seeded by migration with the four plans from the master architecture §2.3.

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `slug` | Text NOT NULL, UNIQUE | `free`, `monthly`, `two_months`, `yearly` — the stable identifier the API and frontend use. |
| `name` | Text NOT NULL | Display name, e.g. "Monthly". |
| `price_paise` | Integer NOT NULL, CHECK (`price_paise >= 0`) | Rs 600 = 60000. Free = 0. |
| `test_limit` | Integer NULL | NULL = unlimited (Yearly). 3 / 20 / 50 for the others. |
| `duration_days` | Integer NULL | NULL = no expiry (Free). 30 / 60 / 365. |
| `is_active` | Boolean NOT NULL, default true | An inactive plan cannot be bought; existing subscriptions are unaffected. |
| `sort_order` | Integer NOT NULL, default 0 | Display order on the Pricing page. |
| `created_at` / `updated_at` | timestamps | |

Seed (idempotent `INSERT … ON CONFLICT (slug) DO NOTHING`): free (0, 3, NULL), monthly (60000, 20, 30), two_months (120000, 50, 60), yearly (600000, NULL, 365).

### 2.2 `subscriptions`

One row per activated paid plan. A student has **at most one active subscription** (partial unique index, §2.2 constraints).

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID NOT NULL | The student. Index `(user_id, created_at)`. |
| `plan_id` | UUID NOT NULL, FK → `plans.id` ON DELETE RESTRICT | RESTRICT: a plan with live subscriptions cannot be deleted (deactivate it instead). |
| `plan_slug` | Text NOT NULL | **Snapshot** of the plan slug at activation. |
| `plan_name` | Text NOT NULL | **Snapshot** of the plan name at activation. |
| `price_paise` | Integer NOT NULL | **Snapshot** of the price paid. Later plan edits never rewrite history. |
| `test_limit` | Integer NULL | **Snapshot** of the limit (NULL = unlimited). |
| `status` | Text NOT NULL, CHECK (`status IN ('active', 'expired', 'deactivated')`) | `expired` = passed `ends_at` (set by the daily sweep); `deactivated` = admin action with reason. |
| `starts_at` | timestamptz NOT NULL | Activation moment (admin approval or code redemption). |
| `ends_at` | timestamptz NOT NULL | `starts_at + plan duration_days`. |
| `activated_by` | Text NOT NULL, CHECK (`activated_by IN ('payment', 'code', 'admin')`) | How this subscription came to be. |
| `payment_transaction_id` | UUID NULL, FK → `payment_transactions.id` ON DELETE SET NULL | The approved payment that funded it (NULL for code/admin activations). |
| `activation_code_id` | UUID NULL, FK → `activation_codes.id` ON DELETE SET NULL | The redeemed code (NULL otherwise). |
| `deactivated_reason` | Text NULL | Required when status becomes `deactivated`. |
| `deactivated_by` | UUID NULL | The admin who deactivated it. |
| `created_at` / `updated_at` | timestamps | |

Constraints: partial unique index `uq_subscriptions_one_active` on (`user_id`) WHERE `status = 'active'`; index `(user_id, status, ends_at)` for the expiry sweep and the active-lookup.

### 2.3 `payment_transactions`

One row per payment attempt (a student starting the manual flow). The **claim**, not the money.

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID NOT NULL | The payer. Index `(user_id, created_at)`. |
| `plan_id` | UUID NOT NULL, FK → `plans.id` ON DELETE RESTRICT | The plan being bought. |
| `plan_slug` / `plan_name` / `price_paise` | Text / Text / Integer NOT NULL | Snapshots at creation (same reason as §2.2). |
| `method` | Text NOT NULL, CHECK (`method IN ('easypaisa', 'jazzcash')`) | |
| `reference` | Text NOT NULL, UNIQUE | Server-generated unique reference, e.g. `OP-7K2Q9X4M`. Shown to the student; used to match their proof submission. |
| `status` | Text NOT NULL, CHECK (`status IN ('pending', 'info_needed', 'approved', 'rejected', 'expired')`) | State machine: pending → approved/rejected/info_needed/expired; info_needed → pending. Approved/rejected are terminal. |
| `transaction_id` | Text NULL | The wallet TID the student enters (e.g. the Easypaisa/JazzCash transaction ID). NULL until the student submits proof. |
| `amount_paise` | Integer NULL | The amount the student claims to have paid. NULL until proof submission. Must equal `price_paise` for approval (see workflow §6). |
| `paid_at` | timestamptz NULL | The date/time the student claims the payment was made. NULL until proof submission. |
| `reviewed_by` | UUID NULL | The admin who approved/rejected it. |
| `reviewed_at` | timestamptz NULL | |
| `rejection_reason` | Text NULL | Required when status becomes `rejected`. |
| `review_note` | Text NULL | Admin's internal note (never shown to the student unless it is an info-needed message). |
| `info_needed_message` | Text NULL | What the admin asks the student for (shown to the student). |
| `expires_at` | timestamptz NOT NULL | `created_at + 72 hours`. The daily sweep flips un-proofed pending rows to `expired`. |
| `created_at` / `updated_at` | timestamps | |

Constraints: partial unique index `uq_payment_tid_approved` on (`method`, `transaction_id`) WHERE `status = 'approved'` — the same wallet transaction can never approve twice; index `(status, created_at)` for the admin queue; index `(user_id, status)`.

### 2.4 `payment_proofs`

One row per submitted proof file. A transaction may have several proof rows (the original submission + resubmissions after `info_needed`).

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `payment_transaction_id` | UUID NOT NULL, FK → `payment_transactions.id` ON DELETE CASCADE | |
| `user_id` | UUID NOT NULL | The submitter (denormalised so the admin queue can filter without a join). |
| `storage_path` | Text NOT NULL | Path in the `payment-proofs` bucket (new private bucket, same policy pattern as 016: users upload/view own, admins view all). Created by a Supabase migration in the build phase — **not** in this design. |
| `file_type` | Text NOT NULL, CHECK (`file_type IN ('jpg', 'jpeg', 'png', 'pdf')`) | Screenshot or PDF only. |
| `file_size_bytes` | Integer NOT NULL, CHECK (`file_size_bytes > 0 AND file_size_bytes <= 10485760`) | 10 MB cap per proof file. |
| `note` | Text NULL | Optional student note with the proof. |
| `is_current` | Boolean NOT NULL, default true | Only the latest proof per transaction is `is_current`; resubmission flips the previous row to false (history retained, never deleted). |
| `created_at` | timestamp | No `updated_at` — proof rows are immutable. |

Index: `(payment_transaction_id, created_at)`.

### 2.5 `activation_codes`

One row per generated code. **The plaintext code is never stored** — only its SHA-256 hash.

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `code_hash` | Text NOT NULL, UNIQUE | SHA-256 hex of the plaintext code. The plaintext is shown to the admin once at generation and then unrecoverable. |
| `code_prefix` | Text NOT NULL | First 4 characters of the plaintext (e.g. `OP-7K`) — lets the admin identify a code without storing it. |
| `plan_id` | UUID NOT NULL, FK → `plans.id` ON DELETE RESTRICT | The plan this code buys. |
| `plan_slug` | Text NOT NULL | Snapshot. |
| `status` | Text NOT NULL, CHECK (`status IN ('unused', 'redeemed', 'expired', 'revoked')`) | `expired` is set by the sweep after `expires_at`; `revoked` is an admin action on an unused code. |
| `batch_id` | UUID NULL | Groups codes generated in one bulk action (for campaign reporting). |
| `generated_by` | UUID NOT NULL | The admin who generated it. |
| `funded_by_transaction_id` | UUID NULL, FK → `payment_transactions.id` ON DELETE SET NULL | The approved payment that funded this code, if any (NULL for giveaway codes). |
| `redeemed_by` | UUID NULL | The student who redeemed it. |
| `redeemed_at` | timestamptz NULL | |
| `revoked_by` / `revoked_reason` | UUID NULL / Text NULL | Required when status becomes `revoked`. |
| `expires_at` | timestamptz NOT NULL | Default generation + 90 days; settable by the admin at generation. |
| `created_at` / `updated_at` | timestamps | |

Index: `(status, created_at)` for the admin code list; `(batch_id)` for bulk reporting.

### 2.6 `activation_redemptions`

One row per redemption **attempt** (success and failure). The audit trail for codes.

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `code_id` | UUID NOT NULL, FK → `activation_codes.id` ON DELETE RESTRICT | RESTRICT: a code with redemption history is never deleted. |
| `attempted_by` | UUID NOT NULL | The student who attempted. Index `(attempted_by, attempted_at)`. |
| `status` | Text NOT NULL, CHECK (`status IN ('redeemed', 'failed')`) | |
| `failure_reason` | Text NULL | Required when `failed` (e.g. `code_not_found`, `already_redeemed`, `expired`, `revoked`, `plan_already_active`, `rate_limited`). The *student* sees only a generic message; the specific reason lives here for the admin. |
| `subscription_id` | UUID NULL, FK → `subscriptions.id` ON DELETE SET NULL | The subscription created by a successful redemption. |
| `attempted_at` | timestamptz NOT NULL, default now() | No `updated_at` — attempts are immutable. |

Constraints: partial unique index `uq_redemption_one_success` on (`code_id`) WHERE `status = 'redeemed'` — the database itself guarantees single-use even under race; index `(code_id, attempted_at)`.

### 2.7 `subscription_usage`

One row per (user, period) counter. The source of truth for "tests used".

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID NOT NULL | Index `(user_id, created_at)`. |
| `subscription_id` | UUID NULL, FK → `subscriptions.id` ON DELETE SET NULL | NULL = Free tier usage (no subscription row exists for free users — see §4). |
| `period_start` | timestamptz NOT NULL | Free: the user's account creation (lifetime window). Paid: the subscription's `starts_at`. |
| `period_end` | timestamptz NULL | NULL = open-ended (Free, or an active paid period). Set when the period closes. |
| `tests_used` | Integer NOT NULL, default 0, CHECK (`tests_used >= 0`) | Incremented in the same transaction as test creation (§4 of the master architecture). |
| `created_at` / `updated_at` | timestamps | |

Constraints: partial unique index `uq_usage_open_period` on (`user_id`) WHERE `period_end IS NULL` — one open usage window per student, so the atomic increment always finds exactly one row to lock.

### 2.8 `admin_roles`

Seeded reference table. Three roles in v1 (see master architecture §7).

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `slug` | Text NOT NULL, UNIQUE | `owner`, `finance`, `support`. |
| `name` | Text NOT NULL | Display name. |
| `description` | Text NULL | What the role may do, in plain words (also enforced in code — the table documents, the code enforces). |
| `created_at` / `updated_at` | timestamps | |

Seed (idempotent): owner, finance, support.

### 2.9 `admin_users`

Maps an Auth user to a role. Applies **only** to users who pass `require_admin` (JWT `is_admin`).

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID NOT NULL, UNIQUE | The admin's Auth user id. One role per admin in v1. |
| `role_id` | UUID NOT NULL, FK → `admin_roles.id` ON DELETE RESTRICT | |
| `assigned_by` | UUID NOT NULL | The owner who assigned it. |
| `created_at` / `updated_at` | timestamps | |

A user with `is_admin=true` but no row here is treated as **support** (least privilege) until the owner assigns a role.

### 2.10 `admin_audit_logs`

Append-only record of every admin action. No update/delete API exists for this table by design.

| Column | Type / constraint | Notes |
|---|---|---|
| `id` | UUID PK | |
| `admin_id` | UUID NOT NULL | The admin who acted. Index `(admin_id, created_at)`. |
| `admin_role` | Text NOT NULL | The role **at the time of the action** (snapshot — a later role change does not rewrite history). |
| `action` | Text NOT NULL | e.g. `payment.approve`, `payment.reject`, `payment.info_needed`, `subscription.deactivate`, `code.generate`, `code.revoke`, `code.bulk_generate`, `plan.update`, `role.assign`, `role.revoke`, `notification.send`. |
| `entity_type` | Text NOT NULL | e.g. `payment_transaction`, `subscription`, `activation_code`, `plan`, `admin_user`. |
| `entity_id` | UUID NULL | The affected row. Index `(entity_type, entity_id)`. |
| `before_json` | JSONB NULL | State before the action (for edits/deactivations). |
| `after_json` | JSONB NULL | State after the action. |
| `reason` | Text NULL | The admin's stated reason (required for rejections, revocations, deactivations). |
| `ip_address` | Text NULL | If the request carries it (best effort; NULL is acceptable). |
| `correlation_id` | Text NULL | Links to the matching `audit_log` row where one exists. |
| `created_at` | timestamp | No `updated_at` — append-only. |

---

## 3. `notifications` extension (reuse, not a new table)

The M9 `notifications` table is reused. Two changes, both in the build phase:

1. **CHECK constraint:** drop `ck_notification_type` and recreate it with the existing six types **plus**: `payment_received`, `payment_approved`, `payment_rejected`, `payment_info_needed`, `subscription_activated`, `subscription_expiring`, `subscription_expired`, `code_redeemed`. The existing `subscription_change` type is kept as the generic fallback for admin-driven subscription changes that fit no specific type.
2. **Allowlist:** extend `NOTIFICATION_TYPES` in `app/services/notifications.py` with the same eight types. The service already rejects unknown types with a 422 (never a 500) — that behaviour is unchanged.

Notification events (who gets what) are specified in `PHASE3_PAYMENT_WORKFLOW.md` §7. No email channel is added: notifications stay in-app only, per the Phase 2 rule (prompt §19).

## 4. Relationships (summary)

```
plans 1───* subscriptions ───* subscription_usage (nullable FK; NULL = Free)
   │              │  ▲
   │              │  │ payment_transaction_id / activation_code_id
   │              │
   │         payment_transactions 1───* payment_proofs
   │              │  ▲ (funded_by_transaction_id)
   │              │
   │         activation_codes 1───* activation_redemptions
   │              │  ▲ (code_id)
   │              │
   └──────────────┘
admin_roles 1───* admin_users (user_id → role)
admin_audit_logs (standalone; references entities by type + id)
notifications (existing; extended types)
student_profiles (existing; read by Students module)
test_sessions (existing; creation increments subscription_usage)
```

**Free-tier usage without a subscription row (decision):** free users have **no** `subscriptions` row — Free is the absence of an active paid subscription. Their usage lives in `subscription_usage` with `subscription_id = NULL` and an open-ended period (`period_end IS NULL`, `period_start` = account creation). This keeps signup clean (no row per user at registration) and makes "current plan" a single query: active subscription row, or Free. The `uq_usage_open_period` partial unique index guarantees one open window per student.

## 5. Migration strategy

- **Revisions 0010–0013 (provisional numbers — the next free numbers after 0009; renumber at build time if another revision lands first):**
  - `0010` — `plans` + `subscriptions` + `subscription_usage` (seed the four plans + three roles? No — roles belong with the admin tables; 0010 seeds plans only).
  - `0011` — `payment_transactions` + `payment_proofs` (+ the new `payment-proofs` Supabase bucket, created by a Supabase migration in the same build step, following the 016 pattern).
  - `0012` — `activation_codes` + `activation_redemptions`.
  - `0013` — `admin_roles` + `admin_users` + `admin_audit_logs` + the `notifications` CHECK-constraint extension + seed the three roles.
- **Additive only.** No existing table is altered except the `notifications` CHECK constraint (§3), which only *widens* the allowed values. No column is dropped, no table is renamed, no existing row is rewritten.
- **Each revision:** `upgrade()` + `downgrade()`, tested on SQLite in CI (the existing CI job) and against a Postgres instance before any deploy — the same rule as Phase 2 (doc 03 §6). A downgrade that would drop a table holding rows **refuses** (raises) unless an explicit archive step has run; that rule is written into the migration.
- **Ordering:** Phase 3 migrations run **after** the Phase 2 chain (0001–0009) is live. The chain must stay linear — 0010's `down_revision` is 0009.
- **No automatic migration on deploy** until the deploy programme decides the deploy-time migration step (Workstream C runbook). Until then, migrations are applied by the documented manual step.
- **Seed data** (plans, roles) ships inside the creating revision as idempotent inserts (`INSERT … ON CONFLICT DO NOTHING` on Postgres; equivalent guard on SQLite for CI).

## 6. What happens to existing data

- **Nothing is migrated or deleted.** Every existing row stays exactly as it is. No backfill is needed: subscriptions, payments, codes, and usage all start empty, and free users' past tests are **not** counted against the Free limit (the limit applies to tests created after the Phase 3 deploy; counting history retroactively would punish early users for using the free beta as it was offered). This is a deliberate decision — record it in the build, do not silently backfill.
- **Existing tests keep working:** a student mid-way through a `created` session when Phase 3 deploys is unaffected (the gate runs at creation, and their session already exists).
- **Existing notifications keep working:** the CHECK widening only adds values.

## 7. Data retention and privacy

- **Payment proofs:** stored in the private `payment-proofs` bucket (per-user policies: users upload/view their own, admins view all — the 016 pattern). Proof files are never deleted by the system; an admin may delete a proof only by deleting its `payment_proofs` row through a dedicated admin action that is itself audited.
- **TIDs:** stored as plain text (they are transaction references, not secrets). They are visible to the owning student and to admins only.
- **No card data, no wallet PINs, no CVVs — ever.** The API must reject any payload containing card-like fields (see `PHASE3_SECURITY_PLAN.md` §6).
- **PII minimised:** the payment flow needs no new personal data beyond what `student_profiles` already holds. The student's phone (if on the profile) is used only for the admin's reference in the payment queue.
- **Audit rows are never edited or deleted** (`admin_audit_logs`, `audit_log`, `activation_redemptions`, `payment_proofs` history). Corrections happen by new rows, never by rewriting old ones — the same rule as Phase 1/2.
