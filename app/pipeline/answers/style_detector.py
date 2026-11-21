# OfficerPath AI — PDF Engine (Phase 1, M5)
# Digital-style detector: printed marks in the text layer.
#
# Three mark kinds, one rule each — exactly ONE marked option is
# an answer; zero is no evidence; more than one is ambiguous and
# the signal is REJECTED with the reason recorded (never resolved
# by guessing which mark counts):
# - bold option: the U+E000 bold marker the M4 digital extractor
#   appends per ``style["bold_lines"]`` (spec D17). OCR pages
#   carry no bold info — bold is NEVER approximated from OCR text.
# - star: a trailing ``*`` on the option text (Paper 60: ``(C)
#   F5*``, ``(C) UDP *`` — the space before the star is allowed).
# - tick: a ``✓``/``✔`` character in the option text (printed
#   tick, not a pen mark — pen marks are the visual detector's
#   job).
#
# Confidence follows spec §7.1: 0.9 for a printed mark; on an OCR
# page a tick/bold mark is rewritten UNVERIFIED at 0.54
# (``apply_ocr_provenance`` — a star is printed text, so it stays
# verified even on an OCR page).

from __future__ import annotations

from app.pipeline.answers.models import AnswerEvidence
from app.pipeline.extract.signals import (
    apply_ocr_provenance,
    extract_option_signals,
)

#: Mark kinds this detector reads, in the order they are checked.
MARK_KINDS: tuple[str, ...] = ("bold", "tick", "asterisk")

#: Detector name per mark kind.
DETECTOR_FOR_KIND: dict[str, str] = {
    "bold": "style-bold",
    "tick": "style-bold",
    "asterisk": "style-star",
}


def detect_style_marks(
    question_number: int | None,
    raw_options: list[str],
    *,
    is_ocr: bool = False,
) -> list[AnswerEvidence]:
    """Detect printed style marks on one question's raw option
    texts (markers NOT yet stripped — the U+E000 bold marker, ``*``
    and tick characters must still be present). Returns one
    evidence per mark kind: a firing evidence (correct_index >= 0)
    when exactly one option carries the mark, a rejection evidence
    (correct_index -1) when the mark is ambiguous, nothing when
    the mark is absent."""
    if len(raw_options) != 4:
        return []
    signals = [extract_option_signals(text) for text in raw_options]
    evidences: list[AnswerEvidence] = []
    for kind in MARK_KINDS:
        marked = [i for i, sig in enumerate(signals) if sig.get(kind)]
        if not marked:
            continue
        detector = DETECTOR_FOR_KIND[kind]
        if len(marked) > 1:
            letters = ", ".join(chr(65 + i) for i in marked)
            evidences.append(
                AnswerEvidence(
                    detector=detector,
                    question_number=question_number,
                    correct_index=-1,
                    confidence=0.0,
                    evidence=(
                        f"{len(marked)} options are {kind}-marked ({letters}) — "
                        f"{kind} signal ambiguous, ignored."
                    ),
                    detail={"mark_kind": kind, "marked": marked, "rejected": True},
                )
            )
            continue
        index = marked[0]
        provenance = "ocr" if is_ocr else "printed"
        # Spec §7.3: OCR tick/bold -> unverified 0.54; a star stays
        # verified (printed text, not a pen mark).
        verified, confidence = apply_ocr_provenance(
            "tick" if kind == "tick" else kind, True, 0.9, provenance
        )
        evidences.append(
            AnswerEvidence(
                detector=detector,
                question_number=question_number,
                correct_index=index,
                confidence=round(confidence, 3),
                evidence=(
                    f"option ({chr(65 + index)}) is {kind}-marked "
                    f"({provenance}, confidence {confidence})"
                ),
                detail={"mark_kind": kind, "marked": [index], "verified": verified},
            )
        )
    return evidences


def detect_bold_option(
    question_number: int | None,
    raw_options: list[str],
    *,
    is_ocr: bool = False,
) -> AnswerEvidence | None:
    """Bold-option detection only (convenience wrapper)."""
    for evidence in detect_style_marks(question_number, raw_options, is_ocr=is_ocr):
        if evidence.detector == "style-bold" and evidence.detail.get("mark_kind") == "bold":
            return evidence
    return None


def detect_star_option(
    question_number: int | None,
    raw_options: list[str],
    *,
    is_ocr: bool = False,
) -> AnswerEvidence | None:
    """Star-marked-option detection only (convenience wrapper)."""
    for evidence in detect_style_marks(question_number, raw_options, is_ocr=is_ocr):
        if evidence.detector == "style-star":
            return evidence
    return None
