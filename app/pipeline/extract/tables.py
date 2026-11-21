# OfficerPath AI — PDF Engine (Phase 1, M4)
# Table-format parsing — port of the Dart parser rules, spec §9.
#
# (a) Delimiter-aware Sr# path — D8, an M4 ADDITION, not a Dart port
# (Dart has no delimiter rule, spec §9.8): pdfplumber table cells
# for digital PDFs (rows Sr#|Question|A|B|C|D|Ans), line-based
# splitting on the '|' / column structure for OCR text.
# (b) Row-wise grid path (§9.3, >= 2 rows, stem <= 400 chars).
# (c) Column-wise path (§9.2, >= 3 key-letter anchor, exactly-5N
# grouping).
# The table pass runs BEFORE the block loop and consumes its lines
# (§9.7).

from __future__ import annotations

import re

from app.pipeline.extract.markers import (
    TABLE_KEY_LETTER_RE,
    clean_stored,
    option_line_match,
    split_option_line,
)
from app.pipeline.extract.numbers import (
    normalize_urdu_digits,
    question_number_detailed,
    strip_question_number_prefix,
)
from app.pipeline.extract.signals import (
    BARE_ANSWER_RE,
    extract_option_signals,
    resolve_signals,
)

#: Spec §9.3: row-wise stem cap.
ROW_WISE_STEM_MAX_CHARS = 400


def _first_inline_marker(line: str) -> tuple[str, str, str] | None:
    """The first inline option marker in a line, if any. Returns
    (stem_tail, letter, option_text). Used by the Sr# path for lines
    carrying a single inline ``A.`` marker after the stem."""
    from app.pipeline.extract.markers import INLINE_MARKER_RE

    match = INLINE_MARKER_RE.search(line)
    if match is None:
        return None
    letter = match.group(1).upper()
    if letter not in ("A", "B", "C", "D", "1", "2", "3", "4"):
        return None
    if letter in ("1", "2", "3", "4"):
        letter = chr(64 + int(letter))
    stem_tail = line[: match.start()].strip()
    option_text = line[match.end() :].strip()
    if not option_text:
        return None
    return stem_tail, letter, option_text


def parse_sr_delimiter_lines(lines: list[dict]) -> tuple[list[dict], set[int]]:
    """D8 (M4 addition). Line-based Sr# rows: a bare-number line
    (the Sr#) followed by a stem line carrying an inline ``A.``
    marker, then ``B.``/``C.``/``D.`` lines, then a bare answer-letter
    line. This is the shape the TestPoint text layer actually
    produces (``Sr#`` is its own line; the question line carries
    ``A. <text>`` inline). Returns (questions, consumed indices)."""
    questions: list[dict] = []
    consumed: set[int] = set()
    i = 0
    while i < len(lines):
        text = lines[i]["text"].strip()
        if not re.fullmatch(r"\d+", normalize_urdu_digits(text)):
            i += 1
            continue
        number = int(normalize_urdu_digits(text))
        # The next line must carry an inline option split opening at A.
        j = i + 1
        stem_parts: list[str] = []
        options: list[dict] = []
        answer_index = -1
        answer_source = ""
        ok = False
        while j < len(lines) and len(options) < 4:
            line_text = lines[j]["text"]
            split = split_option_line(line_text)
            if split is not None and split[0][0] == "A":
                # Stem tail before the first marker joins the stem.
                first_marker = re.search(r"[\(\[]?\s*A\s*[\)\.\:\-]", line_text)
                if first_marker:
                    tail = line_text[: first_marker.start()].strip()
                    if tail:
                        stem_parts.append(tail)
                for letter, opt_text in split:
                    options.append({"letter": letter, "text": opt_text})
                j += 1
                continue
            single = option_line_match(line_text)
            if single is None:
                # A SINGLE inline "A." marker on the stem line (the
                # TestPoint shape: "Books are ... happiness. A. of")
                # — the tail before it is the stem, the rest is
                # option A.
                inline = _first_inline_marker(line_text)
                if inline is not None and not options:
                    stem_tail, letter, opt_text = inline
                    if letter == "A":
                        if stem_tail:
                            stem_parts.append(stem_tail)
                        options.append({"letter": "A", "text": opt_text})
                        j += 1
                        continue
            if single is not None:
                options.append({"letter": single[0], "text": single[1]})
                j += 1
                continue
            if options:
                # Options are complete but no answer line seen yet:
                # stop the row here (the answer line, if any, is
                # handled after the loop).
                break
            stem_parts.append(line_text.strip())
            j += 1
        # The bare answer-letter line follows the 4 options (the
        # option loop exits as soon as the 4th option is collected).
        if len(options) == 4 and j < len(lines):
            bare = BARE_ANSWER_RE.match(lines[j]["text"].strip())
            if bare:
                token = bare.group(1)
                if token.isdigit():
                    idx = int(token) - 1
                else:
                    idx = ord(token.upper()) - 65
                if 0 <= idx < 4:
                    answer_index = idx
                    answer_source = "key"
                j += 1
                ok = True
        if ok and len(options) == 4 and stem_parts:
            stem = " ".join(part for part in stem_parts if part).strip()
            questions.append(
                {
                    "number": number,
                    "text": clean_stored(stem),
                    "options": [clean_stored(o["text"]) for o in options],
                    "correct_index": answer_index,
                    "answer_source": answer_source,
                    "page": lines[i]["page"],
                    "paper": lines[i].get("paper", "Paper 1"),
                    "format": "table",
                }
            )
            consumed.update(range(i, j))
            i = j
        else:
            i += 1
    return questions, consumed


