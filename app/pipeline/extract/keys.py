# OfficerPath AI — PDF Engine (Phase 1, M4)
# Answer keys and the paper-identity gate — port of the Dart parser
# rules, spec §5-§6.4-6.10.
#
# Sources: answer_key.dart:380-1077, 1115-1498, paper_identity.dart:54-387.

from __future__ import annotations

import re

from app.pipeline.extract.markers import clean_answer_token
from app.pipeline.extract.numbers import (
    OCR_NUMBER_TOKEN,
    decode_ocr_number,
    normalize_urdu_digits,
)

#: Spec §5.2: paper-heading shape. The WHOLE line must be (just) the
#: heading, so ``Part 1: Introduction`` is not one.
PAPER_HEADING_RE = re.compile(
    r"^(?:model\s+)?(paper|test|set|part|section)\s*"
    r"(?:no\.?|number|#)?\s*([0-9]+|[A-Z])\s*[:\-–—]?\s*$",
    re.IGNORECASE,
)
#: Spec §5.2: a paper reference anywhere in a line.
PAPER_REF_RE = re.compile(
    r"\b(?:model\s+)?(paper|test|set|part|section)\s*"
    r"(?:no\.?|number|#)?\s*([0-9]+|[A-Z])\b",
    re.IGNORECASE,
)
#: Spec §5.1: month headings (abbreviations normalised to full names).
_MONTHS = {
    "jan": "January",
    "january": "January",
    "feb": "February",
    "february": "February",
    "mar": "March",
    "march": "March",
    "apr": "April",
    "april": "April",
    "may": "May",
    "jun": "June",
    "june": "June",
    "jul": "July",
    "july": "July",
    "aug": "August",
    "august": "August",
    "sep": "September",
    "sept": "September",
    "september": "September",
    "oct": "October",
    "october": "October",
    "nov": "November",
    "november": "November",
    "dec": "December",
    "december": "December",
}
MONTH_HEADING_RE = re.compile(
    r"^(" + "|".join(sorted(_MONTHS)) + r")\.?\s+(\d{4})\s*$", re.IGNORECASE
)
#: Spec §5.1: chapter headings — whole line only.
CHAPTER_HEADING_RE = re.compile(r"^chapter\s+\d+\s*$", re.IGNORECASE)

#: Spec §6.4: key-section heading words (after stripping paper
#: refs/parens). The plural is REQUIRED in the bare ``Answers`` /
#: ``Correct Answers`` alternatives — singular ``Answer:`` would open
#: a spurious section at every answered question.
KEY_CORE_RE = re.compile(
    r"^(answer\s*keys?|answers?|answer\s*sheet|correct\s*answers?"
    r"|keys?)\s*[:\-–—]?\s*$",
    re.IGNORECASE,
)
#: Spec §6.8: unknown key tokens — the question is EXCLUDED, never guessed.
UNKNOWN_KEY_TOKEN_RE = re.compile(r"^(?:\?+|unknown)$", re.IGNORECASE)

#: Spec §6.6: key-entry start. Separator also accepts a comma (OCR
#: reads the entry period as a comma: ``13, (B) ...``); the lookahead
#: blocks thousands separators (``138,000``) and decimals (``43.75%``).
KEY_ENTRY_START_RE = re.compile(
    r"(?:^|\s)(?:Q\s*)?(" + OCR_NUMBER_TOKEN + r")\s*[\.\)\:\-,]"
    r"(?=\s|[A-Ea-e]\b|\(|$)"
)
#: Spec §6.6: bare-Q normalisation — ``Q1 C`` rewritten to ``Q1: C``.
_BARE_Q_ENTRY_RE = re.compile(r"\bQ\s*(" + OCR_NUMBER_TOKEN + r")\s+([A-Ea-e])(?![A-Za-z0-9])")
#: Spec §12.5: ``Q1 Correct ...`` / ``FAQ1 C`` guard — the letter
#: must not be followed by a letter/digit and the ``Q`` must not be
#: part of a longer word.
_BARE_Q_GUARD_RE = re.compile(r"(?<![A-Za-z])Q\s*(\d+)\s+([A-Ea-e])(?![A-Za-z0-9])")


