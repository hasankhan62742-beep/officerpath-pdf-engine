# OfficerPath AI — PDF Engine (Phase 1, M4)
# Option-marker detection, splitting and sanitisation — port of the
# Dart parser rules, spec §2-§3.
#
# Sources: mcq_parser.dart:3994-4330, 4737-4767, 5048-5182,
# answer_key.dart:405-534.

from __future__ import annotations

import re

from app.pipeline.extract.numbers import normalize_urdu_digits

#: Private-use bold-run marker (spec §3.4). Appended by the extractor
#: at the END of a bold text run; consumed by the parser, never stored.
BOLD_MARKER = "\ue000"

#: Question terminators (spec §11.1: ``؟`` counts as ``?`` everywhere).
QUESTION_MARKS = ("?", "؟")

# Spec §3.7: ligatures U+FB00-FB06.
LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
_LIGATURE_RE = re.compile("[" + "".join(LIGATURE_MAP) + "]")


def normalize_ligatures(text: str) -> str:
    """Spec §3.7. Idempotent."""
    return _LIGATURE_RE.sub(lambda m: LIGATURE_MAP[m.group(0)], text)


def clean_stored(text: str) -> str:
    """Spec §3.3. The whole sanitiser for stored text: strip the bold
    marker U+E000 and surrounding whitespace. Nothing else."""
    return text.replace(BOLD_MARKER, "").strip()


# Spec §2.2: option-line markers (own line). Misread digits 8/0 match
# ONLY parenthesised — a bare ``8.`` is a question number (Q8), never
# an option marker.
OPTION_RE = re.compile(r"^\(?([A-Da-d])[\)\.\:\-]\s*(.+)$|^\(([80])[\)]\s*(.+)$")
# Spec §2.3: 5th option marker (E) — used ONLY inside the standard
# block after A-D are already collected, so ``E. coli`` is never an
# option.
OPTION_E_RE = re.compile(r"^\(?([Ee])[\)\.\:\-]\s*(.+)$")
# Spec §2.4: inline markers (one-liner). Roman numerals before single
# letters so ``iv`` wins over ``i``.
INLINE_MARKER_RE = re.compile(r"[\(\[]?\s*(iv|iii|ii|i|[a-dA-D]|[1-4])\s*[\)\.\:]", re.IGNORECASE)
# Spec §2.11 / §9.5: table key letters — a standalone letter on its
# own line (E included: a 5-option table's key can be E).
TABLE_KEY_LETTER_RE = re.compile(r"^\(?\s*([A-Ea-e])\s*[\)\.\:]?\s*$")

# Spec §2.8: function words that let a wrapped option continue.
FUNCTION_WORDS: frozenset[str] = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "but",
        "not",
        "both",
        "at",
        "by",
        "as",
        "from",
        "that",
        "which",
        "who",
        "when",
        "where",
    ]
)

#: Spec §3.9: question-word guard prefixes (``hat|hich|ho|...``).
QUESTION_WORD_PREFIXES: tuple[str, ...] = (
    "hat",
    "hich",
    "ho",
    "hom",
    "hose",
    "hen",
    "here",
    "hy",
    "ow",
    "ame",
)


def decode_ocr_option_letter(char: str) -> str | None:
    """Spec §2.5: ``8`` -> B, ``0`` -> D only. ``4`` is NEVER decoded:
    it is both a valid option number (4th option = D) and a misread
    of A."""
    if char == "8":
        return "B"
    if char == "0":
        return "D"
    if char.upper() in "ABCD":
        return char.upper()
    return None


# Spec §2.2a (A1): radio-button option markers — a printed circle
# OCRs as a glyph, not a letter: "© 274", "@ 364.50", "O None Of
# These" (NOA Maths scan). The set is the shapes Tesseract returns
# for filled/empty circles. "O" counts only as a SINGLE glyph
# followed by whitespace — "Of ..."/"On ..." never match.
SYMBOL_OPTION_RE = re.compile(r"^([©@O○●◉◎◯])\s+(.+)$")
# No-space form: Tesseract sometimes drops the gap before a numeric
# option ("@171", "O8"). The digit-led guard keeps a prose line such
# as "O2 is a gas" (number + words) from matching.
SYMBOL_OPTION_NOSPACE_RE = re.compile(r"^([©@O○●◉◎◯])(\d[\d.,%]*\s*[a-zA-Z°]*)$")


