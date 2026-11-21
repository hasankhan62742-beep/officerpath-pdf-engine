# OfficerPath AI — Phase 1, M5
# Digital-style detector tests: bold / tick / star marks in the
# text layer. Exactly one marked option is an answer; zero is no
# evidence; more than one is ambiguous and rejected.

from app.pipeline.answers.style_detector import (
    detect_bold_option,
    detect_star_option,
    detect_style_marks,
)
from app.pipeline.extract.markers import BOLD_MARKER

PLAIN = ["Alpha", "Beta", "Gamma", "Delta"]


def test_star_mark_fires_on_exactly_one_option() -> None:
    options = ["F1", "F2", "F5*", "F10"]
    evidence = detect_star_option(1, options)
    assert evidence is not None
    assert evidence.correct_index == 2
    assert evidence.detector == "style-star"
    assert evidence.confidence == 0.9


def test_star_with_space_before_it_fires() -> None:
    # Paper 60 Q4: "(C) UDP *" — the space is allowed.
    options = ["ISDN", "Modem", "UDP *", "DSL"]
    evidence = detect_star_option(4, options)
    assert evidence is not None
    assert evidence.correct_index == 2


def test_no_star_is_no_evidence() -> None:
    assert detect_star_option(1, PLAIN) is None


def test_two_stars_is_ambiguous_rejection() -> None:
    evidences = detect_style_marks(1, ["A*", "B*", "C", "D"])
    assert len(evidences) == 1
    assert evidences[0].correct_index == -1
    assert "ambiguous" in evidences[0].evidence


def test_bold_option_fires_from_u_e000_marker() -> None:
    options = ["Alpha", "Beta" + BOLD_MARKER, "Gamma", "Delta"]
    evidence = detect_bold_option(1, options)
    assert evidence is not None
    assert evidence.correct_index == 1
    assert evidence.detector == "style-bold"
    assert evidence.confidence == 0.9


def test_bold_on_ocr_page_is_unverified_054() -> None:
    options = ["Alpha", "Beta" + BOLD_MARKER, "Gamma", "Delta"]
    evidence = detect_bold_option(1, options, is_ocr=True)
    assert evidence is not None
    assert evidence.correct_index == 1
    assert evidence.confidence == 0.54
    assert evidence.detail["verified"] is False


def test_star_on_ocr_page_stays_verified() -> None:
    # A star is printed text, not a pen mark (spec §7.3).
    options = ["F1", "F2", "F5*", "F10"]
    evidence = detect_star_option(1, options, is_ocr=True)
    assert evidence is not None
    assert evidence.confidence == 0.9
    assert evidence.detail["verified"] is True


def test_tick_mark_fires() -> None:
    options = ["Alpha ✓", "Beta", "Gamma", "Delta"]
    evidences = detect_style_marks(1, options)
    tick = [e for e in evidences if "tick" in e.evidence]
    assert len(tick) == 1
    assert tick[0].correct_index == 0


def test_wrong_option_count_is_no_detection() -> None:
    assert detect_style_marks(1, ["A*", "B"]) == []
