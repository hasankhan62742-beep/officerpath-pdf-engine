# OfficerPath AI — PDF Engine (Phase 1, M4)
# Question-number detection — port of the Dart parser rules, spec §1.
#
# Sources: mcq_parser.dart:384-495, answer_key.dart:74-183.
# D1: Urdu/Arabic-Indic digits are normalised to ASCII for MATCHING
# numbers/markers only; stored text keeps the original digits.

from __future__ import annotations

import re

# D1: Eastern Arabic numerals (U+0660-0669) and Extended Arabic-Indic
# digits (U+06F0-06F9) -> ASCII. Used for matching only.
URDU_DIGIT_MAP: dict[str, str] = {
    **{chr(0x0660 + i): str(i) for i in range(10)},
    **{chr(0x06F0 + i): str(i) for i in range(10)},
}
_URDU_DIGIT_RE = re.compile("[" + "".join(URDU_DIGIT_MAP) + "]")


def normalize_urdu_digits(text: str) -> str:
    """Map Urdu/Arabic-Indic digits to ASCII (D1, matching only)."""
    return _URDU_DIGIT_RE.sub(lambda m: URDU_DIGIT_MAP[m.group(0)], text)


# Spec §1.3: OCR digit-confusion map. Only letters map to digits,
# never digit -> digit.
OCR_DIGIT_MAP: dict[str, str] = {
    **{c: "1" for c in "IiLl"},
    **{c: "0" for c in "Oo"},
    **{c: "5" for c in "Ss$§"},
    **{c: "8" for c in "Bb"},
    **{c: "2" for c in "Zz"},
}
_CONFUSABLE = frozenset(OCR_DIGIT_MAP)

# Spec §1.4: OCR number-token pattern. Pure digits any length, else
# 1-3 chars with at least one real digit (alternation, because a regex
# cannot express "at least one digit" inside a character class).
OCR_NUMBER_TOKEN = (
    r"(?:\d+|\d[0-9IiLlOoSsBbZz$§]{0,2}"
    r"|[IiLlOoSsBbZz$§]\d[0-9IiLlOoSsBbZz$§]?"
    r"|[IiLlOoSsBbZz$§]{2}\d)"
)
OCR_NUMBER_TOKEN_RE = re.compile(OCR_NUMBER_TOKEN)


def decode_ocr_number(token: str) -> int | None:
    """Spec §1.3. Pure-digit tokens: any length, result must be >= 1.
    Letter-bearing tokens: max 3 chars, every char a digit or a
    confusable letter, must contain >= 1 real digit. A bare letter
    (``B.``, ``S.``) -> None."""
    if not token:
        return None
    if token.isdigit():
        value = int(token)
        return value if value >= 1 else None
    if len(token) > 3:
        return None
    if not all(c.isdigit() or c in _CONFUSABLE for c in token):
        return None
    if not any(c.isdigit() for c in token):
        return None
    decoded = "".join(OCR_DIGIT_MAP.get(c, c) for c in token)
    value = int(decoded)
    return value if value >= 1 else None


# Spec §1.1: clean number regex, with the (?!\d) guard so a decimal
# (``92.97 m ...``) is never a question number.
QUESTION_NUMBER_RE = re.compile(r"^(?:Q\s*\.?\s*)?(\d+)\s*[.\)\:](?!\d)", re.IGNORECASE)
# Spec §1.2: OCR-misread fallback — separator ``.`` or ``)`` ONLY,
# never ``:`` (``S1:``/``S6:`` are source-bank sequence labels, and ``S1``
# decodes to 51).
OCR_NUMBER_RE = re.compile(
    r"^(?:Q\s*\.?\s*)?(" + OCR_NUMBER_TOKEN + r")\s*[.\)](?!\d)",
    re.IGNORECASE,
)
# Spec §1.5: misread-number start test. Separator ``.``/``)`` only.
MISREAD_NUMBER_START_RE = re.compile(
    r"^(?:Q\s*\.?\s*)?([0-9IiLlOoSsBbZz$§]{1,3})\s*[.\)](?!\d)\s*\S",
    re.IGNORECASE,
)
# Spec §1.8: shared prefix regex. The bare-``Q`` alternative requires
# a separator, so ``Quality ...`` is never stripped.
QUESTION_PREFIX_RE = re.compile(
    r"^(?:Q\s*\.?\s*" + OCR_NUMBER_TOKEN + r"\s*[.\)\:]?"
    r"|Q\s*[.\)\:]|" + OCR_NUMBER_TOKEN + r"\s*[.\)\:])\s*",
    re.IGNORECASE,
)
# Spec §1.9: block-split question start.
BLOCK_SPLIT_START_RE = re.compile(r"^(Q\s*\d*[.\)\:]|\d+[.\)](?!\d))\s*\S", re.IGNORECASE)
# Spec §1.6: bare number — pure digits, any length (a year like 1947
# is a bare number too). Case-sensitive on purpose (see §1.7).
BARE_NUMBER_RE = re.compile(r"^(\d+)\s+(?![a-z0-9])")