def symbol_option_match(line: str) -> str | None:
    """Match a symbol-marked option on its own line. Returns the
    option text, or None. The glyph carries no letter — the caller
    assigns options positionally (1st = A, 2nd = B, ...)."""
    match = SYMBOL_OPTION_RE.match(line.strip())
    if not match:
        match = SYMBOL_OPTION_NOSPACE_RE.match(line.strip())
    if not match:
        return None
    text = match.group(2).strip()
    return text or None


def option_line_match(line: str) -> tuple[str, str] | None:
    """Match an option on its own line. Returns (letter, rest) with
    misread digits decoded, or None. The single extraction site reads
    group 2 ?? group 4 (spec §2.2)."""
    match = OPTION_RE.match(normalize_urdu_digits(line.strip()))
    if not match:
        return None
    if match.group(1) is not None:
        return match.group(1).upper(), match.group(2)
    letter = decode_ocr_option_letter(match.group(3))
    if letter is None:
        return None
    return letter, match.group(4)


def split_option_line(line: str) -> list[tuple[str, str]] | None:
    """Spec §2.6. Split a line carrying several options
    (``(A) 1941 (B) 1942``). The marker must start at a word boundary
    (start of line, whitespace, ``(``, ``,``, ``;``). Returns None
    when: fewer than 2 markers; markers are not a consecutive run;
    a non-empty prefix does not open the set at A; any option text is
    empty; or more than 4 options. OCR-misread markers (8/0) are
    decoded BEFORE the consecutiveness check."""
    marker_re = re.compile(
        r"(?:^|[\s\(,;])\(?\s*([A-Da-d])\s*[\)\.\:\]]"
        r"|(?:^|[\s,;])\(([80])\s*[\)\.\:]"
    )
    text = normalize_urdu_digits(line)
    matches = list(marker_re.finditer(text))
    if len(matches) < 2 or len(matches) > 4:
        return None
    letters: list[str] = []
    starts: list[int] = []
    for match in matches:
        if match.group(1) is not None:
            letter = match.group(1).upper()
            start = match.start()
        else:
            letter = decode_ocr_option_letter(match.group(2)) or ""
            start = match.start()
        letters.append(letter)
        starts.append(start)
    # Consecutive run: A,B / B,C / A,B,C,D ...
    expected = [chr(ord(letters[0]) + i) for i in range(len(letters))]
    if letters != expected:
        return None
    # A non-empty prefix must open the set at A (a bare two-option
    # line ``(C) 1944 (D) 1946`` may start at any letter).
    prefix = text[: starts[0]].strip()
    if prefix and letters[0] != "A":
        return None
    options: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        end = starts[i + 1] if i + 1 < len(matches) else len(text)
        # The option text starts after the marker itself.
        marker_end = match.end()
        option_text = text[marker_end:end]
        option_text = re.sub(r"[\s,;]+$", "", option_text).strip()
        if not option_text:
            return None
        options.append((letters[i], option_text))
    return options


def is_option_continuation(last_option_text: str, line: str) -> bool:
    """Spec §2.8. Line <= 80 chars; the last option must be an open
    sentence (no terminal ``[.!?:;]``); the line must start lowercase
    OR the last option must end with a function word."""
    if len(line) > 80:
        return False
    if not last_option_text:
        return False
    if re.search(r"[.!?:;]\s*$", last_option_text):
        return False
    if line and line[0].islower():
        return True
    last_word = last_option_text.strip().split()[-1].lower().strip(".,;:!?")
    return last_word in FUNCTION_WORDS


