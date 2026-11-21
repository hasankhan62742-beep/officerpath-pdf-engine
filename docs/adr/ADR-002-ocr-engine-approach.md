# ADR-002 — OCR engine approach: Gemini-advisory-first vs offline-first (PaddleOCR / Tesseract)

- **Status:** APPROVED by the owner on 2026-11-21 17:03 PKT ("Haan, ADR-001 aur ADR-002 approve hain, M1 shuru karo")
- **Date:** 2026-11-21
- **Deciders:** Abdul Qadeer (owner); Phase 1 audit
- **Context source:** Ultimate Master Prompt §8 (multi-engine OCR), §15 (optional AI, disabled by default); v2 Master Prompt §11 (same); standing decisions from 20–21 Nov 2026.

## Context

The engine must turn scanned/image PDFs (two-column, mixed English/Urdu, Nastaliq script, answer keys, visual marks) into structured MCQs. The non-negotiables: a wrong answer presented as correct is the worst failure; uncertain answers are flagged, never fabricated; the core must work offline of paid AI; AI is advisory only, never a verified answer. Constraints from the owner:

- **Gemini key lives only on the server, never in the APK; market users need no key.** The server key itself is **deferred** ("baad ki bat") — do not keep asking the owner for it.
- **Hosting is Render free Stage 1** (512 MB RAM, 0.1 CPU — see ADR-001), which constrains local OCR heavily.
- **No paid AI/infra without explicit approval.**

## Options considered

### Option A — Gemini vision as the primary OCR route, offline engines as fallback — RECOMMENDED for Stage 1

- **Evidence (cited from the PPSC66 baseline + 2026-11-20 audit, not re-measured in M0):**
  - Gemini vision (`gemini-3.5-flash-lite`, prompt-enforced left-column-first reading order, image resized to 1000 px) + the Dart parser scores **100/100 on PPSC-66** on the VM, key 100/100 matched. This is the only OCR route with a measured 100/100 on the acceptance file.
  - The same parser on real Tesseract 5.3.4 text scores **14–20/100**; on phone ML Kit text **1/100**. The gap is OCR quality, not parser logic.
  - **Caveats measured on the same baseline:** Gemini's recitation filter blocked p3 (6 blocks) and p5 (2 blocks) of PPSC-66; mitigation was page crops + `[?]` marking, which is designed but unproven server-side. Gemini `gemini-2.5-flash-lite` returns HTTP 404 (tested 19 Nov 2026) — must not be used. Free tier is ~500 requests/day shared per project — a server key caps at roughly ~70 seven-page books/day (ASSUMED arithmetic from the 500/day figure, not measured).
- **Fits:** Gemini calls are network-bound, not CPU/RAM-bound — they fit inside Render's 512 MB / 0.1 CPU envelope, where local OCR does not. The `AIAssistProvider` interface (prompt §15) is the right shape: provider-independent, disabled by default, suggestions only, every call logged with cost/latency, rate-limited and budget-capped.
- **Consequences:** Stage 1 cannot start OCR work until the server-key question is settled on the owner's terms (key deferred). Until then, M3 builds the abstraction + digital extractor + offline engines and benchmarks them; Gemini integration is built behind the disabled-by-default flag with no key provisioned. Student content is sent to Google only with explicit configuration + a documented privacy notice (prompt §15).

### Option B — Offline-first: PaddleOCR + Tesseract behind the `OCREngine` abstraction, Gemini advisory only