def parse_sr_pdfplumber_tables(pdf_bytes: bytes) -> list[dict]:
    """D8 (M4 addition). pdfplumber table cells for digital PDFs:
    rows ``Sr# | Question | A | B | C | D | Ans`` (an optional 8th
    Key column is ignored). Returns question dicts; empty when no
    such table exists."""
    try:
        import pdfplumber
    except ImportError:
        return []
    questions: list[dict] = []
    try:
        with pdfplumber.open(__import__("io").BytesIO(pdf_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    continue
                for table in tables:
                    for row in table:
                        if not row or len(row) < 7:
                            continue
                        cells = [(c or "").strip() for c in row]
                        if not re.fullmatch(r"\d+", cells[0]):
                            continue
                        question_text = " ".join(cells[1].split())
                        options = [" ".join(c.split()) for c in cells[2:6]]
                        if not question_text or any(not o for o in options):
                            continue
                        answer_token = cells[6].strip()
                        correct_index = -1
                        if re.fullmatch(r"[A-Da-d]", answer_token):
                            correct_index = ord(answer_token.upper()) - 65
                        questions.append(
                            {
                                "number": int(cells[0]),
                                "text": question_text,
                                "options": options,
                                "correct_index": correct_index,
                                "answer_source": ("key" if correct_index >= 0 else ""),
                                "page": page_number,
                                "paper": "Paper 1",
                                "format": "table",
                            }
                        )
    except Exception:
        return questions
    return questions


def _norm_text(text: str) -> str:
    """Comparison form for matching rows back to lines: bold marker
    stripped, Urdu digits unified, whitespace collapsed, lowercased.
    Stored text is never touched — this is matching only (D1)."""
    return " ".join(normalize_urdu_digits(text.replace("\ue000", "")).split()).lower()


def _option_value(text: str) -> str:
    """An option's value for comparison: a leading marker ("A. ",
    "(B) ") is stripped — pdfplumber cells carry the marker
    ("A. from") while the line stream's option rest does not
    ("from"). Without this, no option line ever matches."""
    matched = option_line_match(text)
    return _norm_text(matched[1]) if matched else _norm_text(text)


def match_pdfplumber_rows_to_lines(rows: list[dict], lines: list[dict]) -> set[int]:
    """Match pdfplumber Sr# rows back to the line entries they came
    from, so the grid/block passes do not re-parse them (§9.7).

    Without this, the pdfplumber fallback rows are appended but their
    lines stay unconsumed, and the grid path re-parses the same rows
    as numberless phantoms while the block pass re-parses them again
    (TestPoint in M4: 580 + 364 phantom rows, question precision
    0.54). A row matches only when a line containing its question
    stem is found on the same page (the bare Sr# line cannot anchor
    the match — bare numbers are noise-filtered, §3.12, before the
    table pass); from there only lines belonging to the row are
    consumed (question continuation lines, its 4 option lines, the
    Ans letter line). A row that cannot be matched is left
    unconsumed — the grid/block passes may still parse it, exactly
    as before this fix. Rows are processed in document order with a
    per-page cursor, so Sr# restarts across sections cannot match
    backwards.
    """
    consumed: set[int] = set()
    by_page: dict[int, list[dict]] = {}
    for entry in lines:
        by_page.setdefault(entry["page"], []).append(entry)
    cursor: dict[int, int] = {}
    for row in rows:
        page_lines = by_page.get(row["page"])
        if not page_lines:
            continue
        question_norm = _norm_text(row["text"])
        q_head = question_norm[:40]
        expected_options = {_option_value(o) for o in row.get("options", [])}
        # Anchor on the QUESTION line, not the Sr# line: bare Sr#
        # numbers are noise-filtered (§3.12) before the table pass,
        # so they are never in `lines`. The anchor is the earliest
        # unconsumed line on the page (at/after the cursor) whose
        # text contains the question stem's head.
        start = None
        pos = cursor.get(row["page"], 0)
        while pos < len(page_lines):
            entry = page_lines[pos]
            if entry["index"] not in consumed:
                # The line holds the 40-char stem head, or IS the stem's
                # start (wrapped stem's first line). The length floor
                # matters: a bare "a" is a substring of almost any
                # question and must never anchor a row. A leading Sr#
                # is stripped for comparison only — on some pages the
                # number sits on the same line as the stem ("102 The
                # words in these books will be of").
                text = _norm_text(entry["text"])
                text = re.sub(r"^\d+\s+", "", text)
                if q_head in text or (len(text) >= 10 and question_norm.startswith(text)):
                    start = pos
                    break
            pos += 1
        if start is None:
            continue
        j = start
        consumed.add(page_lines[j]["index"])
        j += 1
        # Question continuation lines: part of the question text, and
        # never a bare single letter (that is a marker/key line, not
        # a continuation). The first option line ends the stem — the
        # stem line itself may carry the first option inline.
        while j < len(page_lines):
            entry = page_lines[j]
            if entry["index"] in consumed:
                break
            text = _norm_text(entry["text"])
            if len(text) <= 1:
                break
            if option_line_match(entry["text"]) is not None:
                break
            # A continuation is a real fragment of the stem (length
            # floor: a 2-letter word is a substring of any question).
            if question_norm in text or (len(text) >= 6 and text in question_norm):
                consumed.add(entry["index"])
                j += 1
                continue
            break
        # Option lines (up to 4): a marker line whose rest matches one
        # of the row's options, or a bare option-value line. Options
        # may WRAP across lines ("A. She will / be praised / very
        # much / by you."): a rest that is a strict prefix of an
        # expected option also matches, and its continuation lines
        # are consumed while the accumulated text stays a prefix of
        # that option.
        seen_options = 0
        while j < len(page_lines) and seen_options < 4:
            entry = page_lines[j]
            if entry["index"] in consumed:
                break
            matched = option_line_match(entry["text"])
            rest = _norm_text(matched[1]) if matched else _norm_text(entry["text"])
            if rest in expected_options:
                consumed.add(entry["index"])
                j += 1
                seen_options += 1
                continue
            if len(rest) >= 3 and any(opt.startswith(rest) for opt in expected_options):
                consumed.add(entry["index"])
                j += 1
                seen_options += 1
                acc = rest
                while j < len(page_lines):
                    nxt = page_lines[j]
                    if nxt["index"] in consumed:
                        break
                    if option_line_match(nxt["text"]) is not None:
                        break
                    if TABLE_KEY_LETTER_RE.match(nxt["text"].strip()):
                        break
                    acc = (acc + " " + _norm_text(nxt["text"])).strip()
                    if not any(opt.startswith(acc) for opt in expected_options):
                        break
                    consumed.add(nxt["index"])
                    j += 1
                    if acc in expected_options:
                        break
                continue
            break
        # Ans letter line: a single A–E letter on its own line.
        if j < len(page_lines):
            entry = page_lines[j]
            if TABLE_KEY_LETTER_RE.match(entry["text"].strip()):
                consumed.add(entry["index"])
                j += 1
        cursor[row["page"]] = j
    # Header pass: the table's own header block ("Sr# / Question /
    # A / B / C / D / <type label> / Ans / Key") sits immediately
    # before each section's first row and is otherwise unconsumed,
    # so the grid/block passes assemble its fragments into
    # numberless phantom questions ("C D Prepositions Ans", "Ans
    # Key"). Consume the run starting at each "Sr#" line: known
    # header tokens, plus exactly one non-token line when the line
    # after it is "Ans"/"Key" (the section's type label). The run
    # stops at the first already-consumed line (a row anchor).
    _HEADER_TOKENS = {"question", "a", "b", "c", "d", "ans", "key"}
    for page_lines in by_page.values():
        j = 0
        while j < len(page_lines):
            entry = page_lines[j]
            token = _norm_text(entry["text"]).replace(" ", "")
            if token != "sr#" or entry["index"] in consumed:
                j += 1
                continue
            consumed.add(entry["index"])
            j += 1
            while j < len(page_lines):
                nxt = page_lines[j]
                if nxt["index"] in consumed:
                    break
                nxt_token = _norm_text(nxt["text"]).replace(" ", "")
                if nxt_token in _HEADER_TOKENS:
                    consumed.add(nxt["index"])
                    j += 1
                    continue
                after = page_lines[j + 1] if j + 1 < len(page_lines) else None
                after_token = _norm_text(after["text"]).replace(" ", "") if after else ""
                if after_token in {"ans", "key"}:
                    consumed.add(nxt["index"])
                    j += 1
                    continue
                break
    return consumed


def _nospace(text: str) -> str:
    """Comparison form with all whitespace removed: the line stream
    splits words mid-word across lines ("Retrospectiv" / "ely"),
    so a space-joined accumulation can never equal the cell value.
    Space-removed comparison is strictly more permissive — the
    marker-position and anchored-row guards carry the safety."""
    return "".join(_norm_text(text).split())


def _longest_common_substring(a: str, b: str) -> int:
    """Length of the longest common substring (difflib). Used for
    the garbage-cell case: pdfplumber merges adjacent cells, so a
    row's option value can be corrupted ("morning. B. She will be
    praised...") while still containing the true option text."""
    import difflib

    if not a or not b:
        return 0
    return difflib.SequenceMatcher(None, a, b).find_longest_match().size


def _option_run_matches(assembled: str, value: str) -> bool:
    """Does an assembled option run (marker line + continuations,
    joined) match a row's option value? True on any of:
    exact, prefix either way (truncated cell value), substring
    either way, longest common substring >= 15 chars (merged /
    garbage cells), or difflib ratio >= 0.6. ``assembled`` and
    ``value`` are space-removed normalised text."""
    import difflib

    if not assembled or not value:
        return False
    if assembled == value:
        return True
    if value.startswith(assembled) or assembled.startswith(value):
        return True
    if assembled in value or value in assembled:
        return True
    if _longest_common_substring(assembled, value) >= 15:
        return True
    return difflib.SequenceMatcher(None, assembled, value).ratio() >= 0.6


def _is_promo_line(text: str, stems: list[str]) -> bool:
    """Page furniture: a line carrying a domain token ("testpoint.pk",
    "example.com") and no question mark, that is not part of any
    row's stem. The TestPoint promo footer ("TestPoint.pk <Urdu:
    search Google for past papers>") is the measured case: 93 such
    lines, all unconsumed, each seeding a phantom question."""
    if "?" in text:
        return False
    # No trailing \b: the domain is often glued to Urdu text
    # ("testpoint.pkاپٹس..."), and Urdu letters are \w in Python
    # re, so "pk" + Urdu has no word boundary after it.
    if not re.search(r"\b[a-z0-9-]+\.(pk|com|org|net|edu)", text):
        return False
    compact = _nospace(text)
    return not any(compact in _nospace(stem) for stem in stems)


def consume_leftover_option_lines(
    rows: list[dict], lines: list[dict], consumed: set[int]
) -> set[int]:
    """Second pass (M5, positional — NOT adjacent): consume
    option lines that ``match_pdfplumber_rows_to_lines`` left free
    because the line stream does not follow table row order.

    Measured case (TestPoint p8, Active/Passive Voice): the line
    stream is COLUMN-ordered — all 5 stems, then all A-options,
    then all B-options... — while pdfplumber rows are ROW-ordered.
    The adjacency walk anchors on a stem and finds the NEXT stem,
    not its options, so every option line stays free and the
    grid/block passes reassemble them into numberless phantoms
    ("cheerfully by them every morning", 248 FPs in M4).

    How it works, per page:
    - Furniture first: promo (domain) lines and "Ans"/"Key" footer
      lines are consumed — they are never question content.
    - Only rows whose stem was consumed in pass 1 ("anchored")
      contribute option values. A row pdfplumber found but pass 1
      could not anchor keeps ALL its lines free for the grid/block
      passes — this pass never hides an unparsed question.
    - Free lines are scanned in stream order. A marker line (or a
      bare option-start line) opens a RUN: itself plus the following
      free bare lines, stopping early as soon as the run completes
      an option value, and never past the next marker line. The
      run is consumed only when its assembled text fuzzy-matches
      an option value of an anchored row on the same page — and,
      for marker lines, at the marker's own position (A=0..D=3).
      A run that matches nothing is left entirely free.
    - Garbage cells are handled by the fuzzy match: a merged cell
      ("morning. B. She will be praised...") still contains the
      true option as a substring, and a corrupted cell ("eCv.
      eSrhye will being praised...") still shares a >= 15-char
      substring with it.
    """
    extra: set[int] = set()
    by_page: dict[int, list[dict]] = {}
    for entry in lines:
        by_page.setdefault(entry["page"], []).append(entry)
    for page, page_lines in by_page.items():
        page_rows = [r for r in rows if r.get("page") == page]
        if not page_rows:
            continue
        stems = [_norm_text(r.get("text", "")) for r in page_rows]
        # --- furniture -------------------------------------------
        for entry in page_lines:
            if entry["index"] in consumed or entry["index"] in extra:
                continue
            text = _norm_text(entry["text"])
            if _is_promo_line(text, stems):
                extra.add(entry["index"])
                continue
            if text.replace(" ", "") in {"ans", "key", "anskey"}:
                extra.add(entry["index"])
        # --- anchored rows only ----------------------------------
        anchored: list[dict] = []
        for row in page_rows:
            question_norm = _norm_text(row.get("text", ""))
            q_head = question_norm[:40]
            for entry in page_lines:
                if entry["index"] not in consumed:
                    continue
                text = _norm_text(entry["text"])
                text = re.sub(r"^\d+\s+", "", text)
                if q_head in text or (len(text) >= 10 and question_norm.startswith(text)):
                    anchored.append(row)
                    break
        if not anchored:
            continue
        # Option values per anchored row, space-removed, by position.
        # values[position] = list of (row, value_nospace).
        values: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
        all_values: list[str] = []
        for row in anchored:
            for pos, option in enumerate(row.get("options", [])[:4]):
                value = _nospace(_option_value(option))
                if len(value) >= 2:
                    values[pos].append(value)
                    all_values.append(value)
        if not all_values:
            continue
        free = [e for e in page_lines if e["index"] not in consumed and e["index"] not in extra]
        i = 0
        while i < len(free):
            entry = free[i]
            matched = option_line_match(entry["text"])
            if matched is not None:
                letter = matched[0].upper()
                position = ord(letter) - ord("A") if letter in "ABCD" else None
                candidates = values.get(position, []) if position is not None else []
                run, end = _assemble_run(free, i, candidates)
                if position is not None and _run_matches(run, candidates):
                    extra.update(e["index"] for e in run)
                    i = end
                    continue
                i += 1
                continue
            # Bare line: an option start only when it is a >= 6-char
            # prefix of an anchored row's option value (a lone word
            # like "every" is too weak — it stays free).
            text_nospace = _nospace(entry["text"])
            if len(text_nospace) >= 6 and any(v.startswith(text_nospace) for v in all_values):
                run, end = _assemble_run(free, i, all_values)
                if _run_matches(run, all_values):
                    extra.update(e["index"] for e in run)
                    i = end
                    continue
            i += 1
    return extra


def _assemble_run(free: list[dict], start: int, candidates: list[str]) -> tuple[list[dict], int]:
    """Assemble an option run: the line at ``start`` plus the
    following free BARE lines, stopping before the next marker line
    or key-letter line, and stopping EARLY as soon as the run's
    text already completes a candidate option value (the value is
    a prefix of the assembled text — the cell value may be
    truncated, so the run is done). The early stop is what keeps a
    stem line that follows an option out of the run: the option
    completes first, so the stem is never appended. The run is
    bounded to 8 lines: a real option wraps at most a few lines,
    and an unbounded run would swallow the next question."""
    run = [free[start]]
    j = start + 1
    while j < len(free) and len(run) < 8:
        nxt = free[j]
        if option_line_match(nxt["text"]) is not None:
            break
        if TABLE_KEY_LETTER_RE.match(nxt["text"].strip()):
            break
        run.append(nxt)
        j += 1
        # Stop as soon as the run completes a candidate value
        # (assembled == value, or the value is a prefix of the
        # assembled text because the cell value was truncated).
        # A stem line that follows a complete option is therefore
        # never appended.
        if any(_run_text(run).startswith(v) for v in candidates):
            break
    return run, j


def _run_text(run: list[dict]) -> str:
    """A run's assembled text, space-removed: the first line's
    option rest (or whole text for a bare first line) plus the
    continuation lines."""
    if not run:
        return ""
    first = run[0]
    matched = option_line_match(first["text"])
    parts = [_nospace(matched[1])] if matched is not None else [_nospace(first["text"])]
    for entry in run[1:]:
        parts.append(_nospace(entry["text"]))
    return "".join(parts)


def _run_matches(run: list[dict], candidates: list[str]) -> bool:
    """Fuzzy-match a run's assembled text against the candidate
    option values (see ``_option_run_matches``)."""
    if not run or not candidates:
        return False
    assembled = _run_text(run)
    if len(assembled) < 2:
        return False
    return any(_option_run_matches(assembled, value) for value in candidates)


def parse_pipe_delimiter_lines(lines: list[dict]) -> tuple[list[dict], set[int]]:
    """D8 (M4 addition). OCR-text ``|``-delimited rows: a line with
    >= 6 ``|``-separated segments whose first segment is numeric
    (Sr#) and whose last segment is a single answer letter."""
    questions: list[dict] = []
    consumed: set[int] = set()
    for entry in lines:
        parts = [part.strip() for part in entry["text"].split("|")]
        if len(parts) < 7:
            continue
        if not re.fullmatch(r"\d+", normalize_urdu_digits(parts[0])):
            continue
        options = parts[2:6]
        if any(not opt for opt in options):
            continue
        answer_token = parts[6]
        correct_index = -1
        if re.fullmatch(r"[A-Da-d]", answer_token):
            correct_index = ord(answer_token.upper()) - 65
        questions.append(
            {
                "number": int(normalize_urdu_digits(parts[0])),
                "text": clean_stored(parts[1]),
                "options": [clean_stored(o) for o in options],
                "correct_index": correct_index,
                "answer_source": "key" if correct_index >= 0 else "",
                "page": entry["page"],
                "paper": entry.get("paper", "Paper 1"),
                "format": "table",
            }
        )
        consumed.add(entry["index"])
    return questions, consumed


#: Lowercase words allowed inside a Title-Cased type label
#: ("Article and its Types").
_TYPE_LABEL_FUNCTION_WORDS: frozenset[str] = frozenset(
    {"and", "or", "of", "its", "the", "a", "an", "in", "on", "for", "with", "to", "by", "from"}
)


def _looks_like_type_label(anchor: str) -> bool:
    """A type label is 1-5 words, Title-Cased apart from a small
    allowlist of lowercase function words. A wrapped stem fragment
    ("In which city will COP31 be") fails it and is never an
    anchor."""
    words = anchor.split()
    if not words or len(words) > 5:
        return False
    for word in words:
        stripped = word.strip(".,;:!?()[]{}" + chr(34) + chr(39))
        if not stripped:
            continue
        if stripped[0].isupper() or stripped.isdigit():
            continue
        if stripped.lower() in _TYPE_LABEL_FUNCTION_WORDS:
            continue
        return False
    return True


def parse_table_rows_grid(
    lines: list[dict],
) -> tuple[list[dict], list[dict], set[int]]:
    """Spec §9.3. Row-wise: question line(s) + 4 bare option lines
    anchored by a key letter or a type label; >= 2 rows; stem <= 400
    chars. Tick/bold on an option resolves a key-less row; a
    key-vs-tick/bold disagreement is a recorded conflict, key wins.
    Rows without a usable key become pending (returned separately) —
    never silently dropped. Returns (rows, pending_rows, consumed).

    Recognition is by look-back from the anchor: a key-letter (or
    type-label) line is preceded by >= 5 plain lines — the last 4
    are the bare option values, the earlier ones the stem. Bare
    option lines carry no markers; a line WITH a marker contributes
    its text as one option."""
    rows: list[dict] = []
    pending: list[dict] = []
    consumed: set[int] = set()
    conflicts: list[str] = []
    n = len(lines)

    def _is_plain(entry: dict) -> bool:
        text = entry["text"].strip()
        if not text:
            return False
        if TABLE_KEY_LETTER_RE.match(text):
            return False
        return question_number_detailed(text) is None

    def _anchor_at(k: int) -> tuple[bool, int | None]:
        anchor = lines[k]["text"].strip()
        key_match = TABLE_KEY_LETTER_RE.match(anchor)
        if key_match:
            idx = ord(key_match.group(1).upper()) - 65
            return True, idx if 0 <= idx < 4 else None
        if (
            anchor
            and len(anchor) <= 40
            and "?" not in anchor
            and "؟" not in anchor
            and ":" not in anchor
            and not option_line_match(anchor)
            and question_number_detailed(anchor) is None
            and _looks_like_type_label(anchor)
        ):
            # A type label (e.g. "Noun") anchors the row. It never
            # contains ":" — "Correct Answer: B) ..." is an answer
            # line, not a label.
            return True, None
        return False, None

    i = 0
    while i < n:
        anchored, key_index = _anchor_at(i)
        if not anchored:
            i += 1
            continue
        # Look back over plain lines (max 8: stem lines + 4 options).
        start = i - 1
        plain: list[int] = []
        while start >= 0 and len(plain) < 8 and _is_plain(lines[start]):
            plain.append(start)
            start -= 1
        plain.reverse()
        if len(plain) < 5:
            i += 1
            continue
        option_positions = plain[-4:]
        stem_positions = plain[:-4]
        # A genuine table stem never carries an option marker: if any
        # stem line is an option line, the "row" is really a standard
        # block (e.g. CA40's A)-D) lines + "Correct Answer:" line
        # under a section heading used as a type-label anchor).
        if any(option_line_match(lines[p]["text"].strip()) is not None for p in stem_positions):
            i += 1
            continue
        stem = clean_stored(
            strip_question_number_prefix(" ".join(lines[p]["text"].strip() for p in stem_positions))
        )
        if not stem or len(stem) > ROW_WISE_STEM_MAX_CHARS:
            i += 1
            continue
        option_texts: list[str] = []
        option_signals: list[dict[str, bool]] = []
        for p in option_positions:
            raw = lines[p]["text"].strip()
            single = option_line_match(raw)
            option_texts.append(clean_stored(single[1]) if single else clean_stored(raw))
            option_signals.append(extract_option_signals(raw))
        correct_index, source, row_conflicts = resolve_signals(
            option_signals, None, key_index, option_texts
        )
        conflicts.extend(row_conflicts)
        record = {
            "number": None,
            "text": stem,
            "options": option_texts,
            "correct_index": correct_index,
            "answer_source": source,
            "page": lines[stem_positions[0]]["page"],
            "paper": lines[stem_positions[0]].get("paper", "Paper 1"),
            "format": "table",
        }
        if correct_index >= 0:
            rows.append(record)
        else:
            pending.append({**record, "reason": "no-key-entry"})
        consumed.update(range(stem_positions[0], i + 1))
        i += 1
    if len(rows) + len(pending) < 2:
        # Spec §9.3: >= 2 rows minimum — a single row is not a table.
        return [], [], set()
    return rows, pending, consumed


def parse_table_columns(lines: list[dict]) -> tuple[list[dict], set[int]]:
    """Spec §9.2. Column-wise: a run of >= 3 key letters is the
    anchor; the pre-key region must group into exactly 5N items (N
    questions + 4N options). Type labels follow the key run."""
    key_runs: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if TABLE_KEY_LETTER_RE.match(lines[i]["text"].strip()):
            start = i
            while i < len(lines) and TABLE_KEY_LETTER_RE.match(lines[i]["text"].strip()):
                i += 1
            if i - start >= 3:
                key_runs.append((start, i))
        else:
            i += 1
    if not key_runs:
        return [], set()
    # Use the first qualifying run as the anchor.
    key_start, key_end = key_runs[0]
    pre_key = lines[:key_start]
    items: list[str] = []
    for entry in pre_key:
        text = entry["text"].strip()
        if not text:
            continue
        items.append(text)
    if not items or len(items) % 5 != 0:
        return [], set()
    n = len(items) // 5
    key_letters = [
        TABLE_KEY_LETTER_RE.match(lines[k]["text"].strip()).group(1).upper()  # type: ignore[union-attr]
        for k in range(key_start, key_end)
    ]
    if len(key_letters) < n:
        return [], set()
    questions: list[dict] = []
    consumed: set[int] = set()
    for q in range(n):
        stem = clean_stored(items[q * 5])
        options = [clean_stored(items[q * 5 + 1 + k]) for k in range(4)]
        letter = key_letters[q]
        idx = ord(letter) - 65
        if not (0 <= idx < 4):
            continue
        questions.append(
            {
                "number": None,
                "text": stem,
                "options": options,
                "correct_index": idx,
                "answer_source": "key",
                "page": pre_key[0]["page"] if pre_key else 0,
                "paper": pre_key[0].get("paper", "Paper 1") if pre_key else "Paper 1",
                "format": "table",
            }
        )
    consumed.update(entry["index"] for entry in pre_key)
    consumed.update(range(key_start, key_end))
    return questions, consumed
