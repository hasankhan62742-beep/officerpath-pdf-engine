# OfficerPath AI — PDF Engine (Phase 1, M4)
# Q&A without options + flashcards — port of the Dart parser rules,
# spec §10.1-10.2.
#
# Output type is ``qa_pair``: question + answer, NO options. The
# extractor NEVER fabricates 4 options for these (task decision).
# The pool-built q-only options of Dart §10.1 are implemented as
# :func:`build_q_only_options` (seeded, D10) and unit-tested, but the
# M4 service emits ``qa_pair`` records without options.

from __future__ import annotations

import random
import re

from app.pipeline.extract.markers import (
    clean_stored,
    is_noise_line,
    strip_answer_tail,
)
from app.pipeline.extract.numbers import (
    question_number_detailed,
    strip_question_number_prefix,
)
from app.pipeline.extract.signals import ANSWER_LINE_RE

#: D10: SEEDED deterministic distractor shuffle — a deliberate change
#: from Dart's unseeded ``Random()`` (spec §14.9). Identical input
#: produces identical option orders across runs.
QA_POOL_SEED = 20261121

#: Spec §10.2 caps (D9: kept as Dart defines them; the Computer Q&A
#: file's answers are short — how many exceed the caps is measured
#: in the benchmark and reported).
FLASHCARD_MAX_CHARS_PER_LINE = 100
FLASHCARD_MAX_LINES = 2
FLASHCARD_MAX_TOTAL_CHARS = 160

_DASH_SPLIT_RE = re.compile(r"\s+[—–]\s+")
_TRAILING_SPLIT_RE = re.compile(r"[?؟:]")


def is_real_q_only_stem(text: str) -> bool:
    """Spec §10.1 (``_isRealQOnlyStem``): >= 10 chars, >= 2 words, a
    word >= 3 chars — guards against OCR debris like ``Wh to e``
    becoming fake questions with pool-built options."""
    words = text.split()
    return len(text) >= 10 and len(words) >= 2 and any(len(word) >= 3 for word in words)


def build_q_only_options(correct_answer: str, answer_pool: list[str]) -> list[str] | None:
    """Spec §10.1/§8.4. 4 options built from the correct answer + 3
    distractors drawn from OTHER questions' answers in the same book
    (never the correct answer twice). The pool is keyed by normalised
    (trim + lowercase) answer text — duplicates collapse to one
    entry. If the book has fewer than 3 usable distinct distractors,
    return None — fake options are never invented. D10: the draw is
    seeded (``random.Random(20261121)``)."""
    pool: dict[str, str] = {}
    for answer in answer_pool:
        key = answer.strip().lower()
        if key and key != correct_answer.strip().lower():
            pool.setdefault(key, answer.strip())
    distinct = sorted(pool.values())
    if len(distinct) < 3:
        return None
    rng = random.Random(QA_POOL_SEED)
    distractors = rng.sample(distinct, 3)
    options = [correct_answer.strip()] + distractors
    rng.shuffle(options)
    return options


def _split_trailing_answer(line: str) -> tuple[str, str] | None:
    """Spec §10.2(c): trailing answer after the LAST ``?``/``:``/``؟``
    on the same line. A ``:`` split needs a real stem (>= 3 words /
    list entry / sentence tail) so a bare label never splits."""
    matches = list(_TRAILING_SPLIT_RE.finditer(line))
    if not matches:
        return None
    last = matches[-1]
    stem = line[: last.end()].strip()
    answer = line[last.end() :].strip()
    if not stem or not answer:
        return None
    # A ":" split needs a real stem (>= 3 words, the colon itself not
    # counted) so a bare label never splits ("Composed By:" is a
    # label, not a question).
    if line[last.start()] == ":" and len(stem.rstrip(":").split()) < 3:
        return None
    return stem, answer


def _split_dash_answer(line: str) -> tuple[str, str] | None:
    """Spec §10.2(b): dash-inline (``—``/``–``, never a plain
    hyphen)."""
    match = _DASH_SPLIT_RE.search(line)
    if not match:
        return None
    stem = line[: match.start()].strip()
    answer = line[match.end() :].strip()
    if not stem or not answer:
        return None
    return stem, answer


