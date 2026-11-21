# OfficerPath AI — Phase 1 Master Engineering Prompt (Ultimate Edition)

Received from Abdul Qadeer on 2026-11-21 ~16:54 PKT in the main chat (side chat fb3f93bf).
Full text is in that conversation turn — this file is the durable pointer, not a retype.

## What it asks for
- Role: Principal Software Architect / Senior Python Engineer / ML-OCR Specialist / Document Intelligence Researcher / Technical Lead. Own outcome end to end.
- Product: Document Intelligence Engine — Python system turning student uploads (digital/scanned/mixed PDFs, JPG/PNG/WebP/TIFF, multi-page, batches, legible handwriting) into structured, traceable, test-ready MCQs for PPSC/FPSC/BPSC/SPSC/KPSC/CSS/PMS/NTS.
- Non-negotiables: truth over completeness (never fabricate answers/text/confidence/numbers); preserve never discard; originals immutable; traceability (doc/page/bbox/engine/method per question/option/answer); publisher independence; core works offline of paid AI (AI advisory only, disabled by default); fail loudly; cost discipline (no paid infra/service without explicit written approval); safe by default; simplest thing that meets requirement.
- Evidence labels on every important statement: VERIFIED / ASSUMED / UNVERIFIED / UNKNOWN.
- Definition of Done: real code on dev branch, tests pass, type checks + lint pass, errors/edge cases handled + tested, structured logs + correlation IDs, documented, evidence protocol, existing app still builds + its tests pass.

## Milestones 0-8 (gates)
- M0 Repository audit, branch, baseline, architecture plan (MANDATORY FIRST, no feature code until audit + plan presented)
- M1 Project structure, config, DB schema, migrations, ingestion, validation, storage
- M2 PDF analysis, page classification, rendering, adaptive preprocessing
- M3 OCR abstraction, engines, digital extractor, layout analysis
- M4 MCQ + option extraction
- M5 Answer detection (key, inline, style, visual, handwriting)
- M6 Matching, validation, confidence scoring, reports, review APIs
- M7 Background jobs, security hardening, observability, performance
- M8 Full test suite, benchmarks, docs, deployment guide, completion report

## Standing decisions this prompt must respect (from earlier turns, 20-21 Nov 2026)
- Engine = Python, app = Flutter thin client (user's settled call; Flutter is UI only, not the problem).
- Hosting: Stage 1 Render free tier (no card expected), Stage 2 Hostinger KVM 1 VPS when payment possible. GCP billing PAUSED after 3-4 cards rejected — do NOT resume, do NOT provision Cloud Run / paid GCP.
- Gemini key lives ONLY on the server, never in the APK; market users need no key. Free tier ~500 req/day on gemini-3.5-flash-lite. Key itself is deferred ('baad ki bat') — do NOT keep asking for it.
- STOP CONDITION: no Phase 2 until every critical Phase 1 acceptance test passes live.
- Current state (VERIFIED 21 Nov): engine is SKELETON ONLY — FastAPI + Dockerfile + register/jobs/health endpoints; OCR + parsing NOT written; PyMuPDF/OpenCV/PaddleOCR/Tesseract NOT in requirements.txt. Local tests 22 passed on 20 Nov. GitHub repo officerpath-pdf-engine exists (public, empty at creation); local ~/workspace/officerpath-pdf-engine is NOT a git repo — code not yet pushed. Migration 015 written, NOT applied live. Flutter v2.0.5 released, phone test still pending on PPSC-66 PDF / table photos / Paper 60 photo.
- Existing audit docs to reuse, not redo blindly: ~/workspace/officerpath-ai/PHASE1_AUDIT_2026-11-20.md, MASTER_DIRECTIVE_2026-11-20.md, PPSC66_BASELINE_2026-11-20.md.
- Never commit to main/production branch, never force-push, never destructive migrations, never touch live Supabase data or production app without approval.
- Answer precedence (standing): manual verification > explicit key > inline answer > digital style > visual > inferred. Keys never cross-apply between papers. A wrong answer presented as correct is the worst failure; flagged uncertain is acceptable; fabricated is not.

## Status
- 2026-11-21 16:54 PKT: Milestone 0 audit started (subagent). No feature code until audit + Phase 1 plan are presented to the user.