def normalise_five_options(
    options: list[str], correct_index: int
) -> tuple[list[str], int, str] | None:
    """Spec §2.10. Answer A-D -> drop E (usually "None"); answer E ->
    keep E's text as the 4th option, drop D. Returns
    (options, correct_index, dropped_letter) or None when there is no
    usable answer (a 5-option candidate with NO answer cannot become
    a pending question — it stays excluded)."""
    if len(options) != 5:
        return None
    if correct_index < 0 or correct_index > 4:
        return None
    if correct_index == 4:
        return options[:3] + [options[4]], 3, "E"
    return options[:4], correct_index, "E" if correct_index < 4 else "D"


# --- ticks / asterisks (spec §3.5, §3.6, §6.11, §6.13) ---------------

TICK_CHARS = ("✓", "✔")
_ASTERISK_TAIL_RE = re.compile(r"\*\s*[.,;:\)]?\s*$")
_TRAILING_ASTERISK_RE = re.compile(r"\*\s*([.,;:\)]?)\s*$")


def has_tick(text: str) -> bool:
    """Spec §6.11: tick before or after the option text."""
    return any(ch in text for ch in TICK_CHARS)


def strip_ticks(text: str) -> str:
    """Spec §3.5."""
    return text.replace("✓", "").replace("✔", "").strip()


def strip_leading_tick(line: str) -> str:
    """Spec §3.5: ``✓ B) China``, ``✔ B) China``, ``(✓) B) China``."""
    stripped = line.strip()
    stripped = re.sub(r"^\(\s*[✓✔]\s*\)\s*", "", stripped)
    stripped = re.sub(r"^[✓✔]\s*", "", stripped)
    return stripped


def has_asterisk(text: str) -> bool:
    """Spec §6.13: trailing ``*`` at the END of an option's text,
    with or without a space before it and one trailing punctuation
    mark after it."""
    return bool(_ASTERISK_TAIL_RE.search(text))


def strip_asterisks(text: str) -> str:
    """Spec §3.6. A trailing ``*`` (with optional space before,
    optional one trailing punctuation mark after) is removed;
    ``HTML*`` -> ``HTML``, ``F5 *`` -> ``F5``, ``Flaming.*`` ->
    ``Flaming.``. A ``*`` in the MIDDLE (``2 * 3 = 6``) is never a
    marker and never stripped."""
    return _TRAILING_ASTERISK_RE.sub(r"\1", text).strip()


# --- noise / defects / explanations (spec §3.12-3.16) -----------------

_BARE_DIGIT_RE = re.compile(r"^\d{1,4}$")
_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)\.]+$")
_PAPERS_HEADER_RE = re.compile(r"^papers of \d{4}\s+\d+", re.IGNORECASE)
_VOLUME_RE = re.compile(r"^\d+\s+.*\(volume \d+\)", re.IGNORECASE)
EXPLANATION_HEADING_RE = re.compile(
    r"^\s*(?:[-•–—]\s*)?(explanation|associated information)\s*:?\s*$",
    re.IGNORECASE,
)
NOTE_RE = re.compile(r"^\(?\s*note\s*[:\-]\s*(.+)\)?\s*$", re.IGNORECASE)
DEFECT_OPTION_RE = re.compile(
    r"\[\s*(cut\s*off|missing|illegible|not\s*clear|unreadable|damaged"
    r"|torn|blurred|incomplete)\s*\]",
    re.IGNORECASE,
)
_CANNOT_DETERMINE_RE = re.compile(
    r"(could not (be )?determine|cannot (be )?determine|not determinable)",
    re.IGNORECASE,
)
PAGE_FOOTER_RE = re.compile(r"page\s*\d+(\s*of\s*\d+)?\s*$", re.IGNORECASE)


def is_noise_line(line: str) -> bool:
    """Spec §3.12. Bare digit line; promo lines; running headers;
    bare phone-number lines. (The >= 3 numeric-option-run exception
    is handled by the caller via :func:`is_numeric_option_run`.)"""
    text = line.strip()
    if not text:
        return True
    if _BARE_DIGIT_RE.match(text):
        return True
    lowered = text.lower()
    if "like" in lowered and "follow" in lowered and "facebook" in lowered:
        return True
    if "for more informative material" in lowered:
        return True
    if _PAPERS_HEADER_RE.match(text) or _VOLUME_RE.match(text):
        return True
    digits = sum(c.isdigit() for c in text)
    return bool(digits >= 7 and _PHONE_RE.match(text) and not any(c.isalpha() for c in text))


