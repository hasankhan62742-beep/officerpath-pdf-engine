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


#: M15 (Child A, measured 2026-11-24; ADR-008 addendum) — the
#: confidence-gated PSM-4 retry for the SINGLE path. The signal the
#: M2 quality metrics could not provide turned out to be Tesseract's
#: own mean word confidence: on PPSC-66 the PSM-3 per-page means
#: were p1 92.5, p2 90.2, p3 91.3, p4 88.7, p5 81.8, p6 90.5,
#: p7 89.6 — p5 alone below 85, and exactly the page M5 showed
#: wants PSM 4 (9/19 vs PSM 3's 4/19). Rule: retry a page with
#: PSM 4 when its PSM-3 mean word confidence is below the
#: threshold, and keep the retry only when its mean confidence is
#: STRICTLY higher (keep margin 0). Measured: PPSC-66 41 -> 42
#: questions, 40 -> 41 correct vs key, 0 wrong (only p5 retried;
#: PSM-4 conf 86.4 vs 81.8); table photo and Paper 60 unchanged.
#: CAVEAT: the margin-0 keep rule was chosen post-hoc (the
#: pre-registered +5 rule scored 41 — PSM-4 was +4.6, just under),
#: so it was validated on a second paper before adoption: NOA
#: Urdu MCQs (9 pp, 135-question key) showed NO change
#: (75 questions / 7 pending / 39 correct / 29 wrong, baseline
#: and retry identical — only p9 retried, PSM-4 conf equal at
#: 84.1, not kept). Applies to the single path only (PDF pages
#: AND the image path); multi-pass (M14/ADR-010) is untouched —
#: it calls _ocr_page directly with its three fixed variants.
PSM4_RETRY_CONFIDENCE_THRESHOLD = 85.0

#: PSM used for the retry pass.
PSM4_RETRY_PSM = 4

#: Keep margin (points of mean word confidence) the PSM-4 retry
#: must beat the PSM-3 result by. 0.0 = keep only if strictly
#: better (see the post-hoc caveat above).
PSM4_RETRY_KEEP_MARGIN = 0.0


def mean_word_confidence(blocks: list) -> float | None:
    """Mean Tesseract word confidence (0-100) over a page's OCR
    blocks — the exact rule Child A's ``bench_a.py`` computed from
    the TSV: every word with non-empty text and conf >= 0 counts
    once; conf -1 ("no confidence") is dropped, never averaged
    in. ``word_confidences`` on each block already carries exactly
    those words (empty words are dropped when blocks are grouped),
    so the mean over its values >= 0 reproduces the TSV mean.
    Returns None when the page has no scored words (blank page /
    OCR failure) — such a page is never retried."""
    confs: list[float] = []
    for block in blocks:
        word_confidences = getattr(block, "word_confidences", None) or {}
        for conf in word_confidences.values():
            if float(conf) >= 0:
                confs.append(float(conf))
    if not confs:
        return None
    return round(sum(confs) / len(confs), 1)


def should_retry_psm4(mean_confidence: float | None) -> bool:
    """True when a page's PSM-3 mean word confidence is below the
    retry threshold (and a mean exists at all)."""
    return mean_confidence is not None and mean_confidence < PSM4_RETRY_CONFIDENCE_THRESHOLD


def keep_psm4_retry(mean_psm3: float | None, mean_psm4: float | None) -> bool:
    """True when the PSM-4 retry's mean word confidence beats the
    PSM-3 result by more than the keep margin — i.e. strictly
    better at margin 0. Either mean missing means "do not keep"."""
    if mean_psm3 is None or mean_psm4 is None:
        return False
    return mean_psm4 > mean_psm3 + PSM4_RETRY_KEEP_MARGIN
