# OfficerPath AI — PDF Engine (Phase 1, M4)
# Answer detection and confidence — port of the Dart parser rules,
# spec §6.1-6.3, §6.11-6.14, §7.
#
# Sources: mcq_parser.dart:4332-4420, 5030-5080, question.dart:160-260.

from __future__ import annotations

import re
from collections.abc import Callable

from app.pipeline.extract.markers import (
    has_asterisk,
    has_tick,
    strip_asterisks,
    strip_ticks,
)

#: Spec §6.2: explicit answer line.
ANSWER_LINE_RE = re.compile(
    r"^(?:Final\s+Answers?|(?:Correct|Right)\s+Answers?|Answer\s+Keys?"
    r"|Correct|Right|Answers?|Ans|Key)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)
#: Spec §6.3: bare answer line — a lone ``(c)`` / ``C`` / ``3``.
BARE_ANSWER_RE = re.compile(r"^[\(\[]?\s*([A-Da-d1-4])\s*[\)\]]?\s*$")
#: Spec §6.15: inline answer (Q-only) — ``Q ... Ans: X``.
INLINE_ANSWER_RE = re.compile(
    r"\b((?:correct|right)\s+answers?|correct|right|ans|answer|key)"
    r"\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)

#: Spec §7.1: per-question confidence by source.
CONFIDENCE_FOR_SOURCE: dict[str, float] = {
    "answer-line": 1.0,
    "key": 1.0,
    "tick": 0.9,
    "bold": 0.9,
    "asterisk": 0.9,
    "flashcard": 0.9,
    "manual": 1.0,
    "ai": 0.5,
    "": 0.0,
}

#: Spec §7.2: verified sources. ``flashcard`` is explicitly NOT
#: verified (a q-only question's options are GENERATED from the answer
#: pool — the book printed no A-D mark on them).
VERIFIED_SOURCES: frozenset[str] = frozenset({"answer-line", "key", "tick", "bold", "asterisk"})

#: Spec §6.1: precedence, highest first.
PRECEDENCE: tuple[str, ...] = (
    "answer-line",
    "key",
    "tick",
    "bold",
    "asterisk",
)


def confidence_for_source(source: str, verified: bool = True) -> float:
    """Spec §7.1. Unverified -> base x 0.6 (clamped 0-1). Never 1.0
    for a mark."""
    base = CONFIDENCE_FOR_SOURCE.get(source, 0.0)
    if not verified:
        base *= 0.6
    return max(0.0, min(1.0, base))


def verification_status(
    correct_index: int,
    verified: bool,
    source: str,
    manually_corrected: bool = False,
) -> str:
    """Spec §7.4: ``no-answer`` / ``verified`` / ``unverified`` /
    ``manually-corrected``."""
    if manually_corrected:
        return "manually-corrected"
    if correct_index == -1:
        return "no-answer"
    if verified and source in VERIFIED_SOURCES:
        return "verified"
    return "unverified"


def apply_ocr_provenance(
    answer_source: str, verified: bool, confidence: float, provenance: str
) -> tuple[bool, float]:
    """Spec §7.3. When provenance is ``ocr`` AND the answer source is
    ``tick``/``bold``, the question is rewritten UNVERIFIED with
    confidence ``0.9 x 0.6 = 0.54``. An asterisk, key or answer line
    is printed text, not a pen mark, so it stays verified even on an
    OCR page."""
    if provenance == "ocr" and answer_source in ("tick", "bold"):
        return False, 0.54
    return verified, confidence


def extract_option_signals(text: str) -> dict[str, bool]:
    """Per-option printed/visual signals from one option's raw text
    (before stripping). Bold is read from the extractor's U+E000
    marker (spec §3.4); tick/asterisk from the text itself."""
    from app.pipeline.extract.markers import BOLD_MARKER

    return {
        "bold": BOLD_MARKER in text,
        "tick": has_tick(text),
        "asterisk": has_asterisk(text),
    }


def clean_option_text(text: str) -> str:
    """Stored option text: ticks and asterisks stripped, bold marker
    removed, trimmed (spec §3.3/§3.5/§3.6)."""
    from app.pipeline.extract.markers import BOLD_MARKER, clean_stored

    cleaned = strip_ticks(text)
    cleaned = strip_asterisks(cleaned)
    return clean_stored(cleaned.replace(BOLD_MARKER, ""))


def resolve_signals(
    option_signals: list[dict[str, bool]],
    answer_line_token: str | None,
    key_index: int | None,
    options: list[str],
    resolve_token: Callable[[str, list[str]], int | None] | None = None,
) -> tuple[int, str, list[str]]:
    """Spec §6.1/§6.11-6.13. Precedence: answer-line > key > tick >
    bold > asterisk. When signals conflict, the higher-precedence one
    wins and the conflict is recorded — never silently resolved.
    Returns (correct_index, answer_source, conflicts). ``-1`` /
    ``""`` when no signal resolves. ``resolve_token`` is
    ``keys.resolve_answer_token`` (passed in to avoid a circular
    import)."""
    conflicts: list[str] = []
    candidates: dict[str, int] = {}

    if answer_line_token is not None and resolve_token is not None:
        resolved = resolve_token(answer_line_token, options)
        if resolved is not None:
            candidates["answer-line"] = resolved
    if key_index is not None:
        candidates["key"] = key_index
    for kind in ("tick", "bold", "asterisk"):
        marked = [i for i, sig in enumerate(option_signals) if sig.get(kind)]
        if len(marked) == 1:
            candidates[kind] = marked[0]
        elif len(marked) > 1:
            letters = ", ".join(chr(65 + i) for i in marked)
            conflicts.append(
                f"{len(marked)} options are {kind} "
                f"({letters}) — {kind} signal ignored, answer still needed."
                if kind == "bold"
                else f"{len(marked)} options are {kind}-marked "
                f"({letters}) — {kind} signal ambiguous."
            )
    for source in PRECEDENCE:
        if source in candidates:
            winner = candidates[source]
            for other_source, other_index in candidates.items():
                if other_source != source and other_index != winner:
                    conflicts.append(
                        f"answer conflict: {source} says "
                        f"{chr(65 + winner)}, {other_source} says "
                        f"{chr(65 + other_index)} — {source} wins."
                    )
            return winner, source, conflicts
    return -1, "", conflicts


def final_answer_value_conflict(letter_index: int, value: str, options: list[str]) -> str | None:
    """Spec §6.14. For ``Final Answer: (X) <value>``, the trailing
    value should be the letter's option text. If it exactly matches a
    DIFFERENT option's text, a conflict is recorded but the LETTER
    still wins. The value trim is Unicode-aware (``\\p{L}``) — an
    Urdu answer value ending in an Arabic-script letter must not be
    stripped as punctuation."""
    value_clean = re.sub(r"[^\w]+$", "", value.strip(), flags=re.UNICODE)
    if not value_clean:
        return None
    for i, option in enumerate(options):
        if i != letter_index and option.strip().lower() == value_clean.lower():
            return (
                f"final-answer value '{value_clean}' matches option "
                f"{chr(65 + i)} but the letter says {chr(65 + letter_index)}"
                " — letter wins."
            )
    return None