# Spec §1.1a (A1): "Question#N" marker — the NOA Maths scan numbers
# its questions "Question#1" ... on their own line, with no
# separator after the number. Only the #-form is recognised:
# "Question 12" in prose is never a marker, and the #-form never
# appears in any other fixture's text layer (checked A1).
QUESTION_HASH_RE = re.compile(r"^question\s*#\s*(\d+|[0-9IiLlOoSsBbZz$§]{1,3})\b", re.IGNORECASE)
# Spec §1.8a (A1): the same #-form, for prefix stripping.
QUESTION_HASH_PREFIX_RE = re.compile(
    r"^question\s*#\s*(?:\d+|[0-9IiLlOoSsBbZz$§]{1,3})\s*[.\)\:]?\s*",
    re.IGNORECASE,
)


def question_number_detailed(line: str) -> tuple[int, bool] | None:
    """Spec §1.1-1.2. Returns (number, decoded) or None. ``decoded``
    is True only when the number came from a misread token."""
    text = normalize_urdu_digits(line.strip())
    match = QUESTION_NUMBER_RE.match(text)
    if match:
        return int(match.group(1)), False
    match = OCR_NUMBER_RE.match(text)
    if match:
        value = decode_ocr_number(match.group(1))
        if value is not None:
            return value, True
    match = QUESTION_HASH_RE.match(text)
    if match:
        token = match.group(1)
        value = int(token) if token.isdigit() else decode_ocr_number(token)
        if value is not None:
            return value, not token.isdigit()
    return None


def is_misread_number_start(line: str) -> bool:
    """Spec §1.5. Guards ``6.2x20 = 124.`` (decimal/equation, not Q6)."""
    text = normalize_urdu_digits(line.strip())
    match = MISREAD_NUMBER_START_RE.match(text)
    if not match:
        return False
    return decode_ocr_number(match.group(1)) is not None


def bare_number_at_start(line: str) -> int | None:
    """Spec §1.6. Pure digits, else a misread token decoded via
    decode_ocr_number."""
    text = normalize_urdu_digits(line.strip())
    match = BARE_NUMBER_RE.match(text)
    if match:
        return int(match.group(1))
    # Else a misread token decoded via decode_ocr_number — but only
    # when the token actually contains a confusable letter. A pure
    # digit that failed the lookahead above ("3 apples are red.")
    # is a list item / year, never a bare number.
    token_match = re.match(r"^([0-9IiLlOoSsBbZz$§]{1,3})\s", text)
    if token_match and any(c.isalpha() for c in token_match.group(1)):
        return decode_ocr_number(token_match.group(1))
    return None


def strip_question_number_prefix(text: str) -> str:
    """Spec §1.7. Strips dotted/``Q`` forms via questionPrefixRe, plus
    a BARE number only when the text ends with ``?``/``؟`` (a complete
    question stem). Known ambiguity (ported, not fixed): a question
    OPENING with a year (``1947 Was a leap year?``) loses the year.
    A1: the ``Question#N`` form is stripped the same way."""
    stripped = QUESTION_HASH_PREFIX_RE.sub("", text, count=1)
    if stripped != text:
        return stripped
    stripped = QUESTION_PREFIX_RE.sub("", text, count=1)
    if stripped != text:
        return stripped
    if text.rstrip().endswith(("?", "؟")):
        match = BARE_NUMBER_RE.match(normalize_urdu_digits(text))
        if match:
            # Strip the same span from the ORIGINAL text.
            return text[match.end() :].lstrip()
    return text
