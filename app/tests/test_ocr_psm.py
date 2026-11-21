# OfficerPath AI — PDF Engine (Phase 1, M6)
# Per-page PSM selection tests (ADR-008).

from app.pipeline.ocr.psm import DEFAULT_PSM, NO_ROUTING_EVIDENCE, select_psm
from app.pipeline.pdf.quality import PageQuality


def test_select_psm_returns_measured_best_default() -> None:
    assert select_psm(None) == 3
    assert DEFAULT_PSM == 3


def test_select_psm_does_not_route_on_quality_that_does_not_separate() -> None:
    # The two M5 anchor pages: p3 wants PSM 3, p5 wants PSM 4, but
    # their measured quality is nearly identical — so NO quality
    # rule may separate them. select_psm must not pretend otherwise
    # by returning different PSMs for these two quality vectors.
    p3 = PageQuality(blur_score=2480.9, contrast_score=65.1, ink_coverage=0.099)
    p5 = PageQuality(blur_score=2002.8, contrast_score=60.6, ink_coverage=0.087)
    assert select_psm(p3) == select_psm(p5) == 3


def test_no_routing_evidence_quotes_measured_numbers() -> None:
    assert NO_ROUTING_EVIDENCE["p3_psm3_recovered_of_19"] == 16
    assert NO_ROUTING_EVIDENCE["p5_psm4_recovered_of_19"] == 9
    assert "do not separate" in NO_ROUTING_EVIDENCE["conclusion"]
