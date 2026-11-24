# OfficerPath AI — PDF Engine (Phase 1, M6)
# Per-page PSM selection tests (ADR-008).

from app.pipeline.interfaces import BoundingBox, OCRBlock
from app.pipeline.ocr.psm import (
    DEFAULT_PSM,
    NO_ROUTING_EVIDENCE,
    PSM4_RETRY_CONFIDENCE_THRESHOLD,
    keep_psm4_retry,
    mean_word_confidence,
    select_psm,
    should_retry_psm4,
)
from app.pipeline.pdf.quality import PageQuality


def _block(word_confs: dict[str, float]) -> OCRBlock:
    return OCRBlock(
        text=" ".join(word_confs),
        bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
        page_number=1,
        word_confidences=word_confs,
    )


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


# --- M15: confidence-gated PSM-4 retry rule (ADR-008 addendum) ---


def test_psm4_retry_threshold_is_85() -> None:
    assert PSM4_RETRY_CONFIDENCE_THRESHOLD == 85.0


def test_mean_word_confidence_averages_words_and_drops_minus_one() -> None:
    # bench_a's TSV rule: every non-empty word with conf >= 0
    # counts once; conf -1 ("no confidence") is dropped, never
    # averaged in. Two blocks: (90 + 80 + -1) and (85) -> 85.0.
    blocks = [
        _block({"a#0": 90.0, "b#1": 80.0, "c#2": -1.0}),
        _block({"d#0": 85.0}),
    ]
    assert mean_word_confidence(blocks) == 85.0


def test_mean_word_confidence_none_without_scored_words() -> None:
    assert mean_word_confidence([]) is None
    assert mean_word_confidence([_block({"a#0": -1.0})]) is None
    assert mean_word_confidence([_block({})]) is None


def test_should_retry_psm4_only_below_threshold() -> None:
    assert should_retry_psm4(81.8) is True  # PPSC-66 p5, the retried page
    assert should_retry_psm4(84.9) is True
    assert should_retry_psm4(85.0) is False  # at threshold: no retry
    assert should_retry_psm4(92.5) is False
    assert should_retry_psm4(None) is False


def test_keep_psm4_retry_needs_strictly_higher_confidence() -> None:
    # Margin 0: keep only if STRICTLY better. PPSC-66 p5 (86.4 vs
    # 81.8) is kept; an equal retry (NOA p9: 84.1 vs 84.1) is not.
    assert keep_psm4_retry(81.8, 86.4) is True
    assert keep_psm4_retry(84.1, 84.1) is False
    assert keep_psm4_retry(90.0, 86.0) is False
    assert keep_psm4_retry(None, 86.4) is False
    assert keep_psm4_retry(81.8, None) is False