def normalise_bare_q_entries(text: str) -> str:
    """Spec §6.6/§12.5: rewrite ``Q1 C`` to ``Q1: C`` (with the
    word-boundary guards so ``FAQ1 C`` is untouched)."""
    return _BARE_Q_ENTRY_RE.sub(lambda m: f"Q{m.group(1)}: {m.group(2)}", text)


def normalise_paper_title(title: str) -> str:
    """Spec §5.6: lowercase, collapsed whitespace, leading qualifier
    (``model|mock|sample|past``) removed, trailing punctuation
    removed. ``Model Paper 66`` and ``PAPER 66`` normalise to the
    same string; ``Model Paper 66`` and ``Model Paper 67`` do not."""
    text = re.sub(r"\s+", " ", title.strip().lower())
    text = re.sub(r"^(model|mock|sample|past)\s+", "", text)
    return text.rstrip(".,:;!?-–— ").strip()


def is_answer_key_heading(line: str) -> bool:
    """Spec §6.4/§12.6. The trailing-paren strip never strips a bare
    answer token (``(B)``, ``1-4``, ``A-E``); otherwise ``Answer:
    (B)`` would open a key section and swallow the following
    questions. ``(Answer Key)`` and ``Answer Key (January 2026)``
    are heading forms."""
    text = line.strip()
    # A bare answer token in parens is never a subhead.
    if re.search(r"\(\s*[A-Ea-e]\s*\)\s*$", text):
        return False
    if re.search(r"\(\s*[A-Ea-e]\s*-\s*[A-Ea-e]\s*\)\s*$", text):
        return False
    whole = re.match(r"^\(\s*(.+?)\s*\)$", text)
    if whole:
        # The whole heading is parenthesised: "(Answer Key)".
        text = whole.group(1)
    else:
        # Strip a trailing "(Month Year)" subhead, e.g. "Answer Key
        # (January 2026)", or a trailing "(answer|key|answers)".
        text = re.sub(r"\s*\([A-Za-z]+\s+\d{4}\)\s*$", "", text)
        text = re.sub(r"\s*\((answer|key|answers)\)\s*$", "", text, flags=re.IGNORECASE)
    return bool(KEY_CORE_RE.match(text))


