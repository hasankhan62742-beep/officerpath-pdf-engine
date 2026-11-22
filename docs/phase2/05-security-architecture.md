# Phase 2 M1 — Security Architecture

**Date:** 2026-11-22
**Principle:** the backend enforces every important rule. The frontend
is a convenience, never a security boundary. Nothing in this doc weakens
a Phase 1 control; Phase 2 extends them to the new surface.

## 1. What Phase 1 already enforces (verified — reuse, do not rebuild)

| Control | Evidence | Phase 2 implication |
|---|---|---|
| Supabase JWT verification via `auth.get_user`; tokens never decoded locally, never logged, never stored | `app/security/dependencies.py:get_current_user`, `app/integrations/supabase_auth.py:12-52` | Same dependency guards every new endpoint. No new auth scheme. |
| Per-user scoping: another user's resource → 404 (never leaks existence) | `app/services/jobs.py:108-114`, review + async-jobs routes, M7 benchmark (cross-user 404/404) | Every GAP endpoint (doc 02 §5) gets the same 404 pattern + a cross-user test. |
| Uniform error shape, bad input → 4xx never 500 | `app/core/errors.py`, `app/main.py:110-141` | New endpoints use `ApiError` only. |
| Request-size limit → 422 `file_too_large` (100 MB) | `app/main.py:144-172` middleware + ingestion validator | Upload UI enforces the same limits client-side for UX, server-side for truth. |
| Rate limiting: 10 register/parse per user/min, 5 retries/min → 429 | `app/security/rate_limit.py`, `app/config.py:36-40` | In-memory, per process. New write endpoints (test create, submit, corrections) get explicit limits in their milestone. Multi-replica deploys need a distributed limiter (Redis) — a Phase 3 / scale decision, recorded now. |
| Secret redaction in logs | `app/utils/logging.py:12` regex `key\|token\|secret\|password\|auth\|bearer` | Frontend logs nothing sensitive; backend logs carry no file contents or OCR text (M7 rule, kept). |
| Secrets from env only; `.env.example` placeholders only; detect-secrets baseline | `app/config.py`, `.secrets.baseline`, CI `security` job | New secrets follow the same rule. CI secret scan keeps running. |
| File validation: magic bytes, encrypted-PDF rejection, decompression-bomb caps (25 MP, 12,000 px/side) | `app/pipeline/ingestion/validator.py`, `app/config.py:62-83` | The web upload path inherits all of it — no second validator in the frontend. |
| Gemini advisory disabled by default (flag + key + `max_calls_per_day > 0` — three conditions, see doc 01 §6.2) | `app/pipeline/ocr/gemini.py:109-114` | No change. No Gemini endpoint is exposed. |

## 2. Supabase Auth + the frontend (what the browser may hold)

- The browser holds **only** the Supabase **anon key** (publishable)
  and the user's session tokens, via the Supabase JS client (PKCE
  flow). The anon key is public by design; it confers no privilege
  beyond what RLS allows.
- **The frontend must NEVER receive:** the Supabase **service-role
  key**, `DATABASE_URL`, any backend secret, or any Gemini key.
  (`app/config.py:22-28` states this for the engine; the same rule
  binds the web app.) The service-role key lives only in the backend
  environment (Render Dashboard secrets) and is used only by the
  backend's service client (`app/database/supabase_client.py:24`).
- **The frontend talks to Supabase for Auth only** (sign-up, sign-in,
  session, password reset, email verification). All data access goes
  through the FastAPI backend, which re-verifies the JWT on every call
  and applies ownership checks. The browser never calls Supabase
  PostgREST for engine tables.
- **Email verification is real** (Supabase verification flow). No fake
  OTP, no client-side "verified" flag. A user who has not verified
  cannot reach the app shell (the layout guard checks
  `email_confirmed_at`).

## 3. Ownership model (the rule every new endpoint must satisfy)

1. Every user-owned row carries `user_id` (doc 03 §4). Every read,
   write, and list filters by the JWT's user id.
2. Cross-user access returns **404 `not_found`**, never 403 (the Phase
   1 pattern — a 403 would confirm the resource exists).
3. **Shared content is read-only by default.** Extracted questions are
   per-document, per-user. A correction on a shared question is
   visible to the correcting student and admins; it never silently
   rewrites another student's original. (Full shared-question policy
   is decided in M5 with a decision record.)
4. **Documents are private.** A document's file is served only via a
   signed, owner-checked URL (GAP-12); the `pdf-documents` bucket
   stays private (015 policies: owner view/insert, no client update/
   delete). Question-asset crops follow the same rule.