def scan_flashcards(
    lines: list[dict],
) -> tuple[list[dict], set[int]]:
    """Spec §10.2 (``_scanFlashcards``). Scans lines NOT consumed by
    the block/table passes for the Computer Past Papers shape (answer
    right after ``?``, no options). Each ``lines`` entry is a dict
    with ``text``, ``page`` and ``index`` (global line index).
    Guards: the block must contain NO option line; the answer must be
    on the SAME page; <= 100 chars/line, <= 2 lines, <= 160 total;
    plain lines only (not question/option/answer/explanation/header);
    stop after a line ending in ``.``; lines used by an earlier
    flashcard are never re-used.
    Returns (qa_pairs, consumed_global_indices)."""
    from app.pipeline.extract.markers import option_line_match

    pairs: list[dict] = []
    consumed: set[int] = set()
    used: set[int] = set()
    i = 0
    while i < len(lines):
        entry = lines[i]
        text = entry["text"]
        if i in used or is_noise_line(text):
            i += 1
            continue
        # An inline "Ans:" answer (spec §6.15) on the same line.
        inline = ANSWER_LINE_RE.search(text)
        split = None
        if inline:
            stem = text[: inline.start()].strip()
            answer = inline.group(1).strip()
            if stem:
                split = (stem, answer)
        if split is None:
            # A1: a bare answer line ("Correct Answer Is: 171", or
            # "_ Correct Answer Is: 1116" with OCR junk in front) is
            # not a question — it belongs to a block that failed to
            # parse, not to a flashcard. Without this guard the
            # trailing-answer split below turns it into a junk pair
            # with question "Correct Answer Is:". The match is
            # start-anchored (after junk): a stem that merely ends
            # with an answer phrase still goes to the split below.
            stripped = text.strip().lstrip("_•-–—· ")
            if ANSWER_LINE_RE.match(stripped):
                i += 1
                continue
            split = _split_trailing_answer(text) or _split_dash_answer(text)
        if split is None:
            i += 1
            continue
        stem, answer = split
        # Answer may wrap onto the next line(s) — same page, caps.
        answer_lines = [answer]
        j = i + 1
        while (
            len(answer_lines) < FLASHCARD_MAX_LINES
            and j < len(lines)
            and lines[j]["page"] == entry["page"]
            and j not in used
            and not option_line_match(lines[j]["text"])
            and question_number_detailed(lines[j]["text"].strip()) is None
            and "?" not in lines[j]["text"]
            and "؟" not in lines[j]["text"]
            and not ANSWER_LINE_RE.match(lines[j]["text"].strip())
            and len(lines[j]["text"].strip()) <= FLASHCARD_MAX_CHARS_PER_LINE
            and lines[j]["text"].strip()
        ):
            # Only join a continuation when the answer so far does
            # not already end a sentence.
            if answer_lines[-1].rstrip().endswith((".", "?", "؟")):
                break
            answer_lines.append(lines[j]["text"].strip())
            used.add(j)
            j += 1
            # Stop after a line ending in '.'.
            if answer_lines[-1].endswith("."):
                break
        full_answer = " ".join(answer_lines).strip()
        if len(full_answer) > FLASHCARD_MAX_TOTAL_CHARS:
            i += 1
            continue
        if any(len(part) > FLASHCARD_MAX_CHARS_PER_LINE for part in answer_lines):
            i += 1
            continue
        number_info = question_number_detailed(stem)
        number = number_info[0] if number_info else entry.get("qa_number")
        stem_clean = clean_stored(strip_answer_tail(strip_question_number_prefix(stem)))
        if not is_real_q_only_stem(stem_clean):
            i += 1
            continue
        # The stem must not itself contain an option line, and the
        # answer must not be a bare page indicator.
        if option_line_match(stem_clean):
            i += 1
            continue
        pairs.append(
            {
                "number": number,
                "question": stem_clean,
                "answer": clean_stored(full_answer),
                "page": entry["page"],
                "paper": entry.get("paper", "Paper 1"),
            }
        )
        used.add(i)
        consumed.add(i)
        consumed.update(used & set(range(i, j)))
        i = j if j > i else i + 1
    return pairs, consumed


def count_answers_over_flashcard_caps(pairs: list[dict]) -> int:
    """D9 measurement helper: how many Q&A answers exceed the
    flashcard caps (answer > 100 chars on a line, > 2 lines, or > 160
    total). The Computer Q&A file's answers are short — the count is
    reported in the benchmark."""
    over = 0
    for pair in pairs:
        answer = pair.get("answer", "")
        lines = answer.split("\n")
        if (
            len(answer) > FLASHCARD_MAX_TOTAL_CHARS
            or len(lines) > FLASHCARD_MAX_LINES
            or any(len(line) > FLASHCARD_MAX_CHARS_PER_LINE for line in lines)
        ):
            over += 1
    return over


def split_qa_chunk(number: int, chunk: str) -> dict | None:
    """Split one numbered Q&A chunk (the ground-truth extraction
    shape, used by the benchmark scorer only — NOT by the parser):
    ``?`` split first, then ``:``, then ``;``, then final ``.``.
    Kept here so the benchmark's matching rule is explicit."""
    text = " ".join(chunk.split())
    if "?" in text:
        question, answer = text.split("?", 1)
        return {
            "number": number,
            "question": question.strip() + "?",
            "answer": answer.strip(),
        }
    for sep in (":", ";"):
        if sep in text:
            question, answer = text.rsplit(sep, 1)
            if question.strip():
                return {
                    "number": number,
                    "question": question.strip(),
                    "answer": answer.strip(),
                }
    return None
