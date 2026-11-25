# OfficerPath AI — A1 tests: per-page intelligent routing (gap report
# F1) + the NOA Maths shape it unlocks: "Question#N" numbers,
# radio-glyph options, "Correct Answer Is:" lines, and the table-grid
# pass leaving standard blocks alone.
#
# Measured NOA Maths baseline (2026-11-25, Tesseract 5.3.4, this VM):
# before A1 the 13-page scan gave 0 questions (document-level
# total_chars >= 100 called the watermarked scan "digital"); after
# A1 it gives 17 questions, 17 answered, 17/17 correct against the
# paper's printed "Correct Answer Is:" lines, 9 pending fragments,
# 4 qa_pairs. The acceptance test below pins the floors, not the
# exact count, so a future OCR wobble does not fail it spuriously.

from pathlib import Path

from app.pipeline.extract.blocks import parse_standard_block
from app.pipeline.extract.keys import resolve_answer_token
from app.pipeline.extract.markers import symbol_option_match
from app.pipeline.extract.numbers import (
    question_number_detailed,
    strip_question_number_prefix,
)
from app.pipeline.extract.qa import scan_flashcards
from app.pipeline.extract.signals import ANSWER_LINE_RE
from app.pipeline.extract.tables import parse_table_rows_grid
from app.pipeline.matching.service import parse_document_bytes

FIXTURE = Path(__file__).parent / "fixtures" / "golden" / "ppsc66" / "Math_test_NOA.pdf"


def test_question_hash_numbers():
    assert question_number_detailed("Question#1") == (1, False)
    assert question_number_detailed("Question#45") == (45, False)
    assert question_number_detailed("Question #7") == (7, False)
    assert question_number_detailed("question#12") == (12, False)
    # No "#" — not a hash number (the old "Question 12" shape stays None).
    assert question_number_detailed("Question 12") is None
    assert strip_question_number_prefix("Question#3 What is 2+2?") == "What is 2+2?"
    assert strip_question_number_prefix("Question #3 What is 2+2?") == "What is 2+2?"


def test_symbol_options():
    assert symbol_option_match("© 274") == "274"
    assert symbol_option_match("@ 364.50") == "364.50"
    assert symbol_option_match("O None Of These") == "None Of These"
    assert symbol_option_match("O 48 Km/Hr") == "48 Km/Hr"
    # No-space form: Tesseract drops the gap before a numeric option.
    assert symbol_option_match("@171") == "171"
    assert symbol_option_match("O8") == "8"
    assert symbol_option_match("O10Km") == "10Km"
    # Prose never matches: "Of..." has a letter after O, "O2 is a
    # gas" has words after the number.
    assert symbol_option_match("Of the following") is None
    assert symbol_option_match("O2 is a gas") is None
    assert symbol_option_match("A. Paris") is None


def test_answer_line_is_variants():
    assert ANSWER_LINE_RE.match("Correct Answer Is: 364.50").group(1) == "364.50"
    assert ANSWER_LINE_RE.match("Correct Answer: B").group(1) == "B"
    # OCR misreads of "Is" — the colon is still required.
    assert ANSWER_LINE_RE.match("Correct Answer |s: 15.072 Km").group(1) == "15.072 Km"
    assert ANSWER_LINE_RE.match("Correct Answer I5: 42").group(1) == "42"
    assert ANSWER_LINE_RE.match("Correct Answer 1s: 42").group(1) == "42"
    assert ANSWER_LINE_RE.match("Correct answer is 42") is None


def test_resolve_answer_token_prefer_text():
    opts = ["1/2", "zero", "1", "None Of These"]
    # Default order (spec §6.7): a bare number is an INDEX.
    assert resolve_answer_token("1", opts) == 0
    # Inline "Correct Answer Is:" states a VALUE — the exact text
    # match wins (NOA Maths Q8: the paper's key says "1", option C
    # is the text "1", not option A "1/2").
    assert resolve_answer_token("1", opts, prefer_text=True) == 2
    # No text match -> the index reading is the fallback.
    assert resolve_answer_token("2", ["a", "b", "c", "d"], prefer_text=True) == 1
    # A letter token is untouched by prefer_text.
    assert resolve_answer_token("B", ["x", "y"], prefer_text=True) == 1
    opts = ["274", "367.20", "364.50", "None Of These"]
    assert resolve_answer_token("364.50", opts, prefer_text=True) == 2


def _lines(texts, page=1):
    return [
        {"index": i, "page": page, "text": t, "paper": "Paper 1", "part": "", "qa_number": None}
        for i, t in enumerate(texts)
    ]