def key_heading_remainder(line: str) -> tuple[str, str | None]:
    """Spec §6.5. A line whose START is a key heading but which
    carries more text (``ANSWER KEY: 1. (B) Broke out``) opens the
    section and feeds the remainder back as its first content line.
    The remainder must itself look like key content (a key-entry
    start, or a short title-cased subhead 3-45 chars, no trailing
    sentence punctuation)."""
    text = line.strip()
    match = re.match(
        r"^(answer\s*keys?|answers?|answer\s*sheet|correct\s*answers?"
        r"|keys?)\s*[:\-–—]\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text, None
    remainder = match.group(2).strip()
    # Spec §12.6: a bare answer token is never a subhead — and neither
    # is an answer value starting with an option-letter marker
    # ("Correct Answer: B) Asif Ali Zardari" is an answer LINE, §6.2,
    # not a key heading with a remainder).
    if re.match(r"^\(?\s*[A-Ea-e]\s*[\)\.\:\-]", remainder):
        return text, None
    if KEY_ENTRY_START_RE.search(normalize_urdu_digits(remainder)):
        return match.group(1), remainder
    if (
        3 <= len(remainder) <= 45
        and not remainder.endswith((".", "?", "!", ":"))
        and re.search(r"[A-Z]", remainder)
        and not re.match(r"^\(\s*[A-Ea-e]\s*\)", remainder)
    ):
        return match.group(1), remainder
    return text, None


def is_unknown_key_token(token: str) -> bool:
    """Spec §6.8: ``?``, ``??``, or ``unknown`` (case-insensitive)."""
    return bool(UNKNOWN_KEY_TOKEN_RE.match(token.strip()))


def is_key_only_line(line: str) -> bool:
    """Spec §6.10. A whole line of nothing but key entries
    (``1. D 58. B 73. A 88. B``, ``57. A``, separator-less rows of
    >= 3 contiguous pairs). Every number token must decode; a bare
    letter (``B. C``) is a list marker, never a key entry."""
    text = normalize_urdu_digits(line.strip())
    if not text:
        return False
    # Separator form: all tokens are "number sep letter/text".
    tokens = text.split()
    if len(tokens) >= 2 and all(
        re.match(r"^\d+[\.\)\:\-,]$", tok) or re.match(r"^[A-Ea-e]$", tok) for tok in tokens
    ):
        return True
    # Single entry "57. A" — the WHOLE line must be just the number
    # and the letter (spec §6.10: "a whole line of nothing but key
    # entries"). A question stem such as "14. A Character That ..."
    # is NOT a key line: the value after the letter must be empty.
    if re.match(
        r"^(?:Q\s*)?" + OCR_NUMBER_TOKEN + r"\s*[\.\)\:\-,]\s*[A-Ea-e]\b",
        text,
    ):
        return bool(
            re.match(
                r"^(?:Q\s*)?" + OCR_NUMBER_TOKEN + r"\s*[\.\)\:\-,]\s*"
                r"\(?[A-Ea-e]\)?\s*$",
                text,
            )
        )
    # Separator-less rows of >= 3 contiguous "number letter" pairs.
    pairs = re.findall(r"\b(\d+)\s+([A-Ea-e])\b", text)
    return len(pairs) >= 3 and bool(re.fullmatch(r"(?:\d+\s+[A-Ea-e]\s*){3,}", text))


def parse_key_entries(text: str) -> dict[int, str]:
    """Spec §6.6. Treat a key section as ONE token stream (compact
    runs ``1.C 2.A 3.B ...`` and multi-column layouts both work —
    lookup by number, never by position). First entry wins when a
    number repeats. Separator-less rows (``1 B``, ``1(B)``) count
    only as a second pass and only when the blob holds >= 3 of them,
    and never inside a separator entry's value span."""
    blob = normalise_bare_q_entries(normalize_urdu_digits(text))
    entries: dict[int, str] = {}
    spans: list[tuple[int, int]] = []
    for match in KEY_ENTRY_START_RE.finditer(blob):
        number = decode_ocr_number(match.group(1))
        if number is None:
            continue
        value_start = match.end()
        # Value runs until the next entry start (or end of blob).
        next_match = KEY_ENTRY_START_RE.search(blob, value_start)
        value_end = next_match.start() if next_match else len(blob)
        value = blob[value_start:value_end].strip(" \t\r\n,;")
        value = value.strip()
        if number not in entries:
            entries[number] = value
        spans.append((match.start(), value_end))
    # Second pass: separator-less rows, only when >= 3 of them, and
    # never inside a separator entry's value span.
    # NOTE: the letter must be followed by a lookahead, not a
    # consuming "\s*" — a trailing "\s*" eats the space between
    # pairs, so "1 B 2 C 3 D" would only match 1 and 3.
    sep_less = list(re.finditer(r"(?:^|\s)(\d+)\s*\(?\s*([A-Ea-e])(?=\s|\)|$)", blob))
    outside = [m for m in sep_less if not any(start <= m.start() < end for start, end in spans)]
    if len(outside) >= 3:
        for match in outside:
            number = int(match.group(1))
            if number not in entries:
                entries[number] = match.group(2)
    return entries


def resolve_answer_token(token: str, options: list[str]) -> int | None:
    """Spec §6.7, tried IN ORDER (the order is load-bearing — e.g.
    bare-number-before-text means ``3`` resolves as an index, not as
    option text ``3``):
    (1) ``Option X``; (2) paren letter ``(C) 80``; (3) ``B) text`` /
    ``2. Paris`` — letter/number first, text as fallback; (4) bare
    number 1..len(options) -> index-1; (5) single letter A..(A+len);
    (6) exact case-insensitive text match; (7) bare misread letter
    ``8``/``0`` -> B/D (only AFTER the text match, so a real numeric
    option value ``8`` still wins). Returns None when nothing
    matches."""
    raw = clean_answer_token(token)
    if not raw:
        return None
    text = raw.strip()
    # (1) "Option X"
    match = re.match(r"^option\s+([A-Ea-e1-580])\b", text, re.IGNORECASE)
    if match:
        return _letter_or_number_to_index(match.group(1), options)
    # (2) paren letter "(C) 80" / "(C)80" — letter wins; trailing
    # value is a cross-check (handled by the caller, §6.14).
    match = re.match(r"^\(\s*([A-Ea-e])\s*\)", text)
    if match:
        index = _letter_to_index(match.group(1), options)
        if index is not None:
            return index
    # (3) "B) Asif Ali Zardari" / "2. Paris" — letter/number first.
    match = re.match(r"^\(?([A-Ea-e])\s*[\)\.\:\-]\s*(.+)$", text)
    if match:
        index = _letter_to_index(match.group(1), options)
        if index is not None:
            return index
        # Text as fallback.
        fallback = _text_to_index(match.group(2), options)
        if fallback is not None:
            return fallback
    match = re.match(r"^(\d+)\s*[\)\.\:\-]\s*(.+)$", text)
    if match:
        number = int(match.group(1))
        if 1 <= number <= len(options):
            return number - 1
        fallback = _text_to_index(match.group(2), options)
        if fallback is not None:
            return fallback
    # (4) bare number 1..len(options) -> index-1.
    if re.fullmatch(r"\d+", text):
        number = int(text)
        if 1 <= number <= len(options):
            return number - 1
    # (5) single letter A..(A+len).
    if re.fullmatch(r"[A-Ea-e]", text):
        return _letter_to_index(text, options)
    # (6) exact case-insensitive text match against the options.
    matched = _text_to_index(text, options)
    if matched is not None:
        return matched
    # (7) bare misread letter 8/0 -> B/D.
    if text == "8":
        return _letter_to_index("B", options)
    if text == "0":
        return _letter_to_index("D", options)
    return None


def _letter_to_index(letter: str, options: list[str]) -> int | None:
    index = ord(letter.upper()) - ord("A")
    return index if 0 <= index < len(options) else None


def _letter_or_number_to_index(token: str, options: list[str]) -> int | None:
    if token.isdigit():
        number = int(token)
        if 1 <= number <= len(options):
            return number - 1
        return None
    if token in ("8", "0"):
        return _letter_to_index("B" if token == "8" else "D", options)
    return _letter_to_index(token, options)


def _text_to_index(text: str, options: list[str]) -> int | None:
    lowered = text.strip().lower()
    for i, option in enumerate(options):
        if option.strip().lower() == lowered:
            return i
    return None


# --- paper identity (spec §5.5-5.8) -----------------------------------

#: KeyMatchConfidence ladder (spec §13.4).
KEY_CONFIDENCES = (
    "verified",
    "highConfidence",
    "needsReview",
    "unverified",
    "mismatch",
)


def decide_key_match(
    key_identity: dict,
    question_identity: dict,
    *,
    key_is_bare: bool,
    single_paper_in_document: bool,
    exclusive_coverage: bool,
    position_evidence: bool,
) -> dict:
    """Spec §5.5 (``decideKeyMatch``, paper_identity.dart:190).
    Level 1 — different ``sourceDocumentId`` -> MISMATCH. Level 2 —
    paper number present on both and different -> MISMATCH. Level 3
    — title present on both and different after normalisation ->
    MISMATCH. Level 4 — year/exam present on both and different ->
    MISMATCH; agreement is corroboration, never identity. VERIFIED =
    number + title agree, OR number agrees with a second
    corroborating field (year/exam). HIGH CONFIDENCE = an identifier
    agrees + position + coverage, OR a bare key + position + coverage
    + (single paper in document OR exclusive coverage). NEEDS REVIEW
    = bare key in a multi-paper document with non-exclusive coverage,
    or an identifier agrees but position/coverage evidence is
    missing. UNVERIFIED = no identity and no evidence. Coverage alone
    is NEVER sufficient for VERIFIED; numbers alone are never
    sufficient. Only VERIFIED auto-assigns silently; HIGH CONFIDENCE
    is applied but flagged; NEEDS REVIEW / UNVERIFIED / MISMATCH are
    never applied."""
    evidence: list[str] = []
    key_doc = key_identity.get("source_document_id")
    q_doc = question_identity.get("source_document_id")
    if key_doc and q_doc and key_doc != q_doc:
        return _decision("mismatch", "different source document", evidence)
    key_num = key_identity.get("paper_number")
    q_num = question_identity.get("paper_number")
    if key_num is not None and q_num is not None and str(key_num) != str(q_num):
        return _decision("mismatch", "different paper number", evidence)
    key_title = key_identity.get("paper_title")
    q_title = question_identity.get("paper_title")
    if key_title and q_title:
        if normalise_paper_title(key_title) != normalise_paper_title(q_title):
            return _decision("mismatch", "different paper title", evidence)
        evidence.append("title agrees")
    key_year = key_identity.get("year")
    q_year = question_identity.get("year")
    if key_year is not None and q_year is not None and key_year != q_year:
        return _decision("mismatch", "different year", evidence)
    key_exam = key_identity.get("exam")
    q_exam = question_identity.get("exam")
    if key_exam and q_exam and key_exam.lower() != q_exam.lower():
        return _decision("mismatch", "different exam", evidence)
    number_agrees = key_num is not None and q_num is not None and str(key_num) == str(q_num)
    title_agrees = bool(evidence)
    second_field = (key_year is not None and key_year == q_year) or (
        key_exam and q_exam and key_exam.lower() == q_exam.lower()
    )
    if number_agrees and (title_agrees or second_field):
        evidence.append("paper number agrees")
        return _decision("verified", "paper number + title/year/exam agree", evidence)
    if (number_agrees or title_agrees or second_field) and position_evidence and exclusive_coverage:
        return _decision(
            "highConfidence",
            "identifier agrees + position + coverage",
            evidence,
        )
    if (
        key_is_bare
        and position_evidence
        and exclusive_coverage
        and (single_paper_in_document or exclusive_coverage)
    ):
        return _decision(
            "highConfidence",
            "bare key + position + coverage"
            + (" + single paper in document" if single_paper_in_document else ""),
            evidence,
        )
    if key_is_bare and not single_paper_in_document and not exclusive_coverage:
        return _decision(
            "needsReview",
            "bare key in a multi-paper document with non-exclusive coverage",
            evidence,
        )
    if number_agrees or title_agrees or second_field:
        return _decision(
            "needsReview",
            "an identifier agrees but position/coverage evidence is missing",
            evidence,
        )
    return _decision("unverified", "no identity and no evidence", evidence)


def _decision(confidence: str, reason: str, evidence: list[str]) -> dict:
    return {
        "confidence": confidence,
        "reason": reason,
        "evidence": list(evidence),
        "may_auto_assign": confidence == "verified",
    }


def orphan_adoption_eligible(
    *,
    explicit_key_count: int,
    key_paper_has_questions: bool,
    all_questions_in_one_default_segment: bool,
    question_numbers_unique: bool,
    overlap_fraction: float,
) -> bool:
    """Spec §5.8. An explicit key whose named paper has NO questions
    is adopted for the document's single unlabelled paper ONLY when
    provably safe: exactly ONE explicit key exists; the key's named
    paper has no question lines; every question line is in ONE
    segment, the default paper; question numbers are unique; >= 80%
    of the key's entry numbers appear among the questions."""
    return (
        explicit_key_count == 1
        and not key_paper_has_questions
        and all_questions_in_one_default_segment
        and question_numbers_unique
        and overlap_fraction >= 0.80
    )