- **Evidence:**
  - **PaddleOCR PP-OCRv5 Arabic-script model** (`arabic_PP-OCRv5_mobile_rec`) officially lists Urdu among its languages (Arabic, Persian, Uyghur, Urdu, Pashto, Kurdish, Sindhi, Balochi, English; Baidu claims 81.27% on a 2,676-image Arabic-script set) — per the record, 21 Nov 2026. **Nastaliq quality is UNPROVEN** (model trained mainly on Naskh-style Arabic; Nastaliq's diagonal baseline/overlaps are harder) and **must be benchmarked on the real fixtures before any claim**.
  - **Tesseract:** ceiling 16–20/100 on PPSC-66 (cited above); partially readable on dense ~130 DPI Nastaliq, not reliable for clean Urdu MCQs.
  - **EasyOCR: rejected** (19 Nov: p.24 key 39/100, silent wrong answers, ~8–11 min/page).
  - **Resource evidence:** PaddleOCR on Render free (512 MB / 0.1 CPU) is ASSUMED too slow/heavy for routine use (page-by-page, minutes per book — per the record; **not measured on Render**). UTRNet (92.97% real lines, cited) is a named candidate if a non-Gemini Urdu route is ever required; Cloud Vision Urdu test is still pending (needs the owner's GCP project).
- **Fits:** satisfies "core works offline of paid AI" in the strongest sense; no key, no per-call cost, no recitation filter, no third-party data sharing.
- **Consequences:** expected quality on the acceptance files is materially below Gemini (Tesseract ceiling is measured; PaddleOCR Nastaliq is unknown). If PaddleOCR benchmarks poorly on the fixtures in M3, offline-first cannot be the primary route for Urdu books and the owner must decide between (a) accepting lower Urdu quality, (b) the deferred server key, or (c) postponing Urdu-heavy books.

### Option C — Hybrid (the actual shape of the recommendation)

Build the abstraction so **both** routes exist and are routed per page, with measured evidence deciding the default:

1. **Digital text first** (PyMuPDF/pdfplumber) wherever a page has reliable selectable text — free, exact, no OCR needed.
2. **Gemini vision** for scanned/image pages **when a server key is configured** (Stage 1 primary for quality).
3. **PaddleOCR/Tesseract** for scanned pages when no key is configured (Stage 1 fallback; quality labelled honestly per page).
4. **Disagreement handling** (prompt §8): when engines disagree materially on a region, store both outputs, compute agreement, flag the region — never silently pick one.
5. **Confidence + review routing** (prompt §13): low-confidence pages go to review, never to auto-accept.

This is not "pick Gemini and forget offline" — the offline engines are built and benchmarked in M3 regardless, because the prompt's core-works-offline rule and the deferred-key reality both demand a working no-key path.

## Decision (PROPOSED)

**Adopt the hybrid (Option C): build the `OCREngine` abstraction + digital extractor + PaddleOCR/Tesseract adapters in M3, benchmark all engines on the golden fixtures, and wire Gemini as a disabled-by-default advisory provider whose enablement awaits the owner's server-key decision. Do not provision any Gemini key, paid tier, or third-party OCR service in Phase 1 without explicit approval.**

## Consequences

- M3's benchmark report is the decision document: per-engine CER/WER on clean print, noisy scan, Urdu Nastaliq, mixed language, and the PPSC-66/table/Paper-60 fixtures, plus pages/minute and peak memory on stated hardware. If PaddleOCR Nastaliq is poor, that is reported as a measured failure, not hidden.
- The Flutter app's existing Gemini prompt (transcribe exactly, `[?]` for unreadable, left-column-first) is reused as the server prompt baseline — it is the only prompt with a measured 100/100 behind it.
- The recitation-filter mitigation (page crops) must be designed into the Gemini adapter from the start, not bolted on after the first blocked page.
- No student content leaves the server until the privacy notice + explicit configuration exist (prompt §15).

## Revisit conditions

- When the owner provides (or declines) a server Gemini key, update this ADR: key provided → Gemini becomes the Stage-1 default for scanned pages; key declined → offline-first becomes the default and Urdu-quality expectations are reset in writing.
- If the M3 benchmark shows PaddleOCR Nastaliq at or near Gemini quality on the fixtures, the default flips to offline-first (cheaper, no key, no filter).
- If a new OCR engine is benchmarked (e.g. UTRNet, Cloud Vision), add it as an adapter behind the same interface and re-run the benchmark — do not swap engines on claims.
- If Render free proves unable to run PaddleOCR at all (OOM/timeout measured in M7 load tests), the offline fallback becomes "Tesseract-only on Render; PaddleOCR on the Stage-2 VPS".
