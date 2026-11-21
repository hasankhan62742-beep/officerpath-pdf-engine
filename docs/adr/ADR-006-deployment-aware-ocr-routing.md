# ADR-006: Deployment-aware OCR routing

- **Status:** ACCEPTED (M4, 2026-11-21)
- **Context:** ADR-002 (hybrid OCR) + ADR-005 (PaddleOCR VPS-only).
  M3 measured PaddleOCR at 1,775–3,667 MB peak RSS per page with OOM
  kills (exit 137) on full-resolution phone photos, but the M3 router
  was deployment-blind: it preferred PaddleOCR whenever the package
  was available. On Render free (512 MB, ADR-001) that would OOM the
  Stage-1 service on the first scanned page.
- **Decision:** routing is deployment-aware. A deployment profile
  (`DEPLOYMENT_PROFILE`: `render-free` 512 MB / `vps` 4096 MB /
  `local` 8192 MB, overridable with `MEMORY_BUDGET_MB`) carries a
  memory budget, and PaddleOCR is selected only when the budget is
  ≥ 4 GB (`PADDLEOCR_MIN_MEMORY_MB = 4096`, set above the worst
  measured peak of 3,667 MB). The gate lives in the router
  (`app/pipeline/ocr/deployment.py` + `route_page(..., deployment=...)`)
  as defence in depth: even a registered and available PaddleOCR is
  never selected on a profile that cannot run it. Every exclusion is
  logged once per document and recorded on each page result with its
  reason — never silent. An unknown profile name raises ValueError
  (fail loudly). `render.yaml` sets `DEPLOYMENT_PROFILE=render-free`
  and `PADDLEOCR_ENABLED=false` (belt and braces: the package is not
  even registered on Render).
- **Consequences:**
  - Render free runs digital + Tesseract only (Tesseract peak
    228.7 MB < 512 MB, M3). Scanned-page quality on Stage 1 is
    Tesseract-level until a Gemini key exists — accepted, and
    recorded honestly in the M4 benchmark.
  - VPS (4 GB) runs PaddleOCR, but phone photos still need
    downscaling (M3: full-res OOM even on an 8 GB VM) — the
    downscale rule is unchanged.
  - The digital extractor and Tesseract fit every profile; they have
    no gate. Any future heavy engine gets its own gate in the same
    module, not a special case in the router.
- **Alternatives considered:**
  - `PADDLEOCR_ENABLED=false` on Render only: works, but a single
    env-var mistake re-enables an OOM. The router gate makes the
    memory budget the authority, not one flag.
  - A fixed engine list per profile: equivalent in effect, but the
    budget rule generalises to future engines and documents WHY
    (measured peak vs budget) instead of hard-coding names.