def test_table_rows_grid_ignores_symbol_option_blocks():
    # NOA Maths p1 shape: the 4th option "O None Of These" looks
    # like a type label, and "Scanned with CamScanner" (watermark)
    # does too — neither may anchor a table row that eats the
    # question's own lines.
    lines = _lines(
        [
            "Question#1",
            "16% of a number is 216. What is 27% of that number?",
            "© 274",
            "© 367.20",
            "@ 364.50",
            "O None Of These",
            "Correct Answer Is: 364.50",
            "Question#2",
            "What is the value of x?",
            "© 25m",
            "@ 30m",
            "O 35m",
            "© 40m",
            "Correct Answer Is: 30m",
            "Scanned with CamScanner",
        ]
    )
    rows, pending, consumed = parse_table_rows_grid(lines)
    assert rows == [] and pending == [] and consumed == set()


def test_table_rows_grid_still_works_for_bare_tables():
    # The guard must not break the genuine table shape: bare option
    # values + a key letter still form rows.
    lines = _lines(
        [
            "What is the capital of Pakistan?",
            "Karachi",
            "Lahore",
            "Islamabad",
            "Quetta",
            "C",
            "Which river flows through Lahore?",
            "Indus",
            "Ravi",
            "Chenab",
            "Jhelum",
            "B",
        ]
    )
    rows, pending, consumed = parse_table_rows_grid(lines)
    assert len(rows) == 2
    assert rows[0]["correct_index"] == 2
    assert rows[1]["correct_index"] == 1


def test_flashcards_ignore_bare_answer_lines():
    # A bare answer line is not a question — the trailing-answer
    # split used to turn it into a junk pair with question
    # "Correct Answer Is:".
    pairs, _ = scan_flashcards(_lines(["Correct Answer Is: 171"]))
    assert pairs == []
    pairs, _ = scan_flashcards(_lines(["_ Correct Answer Is: 1116"]))
    assert pairs == []
    # A real inline Q&A on one line still forms a pair.
    pairs, _ = scan_flashcards(_lines(["6. Which Key Is Used For Help in PowerPoint: F1"]))
    assert len(pairs) == 1
    assert pairs[0]["question"] == "Which Key Is Used For Help in PowerPoint:"
    assert pairs[0]["answer"] == "F1"


def test_symbol_options_parse_as_a_block():
    # End to end at the block level: a Question#N block with
    # symbol options and an inline answer line parses with the
    # right answer (positional: 3rd option = C).
    block = _lines(
        [
            "Question#1",
            "16% of a number is 216. What is 27% of that number?",
            "© 274",
            "© 367.20",
            "@ 364.50",
            "O None Of These",
            "Correct Answer Is: 364.50",
        ]
    )
    candidate, _, _ = parse_standard_block(block)
    assert candidate is not None
    assert candidate["number"] == 1
    assert candidate["options"] == ["274", "367.20", "364.50", "None Of These"]
    assert candidate["correct_index"] == 2
    assert candidate["answer_source"] == "answer-line"


def test_noa_maths_per_page_routing():
    """A1 acceptance: the NOA Maths scan (13 pages, CamScanner
    watermark on every page) must no longer parse as 0 questions.
    Floors, not exact counts: OCR wobble must not fail this test.
    """
    pdf_bytes = FIXTURE.read_bytes()
    matched, _report, debug = parse_document_bytes(
        pdf_bytes, "00000000-0000-0000-0000-000000000000"
    )
    counts = matched.counts
    assert counts["questions"] >= 15, counts
    assert counts["answered"] == counts["questions"], counts
    assert counts["duplicates"] == 0, counts
    # Every page classified mixed (watermark + photo) and routed to OCR.
    classifications = debug["page_classifications"]
    assert len(classifications) == 13, classifications
    assert set(classifications.values()) == {"mixed"}, classifications
    routes = debug["page_routes"]
    assert len(routes) == 13, routes
    # Mixed pages take BOTH paths: the digital blocks are kept and
    # OCR runs for the scanned content — that is the A1 fix.
    assert all(v == ["digital-pymupdf", "tesseract"] for v in routes.values()), routes
    # The watermark is never a question, and no question text is
    # watermark-only.
    for q in matched.questions:
        assert "CamScanner" not in q.text, q.text
        assert q.text.strip() != "Scanned with CamScanner"
    # Exact answers, checked against the paper's printed key lines.
    by_number = {q.number: q for q in matched.questions}
    q1 = by_number[1]
    assert q1.correct_index == 2 and q1.options[2] == "364.50"
    q3 = by_number[3]
    assert q3.correct_index == 2 and q3.options[2] == "17m"
    q4 = by_number[4]
    assert q4.correct_index == 1 and q4.options[1] == "36"
    # Q8 proves the prefer_text fix: printed "Correct Answer Is: 1",
    # option C is the text "1" (not option A "1/2").
    q8 = by_number[8]
    assert q8.correct_index == 2 and q8.options[2] == "1"
