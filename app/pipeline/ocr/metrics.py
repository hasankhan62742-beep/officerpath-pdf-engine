# OfficerPath AI — PDF Engine (Phase 1, M3)
# Benchmark metrics: CER / WER / reading-order scores (prompt §20).
#
# Definitions (standard, stated so the benchmark report is checkable):
# - CER = Levenshtein distance (characters) / len(reference chars).
#   WER = Levenshtein distance (words, whitespace-split) /
#   len(reference words). Both are computed on the comparison form
#   (see normalize.py: NFC, unified digits, collapsed whitespace) so
#   engines are not penalised for digit encoding or line breaks.
# - An empty reference with a non-empty hypothesis scores 1.0
#   (everything is an insertion); both empty scores 0.0.
# - Reading order: `pairwise_order_score` aligns the hypothesis line
#   sequence to the reference with difflib, then counts how many
#   reference adjacent pairs keep their relative order in the
#   hypothesis. 1.0 = perfect order. `column_order_accuracy` is the
#   two-column special case: the fraction of reference left-column
#   lines that appear before every reference right-column line.
# - All functions are pure and deterministic; the benchmark script
#   calls them, tests pin them on hand-computed examples.

from __future__ import annotations

import difflib

from app.pipeline.ocr.normalize import normalize_for_comparison


def _levenshtein(a: list[str], b: list[str]) -> int:
    """Edit distance between two token lists, O(min(m, n)) space."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, token_a in enumerate(a, start=1):
        current = [i]
        for j, token_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (token_a != token_b),
                )
            )
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate on the comparison form."""
    ref = normalize_for_comparison(reference)
    hyp = normalize_for_comparison(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(list(ref), list(hyp)) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate on the comparison form."""
    ref = normalize_for_comparison(reference).split()
    hyp = normalize_for_comparison(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def pairwise_order_score(reference_lines: list[str], hypothesis_lines: list[str]) -> float:
    """Fraction of reference adjacent line pairs whose relative order
    survives in the hypothesis. Lines are matched on the comparison
    form; unmatched lines are ignored (they are CER/WER's job, not
    ordering's). Returns 1.0 when fewer than two reference lines can
    be matched (nothing to order)."""
    ref = [normalize_for_comparison(line) for line in reference_lines]
    hyp = [normalize_for_comparison(line) for line in hypothesis_lines]
    hyp_index: dict[str, int] = {}
    for i, line in enumerate(hyp):
        hyp_index.setdefault(line, i)
    positions = [hyp_index[line] for line in ref if line and line in hyp_index]
    if len(positions) < 2:
        return 1.0
    concordant = sum(1 for a, b in zip(positions, positions[1:], strict=False) if a < b)
    return concordant / (len(positions) - 1)


def column_order_accuracy(
    left_lines: list[str], right_lines: list[str], hypothesis_lines: list[str]
) -> float:
    """Two-column check: of the reference left-column lines that were
    recognised at all, what fraction appear before EVERY recognised
    right-column line in the hypothesis? 1.0 = columns never
    interleaved. Returns 1.0 when either side has no recognised line
    (nothing to interleave)."""
    hyp = [normalize_for_comparison(line) for line in hypothesis_lines]
    hyp_index: dict[str, int] = {}
    for i, line in enumerate(hyp):
        hyp_index.setdefault(line, i)
    left_pos = [
        hyp_index[normalize_for_comparison(line)]
        for line in left_lines
        if normalize_for_comparison(line) in hyp_index
    ]
    right_pos = [
        hyp_index[normalize_for_comparison(line)]
        for line in right_lines
        if normalize_for_comparison(line) in hyp_index
    ]
    if not left_pos or not right_pos:
        return 1.0
    last_right = min(right_pos)
    correct = sum(1 for pos in left_pos if pos < last_right)
    return correct / len(left_pos)


def sequence_alignment(
    reference_lines: list[str], hypothesis_lines: list[str]
) -> list[tuple[str, str, str]]:
    """Line-level alignment for the benchmark report: returns
    (status, reference_line, hypothesis_line) triples where status is
    'match' | 'substitute' | 'missing' | 'extra'. Built on
    difflib.SequenceMatcher over comparison-form lines; the ORIGINAL
    lines are returned so the report shows real text."""
    ref_norm = [normalize_for_comparison(line) for line in reference_lines]
    hyp_norm = [normalize_for_comparison(line) for line in hypothesis_lines]
    matcher = difflib.SequenceMatcher(a=ref_norm, b=hyp_norm, autojunk=False)
    rows: list[tuple[str, str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append(("match", reference_lines[i1 + k], hypothesis_lines[j1 + k]))
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                ref_line = reference_lines[i1 + k] if i1 + k < i2 else ""
                hyp_line = hypothesis_lines[j1 + k] if j1 + k < j2 else ""
                rows.append(("substitute", ref_line, hyp_line))
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append(("missing", reference_lines[k], ""))
        else:  # insert
            for k in range(j1, j2):
                rows.append(("extra", "", hypothesis_lines[k]))
    return rows
