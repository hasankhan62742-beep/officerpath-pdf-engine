# OfficerPath AI — Phase 1 Master Engineering Prompt (v2)

Received from Abdul Qadeer on 2026-11-21 ~16:55 PKT in the main chat.
Full text is in that conversation turn — this file is the durable pointer, not a retype.

## How v2 relates to the Ultimate Edition (16:54 PKT)
Same product, same mission, same non-negotiables — v2 is a second wording of the same Phase 1 assignment, not a new project. Do NOT run a second audit; fold v2 into the Milestone 0 audit already running.

Differences to reconcile in the audit / plan (record them, do not silently pick one):
- Milestones: v2 has 9 (M1 audit+architecture … M9 testing/benchmarking/docs/deployment). Ultimate has M0 audit + M1–M8. Map them 1:1 in the plan and use ONE numbering going forward (recommend Ultimate's M0–M8, with v2 M9 folded into M8, and note the mapping).
- v2 §2 audit: branch named "officerpath-phase1-engine" (same as Ultimate), "do not assume the repository is empty" — audit must verify the actual GitHub repo state (repo exists, public, was empty at creation; local code not yet pushed) rather than assuming.
- v2 §11: optional AI interface — same as Ultimate §15 (provider-independent, disabled by default, suggestions only, never overwrites, core works with no keys).
- v2 §17: admin/review capabilities — backend APIs + data structures for a future admin interface (view docs/jobs, review uncertain answers, correct text/options, verify, reprocess, audit every correction). Ultimate covers this via review/correction APIs + audit trail — same requirement.
- v2 §22 execution: "explain → implement → test → fix → document → limitations → preserve stability" per milestone; "do not proceed by merely describing" — same as Ultimate's gates.
- Both agree: Python primary, FastAPI/Pydantic/SQLAlchemy/PostgreSQL/Alembic, PyMuPDF/pdfplumber, OpenCV/Pillow/NumPy, PaddleOCR + Tesseract behind abstraction, no blind installs, no paid infra/AI without approval, no fabricated accuracy (never claim 100%), answers never invented, keys never cross-apply between papers/documents.

## Standing decisions (unchanged)
- Python engine + Flutter thin client; Render free Stage 1 / Hostinger VPS Stage 2; GCP billing PAUSED — no Cloud Run, no paid provisioning.
- Gemini key server-only, deferred — do not keep asking.
- No Phase 2 until Phase 1 acceptance passes.
- Skeleton-only status 21 Nov: see MASTER_PROMPT_PHASE1_ULTIMATE_2026-11-21.md.

## Status
- 2026-11-21 16:55 PKT: v2 received while M0 audit subagent (started 16:54) was running. v2 folded into that audit via follow-up instruction — no duplicate audit spawned.