5. **Soft delete, not hard delete.** `documents.deleted_at` and
   `extracted_questions.deleted_at` already exist; Phase 2 uses them.
   No user data is deleted by a frontend action without an explicit
   confirm step, and deletions are recorded.

## 4. Roles — student vs admin (backend-enforced)

- **Today there is no admin role anywhere in the engine.** The
  engine has no `is_admin` column and never writes one; the Flutter
  app's admin concept lives in its own Supabase tables (015
  references "Admins can view all documents/jobs" policies — those
  policies check a Supabase-side admin claim, **UNVERIFIED** in this
  milestone whether that claim exists on any user today).
- **Phase 2 design (M9 implements, M3 records the decision):** admin
  is a claim on the Supabase Auth user (e.g. `app_metadata.is_admin`
  set only via the Supabase Dashboard / service-role script by the
  owner — never self-assigned, never settable through any API). The
  backend reads the claim from the verified JWT user record and
  enforces it in a dependency (`require_admin`); admin routes return
  404 for non-admins (same no-leak pattern). The frontend `/admin/*`
  layout guard is UX only.
- **Students can never reach admin routes** by changing a URL or
  flipping frontend state: the backend dependency is the enforcement
  point, and every admin endpoint gets a non-admin test (401/404).
- **No student can escalate:** no endpoint accepts a role, plan, or
  `is_admin` field from the client. Any such field in a request body
  is ignored (and logged as a validation anomaly in M9).

## 5. What the frontend must never trust

(Phase 2 prompt §21 — the backend is the authority for all of these.)

| Frontend-supplied value | Backend rule |
|---|---|
| Marks / scores / percentages | Computed server-side at submit from snapshots + responses + the session's marking config; stored in `test_results`. Frontend-supplied marks are ignored. |
| Ownership (`user_id` in a body) | Ignored. Ownership comes from the verified JWT only. |
| Answer keys / `correct_index` | Never accepted from the client. The key lives in the snapshot; the client submits only `selected_index`. |
| Subscription limits / plan / premium | Not enforced from the client. Phase 2 has no payment system; any future limit is enforced server-side (Phase 3). |
| Roles | Never accepted from the client (see §4). |
| Timer / submission time | Server-side anchor (`server_started_at`); the browser clock is display-only. Late submissions are judged by the server clock. |
| File metadata (name, size, type, page count) | Re-validated server-side (magic bytes, limits, classification). Client metadata is a hint. |

## 6. Upload and file safety (web path)

- Client-side checks (type, size, page count estimate) are UX only.
- Server-side: the Phase 1 ingestion validator runs unchanged
  (magic bytes, encrypted-PDF rejection, 100 MB cap, decompression-
  bomb caps, per-page classification). A rejected file returns 422
  with a machine code; the UI shows the reason.
- Originals are immutable: upload stores the original once
  (SHA-256 dedup per user); corrections never touch the stored file.
- The `pdf-documents` bucket stays private; no public URLs. Signed
  download URLs are short-lived and owner-checked.

## 7. Web-specific controls (new in Phase 2)

- **CSRF:** the API is token-authenticated (Bearer JWT), not
  cookie-authenticated, so classic CSRF does not apply to API calls.
  If a cookie-based session is ever introduced, `SameSite=Lax` +
  CSRF tokens become mandatory — record the decision then. The
  Next.js frontend must not introduce cookie auth silently.
- **XSS:** React escapes by default; no `dangerouslySetInnerHTML`
  for user content (question text, notes, document titles). Any
  exception needs a review note in the PR.
- **CORS:** the backend allows only the configured frontend origins
  (dev `http://localhost:3000`, prod the deployed frontend domain —
  see doc 06 §4). Credentials are never `*` in production.
- **Security headers:** the frontend sets `Content-Security-Policy`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and
  `Permissions-Policy` (decided in M2, verified in M9/M10).
- **Dependency hygiene:** `npm audit` in CI; the same pip-audit /
  detect-secrets discipline as the Python side.
- **Notifications:** in-app only in Phase 2. No email is claimed sent
  unless a provider confirms delivery (prompt §19).

## 8. Audit and monitoring

- Correction audit trail: `manual_corrections` + `review_history`
  (existing, Phase 1). Admin actions in M9 go to the existing
  `audit_log` table.
- Auth anomalies (repeated failed logins, cross-user 404 spikes) are
  visible in `errors_total` / `http_requests_total` metrics and JSON
  logs; alerting thresholds are a deploy-time decision (doc 06 §6),
  not a Phase 2 build item.
- **Subscription/premium status (dashboard display):** Phase 2 shows
  it only if the Flutter app's Supabase tables already carry it, read
  through the backend (never from the browser, never written by the
  engine). If the data is not reliably available, the dashboard shows
  "Not available" — never a fabricated status.
