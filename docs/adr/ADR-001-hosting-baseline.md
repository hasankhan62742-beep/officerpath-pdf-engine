# ADR-001 — Hosting baseline: Render free (Stage 1) vs Cloud Run / GCP (paused) vs Hostinger VPS (Stage 2)

- **Status:** APPROVED by the owner on 2026-11-21 17:03 PKT ("Haan, ADR-001 aur ADR-002 approve hain, M1 shuru karo")
- **Date:** 2026-11-21
- **Deciders:** Abdul Qadeer (owner); Phase 1 audit
- **Context source:** Ultimate Master Prompt §22 (deployment readiness, cost discipline, no paid infra without explicit approval); v2 Master Prompt §22 (same); standing decisions from 20–21 Nov 2026.

## Context

The OfficerPath AI engine is a Python FastAPI service (Docker image, `python:3.12-slim`, non-root, `/health` healthcheck) that must run somewhere reachable by the Flutter app. Constraints from the owner, all VERIFIED from the record:

- **Zero budget, no card.** GCP billing is PAUSED after 3–4 cards were rejected (15:49 PKT, 21 Nov 2026); do not resume GCP until the owner says so.
- **Stage 1 must be Rs 0, no card expected; Stage 2 is a Hostinger KVM 1 VPS when payment becomes possible.** (Owner's settled call, 21 Nov 2026.)
- The engine is a skeleton today (M0 audit): register/jobs/health only. No OCR yet. The hosting choice therefore decides what OCR is feasible in Stage 1 (see ADR-002).
- The existing deployment docs in the repo assume Cloud Run (`README.md` "Deploy (Cloud Run)", `Dockerfile` comments). Those docs are stale relative to the owner's decision.

## Options considered

### Option A — Render free tier web service (Docker) — RECOMMENDED as Stage 1

- **Evidence (web-verified 21 Nov 2026, multiple sources incl. Render docs and independent free-tier comparisons):** free web service = **512 MB RAM, 0.1 CPU**, 750 instance-hours/month per workspace (covers one service running ~continuously), **spins down after 15 minutes without traffic, ~30–60 s cold start** to wake; no credit card required for standard free services (multiple sources state this; one caveat in the record: some users have reported being asked for a card at signup — **not 100% guaranteed**); free tier docs say "do not use them for production applications"; filesystem is ephemeral.
- **Fits:** Docker deploy from a GitHub repo (matches the existing Dockerfile + CI shape); Supabase stays the database (Render's free Postgres, which expires after ~30–90 days, is **not** needed); env vars for secrets; $0.
- **Consequences:** 512 MB / 0.1 CPU rules out heavy in-process OCR (PaddleOCR full pipeline, Tesseract on large pages, OpenCV at high DPI) as a routine path — see ADR-002. Cold starts add ~1 min to the first request after idle; a keep-alive ping can prevent sleep but consumes the instance-hours quota and can mask real outages — decide explicitly, don't silently add one. One service only within the quota; a separate worker process would need a second service (Background Workers are not free on Render) — so Stage 1 must run jobs in-process or via the web service itself (e.g. a `/jobs` worker loop inside the same container), which M7 must design around.

### Option B — Google Cloud Run (free tier) — REJECTED for Stage 1 (blocked, not on merit)

- **Evidence (2026-11-20 deploy research, official Cloud Run pricing page):** genuine free tier (2M requests, 180k vCPU-seconds, 360k GiB-seconds/month), request-based billing, min instances 0, Mumbai (`asia-south1`) is Tier 1 and closest to Pakistan. At tens of jobs/day the expected bill is $0.00.
- **Why rejected now:** Cloud Run **requires a billing account (a payment method on file) to deploy at all, even inside the free tier**. The owner's billing path is paused after 3–4 rejected cards. Re-attempting risks flagging the account further. This is a **blocker, not a technical judgment** — Cloud Run remains the best-value option if/when billing is resolved.
- **Consequences:** the repo's Cloud Run deploy docs must be rewritten (M1), not followed. Do not create/enable any GCP resource in Phase 1.

### Option C — Hostinger KVM 1 VPS — Stage 2 (deferred, not now)

- **Evidence (owner's research, 21 Nov 2026):** KVM 1 = 4 GB RAM, root, Docker, Mumbai DC; Rs 2,099/month on a 24-month term = **Rs 50,376 upfront**; JazzCash currently PAUSED, Easypaisa NOT accepted, cards only. Shared hosting cannot run the Python engine (VPS only).
- **Fits:** the permanent home — 4 GB RAM removes the OCR ceiling, no sleep, full control (worker processes, queues, local models).
- **Why deferred:** upfront cost + payment method unavailable today. **No purchase, no provisioning in Phase 1.**

### Option D — Considered and ruled out (evidence in the record)

- **Cloudflare Workers (Python):** 128 MB isolate, 10 ms CPU free, no native libs — cannot run PaddleOCR/Tesseract/OpenCV. Stays for website/admin only.
- **Koyeb:** now needs a card ($29 hold since Feb 2026) — ruled out.
- **Hugging Face Spaces (Docker):** needs PRO $9/month (free Gradio trick uncertain).
- **Modal:** $30/month credits, but card requirement conflicted across sources (uncertain) — not a clean no-card path.
- **Supabase Edge Functions:** cannot run the Python OCR stack (Deno/TypeScript only).

## Decision (PROPOSED)

**Stage 1: Render free tier Docker web service. Stage 2: Hostinger KVM 1 VPS when payment is possible. Cloud Run: parked until GCP billing is resolved by the owner.**

## Consequences

- M1 rewrites the deploy docs for Render (render.yaml / dashboard steps, env vars, health check path, no Cloud Run references) and records the keep-alive decision explicitly.
- The Dockerfile needs no change for Render (it is platform-agnostic); only its comments change.
- M7 must design background processing for a single 512 MB container (in-process worker loop or Supabase-backed queue polled by the web service), because a second free Render service is not available for a worker.
- Stage-1 performance targets must be set against 0.1 CPU / 512 MB, not against this VM (4 vCPU / 8 GB). Benchmarks run on the VM must be labelled as such.
- A GitHub repo is a prerequisite for Render auto-deploy — blocked on the owner's repo decision (§9 R1 of the audit).

## Revisit conditions

- If Render asks for a card at signup (the known caveat), stop and report to the owner before entering any payment details; do not substitute another paid host silently.
- If GCP billing is resolved, re-evaluate Cloud Run vs Render on measured Stage-1 usage (jobs/day, seconds/job) — Cloud Run's free tier is more generous for bursty OCR.
- If Hostinger payment becomes possible, Stage 2 moves the same Docker image to the VPS with a worker process and a queue (M7 design must already allow this).
- If Render changes its free tier (RAM/CPU/sleep), re-benchmark M7 load tests and update this ADR.
