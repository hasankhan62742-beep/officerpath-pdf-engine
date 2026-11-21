# ADR-004 — PDF + preprocessing libraries: PyMuPDF, OpenCV-headless, Pillow, NumPy; pdfplumber deferred

- **Status:** DECIDED in M2 (2026-11-21)
- **Deciders:** Phase 1 M2 (owner approved ADR-001 + ADR-002 on 2026-11-21)
- **Context source:** Ultimate Master Prompt §5.5 (verify version compatibility,
  licence, install size, CPU/RAM, Windows/Linux/Docker behaviour before
  committing), §6–§7 (PDF analysis, rendering, adaptive preprocessing);
  v2 §3–§5 (same).

## Decision

M2 adopts, all pinned in `requirements.txt`:

| Library | Version | Licence | Installed size | Role |
|---|---|---|---|---|
| PyMuPDF | 1.26.3 | AGPLv3 (dual: AGPL or commercial) | ~25 MB wheel | PDF analysis (text/images/fonts), rendering |
| opencv-python-headless | 4.11.0.86 | Apache 2.0 | ~74 MB | Quality metrics, deskew, denoise, CLAHE, threshold |
| Pillow | 13.0.0 | MIT-CMU | ~7 MB | Image normalisation (image files -> PNG) |
| NumPy | 2.3.2 | BSD | ~43 MB | Array math under OpenCV/Pillow |

## Licence note — PyMuPDF is AGPLv3 (flagged, not hidden)

PyMuPDF is dual-licensed AGPLv3 or commercial (Artifex). AGPL §13
covers offering the software over a network: a network service built
on AGPL code must offer its source to users. For OfficerPath AI that
means: **as long as PyMuPDF is in the engine, the engine source must
stay available to its users** — which it already is (the repo is
public, `hasankhan62742-beep/officerpath-pdf-engine`). The exposure is
therefore limited today, but it is a real constraint on any future
closed-source distribution of the engine. Alternatives were evaluated:

- **pdfplumber / pdfminer.six (MIT):** text extraction only — no
  rendering. It cannot replace PyMuPDF for page rendering.
- **pypdf (BSD):** text/metadata only — no rendering either.
- **Poppler / pdf2image (GPL):** same copyleft family as AGPL for
  practical purposes, plus a system dependency in Docker.
- **Commercial PyMuPDF licence:** paid — ruled out by cost discipline
  (no paid services without owner approval).

**Revisit condition:** if the engine is ever distributed closed-source,
replace PyMuPDF (rendering) before that release, or buy the commercial
licence. Until then the AGPL is accepted with the repo public.

## pdfplumber: evaluated, DEFERRED to M3 (not rejected)

pdfplumber (MIT, pdfminer.six underneath) adds char-level text detail
and table extraction on top of what PyMuPDF already gives (words,
spans, fonts, image bboxes). For M2's scope — analysis, classification,
rendering, preprocessing — it adds nothing PyMuPDF does not already
provide, so installing it now would be a speculative dependency
(prompt §5.5: do not install libraries speculatively). It is the
first candidate for M3 layout/table work, where its table extraction
is genuinely useful; that decision is M3's, with its own benchmark.

## Install / Docker behaviour (VERIFIED on the dev VM)

- All four install as manylinux wheels on Python 3.12 / x86-64 Linux —
  no compiler, no system libraries. `opencv-python-headless` needs no
  libGL (the non-headless package does, and is NOT used).
- The `python:3.12-slim` Docker image therefore needs NO new apt
  packages for M2 (UNVERIFIED in Docker itself — no Docker on the VM;
  the first CI Docker build after the push verifies it).
- Total added install size: ~150 MB of wheels (~74 MB OpenCV).
  That matters for Render (ephemeral disk, cold-start image pull) and
  is recorded, not hidden.

## Render envelope consequences (measured, VM numbers)

Fresh-process peak RSS (interpreter + imports ~124 MB included),
measured 2026-11-21 on the 4-vCPU VM — VM numbers, NOT Render numbers
(Render free is 0.1 CPU / 512 MB; expect several-times-slower times):

| Page type | Time/page | Peak RSS |
|---|---|---|
| clean digital (2 pp.) | 0.60 s | 275 MB |
| scanned | 0.93 s | ~300 MB |
| skewed (low_quality) | 4.17 s | 316 MB |
| low-contrast (low_quality) | 3.61 s | 285 MB |
| noisy (low_quality, 2 profiles) | 8.62 s | 325 MB |
| blank | 0.37 s | ~200 MB |
| PPSC-66 real pages | 0.75–0.86 s | 192 MB |

Two calibration changes came out of these measurements (see the M2
report for the numbers): (1) upscaling was REMOVED from the
`low_quality` profile — upscaling a 200-DPI A4 page 1.5x before
denoising pushed peak RSS to ~457 MB, too close to Render's 512 MB
for a Stage-1 default; the operation still exists for per-page use,
pending M3 OCR evidence. (2) The noise metric was redefined twice —
whole-page high-frequency energy scored clean print as "noisy", and a
flat-block filter excluded exactly the noisy blocks; the shipped
metric is a median-absolute-deviation estimate dominated by paper
background.

## Consequences

- M3 builds the OCR adapters on top of these renders (colour PNG at
  200 DPI + the processed grayscale + the recorded profile/quality).
- M7 must run preprocessing in a worker with a memory guard and a
  per-page time budget: the 8.6 s noisy page on a 4-vCPU VM will be
  much slower on Render's 0.1 CPU, and two profiles double the cost.
- The `low_quality` profile's binarisation inflates contrast/blur
  metrics, so the two-profile comparison score currently favours it;
  whether binarisation helps OCR is an M3 benchmark question, not
  decided here.

## Revisit conditions

- If the CI Docker build fails on a missing system library, add the
  minimal apt package and record it here.
- If M3 shows PyMuPDF rendering is the bottleneck, re-evaluate
  Poppler/pdfplumber for the render path (licence note above applies).
- If Render free cannot hold a ~325 MB preprocessing peak alongside
  the API server, preprocessing moves to a separate worker process
  (M7) or the Stage-2 VPS (ADR-001).
