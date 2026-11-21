# OfficerPath AI — PDF Engine (Phase 1, M3)
# Text normalisation for OCR output (prompt §8).
#
# Rules, stated plainly because getting them wrong silently corrupts
# Urdu text:
# - The ORIGINAL engine text is NEVER modified in storage. These
#   helpers exist only for COMPARISON (CER/WER, agreement, dedup) and
#   for the normalised_text column M4 writes. Nothing here rewrites
#   what an engine produced.
# - Unicode: NFC (canonical composition). NFKC is NOT used: it would
#   fold Arabic presentation forms and compatibility characters that
#   are legitimate Urdu text.
# - Digits: Urdu/Arabic-Indic digits (۰-۹ / ٠-٩) map to ASCII digits
#   ONLY in the comparison form — the OCR engines themselves disagree
#   on digits (Tesseract emits ۰-۹, PaddleOCR emits ٠-٩ or 0-9), and a
#   benchmark that counts "۵" vs "5" as an error measures digit
#   encoding, not reading. The original keeps whatever the engine
#   emitted; the comparison form unifies them.
# - Whitespace: runs collapse to one space, ends stripped — engines
#   disagree on line breaks and spacing, and CER/WER must measure
#   content, not layout whitespace.
# - The category-separation rule from the Flutter parser (digits only
#   in number slots, letters only in option markers, Urdu preserved
#   exactly) lives in M4, not here: normalisation must never "fix" a
#   digit into a letter or vice versa.

from __future__ import annotations

import re
import unicodedata

# Arabic-Indic digits ٠-٩ (U+0660..U+0669) and Extended Arabic-Indic
# (Urdu) digits ۰-۹ (U+06F0..U+06F9) -> ASCII 0-9.
_DIGIT_MAP = str.maketrans(
    "".join(chr(c) for c in range(0x0660, 0x066A)) + "".join(chr(c) for c in range(0x06F0, 0x06FA)),
    "0123456789" * 2,
)

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_for_comparison(text: str) -> str:
    """Comparison form: NFC + unified digits + collapsed whitespace.

    Used by CER/WER, agreement scores and dedup. Never applied to
    stored original text.
    """
    normalized = unicodedata.normalize("NFC", text).translate(_DIGIT_MAP)
    return _WHITESPACE_RUN.sub(" ", normalized).strip()


def normalize_digits_only(text: str) -> str:
    """Map Urdu/Arabic-Indic digits to ASCII, NFC, nothing else."""
    return unicodedata.normalize("NFC", text).translate(_DIGIT_MAP)


def detect_script(text: str) -> str:
    """Coarse script label for one string: 'urdu' if it contains any
    Arabic-script letter, 'latin' if it contains Latin letters and no
    Arabic script, 'digits' if only digits/punctuation, else 'mixed'
    or 'empty'. Used for language labelling, never for correction."""
    if not text.strip():
        return "empty"
    has_arabic = any(0x0600 <= ord(ch) <= 0x06FF or 0x0750 <= ord(ch) <= 0x077F for ch in text)
    has_latin = any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in text)
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "urdu"
    if has_latin:
        return "latin"
    return "digits"
