# OfficerPath AI — PDF Engine (Phase 1, M6)
# Per-page Tesseract PSM selection (ADR-008).
#
# The M6 task asked for PSM routing driven by measured page
# quality. The measured evidence says NO quality rule is
# justified, so none is fitted:
#
# - M5 measured per-page PSM on PPSC-66 p3 vs p5 (the two pages
#   where the PSMs disagree): p3 PSM 3 recovers 16/19 (CER
#   0.0623), PSM 4 only 7/19 (CER 0.7006); p5 PSM 3 recovers 4/19
#   (CER 0.7149), PSM 4 9/19 (CER 0.1397). Per-page PSM matters.
# - But the M2 quality metrics do NOT separate the pages
#   (BENCHMARK_M5, "Page quality does NOT explain the p3/p5
#   difference"): blur 2480.9 vs 2002.8, contrast 65.1 vs 60.6,
#   ink 0.099 vs 0.087 — nearly identical. The difference is
#   CONTENT (Urdu + column merge), not quality.
#
# Fitting a threshold to two nearly-identical points would be
# overfitting to noise: any threshold between them "works" on
# the two anchor pages and has no reason to work on a third.
# So select_psm() deliberately returns the measured-best
# single-path PSM (3) for every page, and records WHY. The
# function is the per-page routing hook — when a discriminating
# signal is measured (the M7 candidate is a confidence-gated
# retry: OCR once with PSM 3, retry low-confidence pages with
# PSM 4), the rule changes here and only here, with its own
# measured before/after. Until then, "routed" and "unrouted"
# PPSC-66 recovery are the same number, and the M6 benchmark
# says so instead of inventing a gain.

from __future__ import annotations

from app.pipeline.pdf.quality import PageQuality

#: The measured-best single-path PSM on PPSC-66 (M5 full run:
#: PSM 3 layout 41/100 vs PSM 4 raw 15/100).
DEFAULT_PSM = 3

#: Why no quality rule is fitted (ADR-008). Kept as data so the
#: benchmark and the report can quote it instead of re-deriving it.
NO_ROUTING_EVIDENCE = {
    "p3_blur": 2480.9,
    "p5_blur": 2002.8,
    "p3_contrast": 65.1,
    "p5_contrast": 60.6,
    "p3_ink": 0.099,
    "p5_ink": 0.087,
    "p3_psm3_recovered_of_19": 16,
    "p3_psm4_recovered_of_19": 7,
    "p5_psm3_recovered_of_19": 4,
    "p5_psm4_recovered_of_19": 9,
    "conclusion": (
        "M2 quality metrics do not separate p3 (wants PSM 3) from "
        "p5 (wants PSM 4); content (Urdu + column merge) does. "
        "No quality threshold is fitted."
    ),
}


def select_psm(quality: PageQuality | None) -> int:
    """Select the Tesseract PSM for one page from its measured
    quality. Currently always DEFAULT_PSM (3): the M5 evidence
    (see module docstring / ADR-008) shows no M2 quality metric
    separates the pages that want different PSMs, so a threshold
    would be overfitting to two points. ``quality`` is accepted
    (and may be None) so callers route per page through this one
    hook when a real signal is measured."""
    return DEFAULT_PSM