def is_numeric_option_run(lines: list[str], index: int) -> bool:
    """Spec §3.12 exception: a run of >= 3 consecutive bare-digit
    lines is a numeric option set (``3/4/5/6``), not page numbers,
    and is kept for the table pass."""
    run = 0
    i = index
    while i < len(lines) and _BARE_DIGIT_RE.match(lines[i].strip()):
        run += 1
        i += 1
    return run >= 3


def is_foreign_script_noise_block(text: str) -> bool:
    """Spec §3.13. A block with no question/option/answer structure
    whose letters are majority non-Latin, non-Arabic script (Bengali,
    U+0980-U+09FF). Urdu/Arabic-script content is NEVER noise."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    bengali = sum(1 for c in letters if "\u0980" <= c <= "\u09ff")
    return bengali > len(letters) / 2


def defect_reason(lines: list[str]) -> str | None:
    """Spec §3.14. Defective questions are EXCLUDED with the book's
    own reason, never guessed, never silently dropped."""
    for line in lines:
        match = DEFECT_OPTION_RE.search(line)
        if match:
            return f"defective: {match.group(0)}"
    for line in lines[1:]:
        if _CANNOT_DETERMINE_RE.search(line):
            return "defective: could not determine"
    return None


def strip_answer_tail(text: str) -> str:
    """Spec §3.10: remove a trailing ``Ans: ...`` / ``Answer: ...`` /
    ``Correct: ...`` tail from question text — the text is CUT at
    the start of the marker (``_stripAnswerTail`` returns
    ``substring(0, idx)``), so the marker AND its value go."""
    match = re.search(
        r"\b((?:correct|right)\s+answers?|ans|answer|correct)\s*[:\-]",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return text.strip()
    return text[: match.start()].strip()


def clean_answer_token(token: str) -> str:
    """Spec §3.9. Strips URLs; cuts page-number + next-question bleed.
    Guards keep ``Chapter 5 Summary.``, ``Apollo 11 Mission
    Control``, ``The 3 musketeers?`` whole. A token that is ONLY a
    page indicator (``- 2 of 62``, ``Page 11``) is footer debris,
    never an answer — but a bare number alone (``42``) CAN be a legit
    answer and is kept."""
    text = token.strip()
    text = re.sub(r"https?://\S+|www\.\S+", "", text).strip()
    if re.match(r"^-?\s*\d+\s+of\s+\d+$", text, re.IGNORECASE):
        return ""
    if PAGE_FOOTER_RE.match(text):
        return ""
    # (a) ``.<space><1-3 digits><space>`` when the remainder contains ``?``.
    match = re.search(r"\.\s+\d{1,3}\s+(?=\S)", text)
    if match and "?" in text[match.end() :]:
        text = text[: match.start()].strip()
    # (b) first bare number when the remainder starts with ANOTHER
    # bare number and contains ``?`` (question-word guard keeps
    # ``Henry 8`` whole).
    match = re.match(r"^(\d+)\s+(\d+)\s+(.*)$", text)
    if match and "?" in match.group(3):
        remainder = match.group(3)
        if not any(remainder.lower().startswith(prefix) for prefix in QUESTION_WORD_PREFIXES):
            text = match.group(1)
    # (c) bare number + question-stem remainder >= 15 chars when it
    # starts with a question word, or >= 25 chars when it starts with
    # a capital (noun-start stem).
    match = re.match(r"^\d+\s+(.*)$", text)
    if match and "?" in match.group(1):
        remainder = match.group(1)
        starts_qword = any(
            remainder.lower().startswith(prefix) for prefix in QUESTION_WORD_PREFIXES
        )
        if (starts_qword and len(remainder) >= 15) or (
            remainder[:1].isupper() and len(remainder) >= 25
        ):
            text = text[: match.start(1)].strip()
    return text
