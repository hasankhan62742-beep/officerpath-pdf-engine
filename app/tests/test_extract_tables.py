# OfficerPath AI — Phase 1, M4 tests: table formats (spec §9) and
# the D8 delimiter-aware Sr# path (M4 addition).

from app.pipeline.extract.tables import (
    match_pdfplumber_rows_to_lines,
    parse_pipe_delimiter_lines,
    parse_sr_delimiter_lines,
    parse_table_columns,
    parse_table_rows_grid,
)


def _lines(texts, page=1):
    return [
        {"index": i, "page": page, "text": t, "paper": "Paper 1", "part": ""}
        for i, t in enumerate(texts)
    ]


def test_sr_delimiter_lines_testpoint_shape():
    lines = _lines(
        [
            "Sr#",
            "Question",
            "A",
            "B",
            "C",
            "D",
            "Ans",
            "Key",
            "1",
            "Books are a great source _______ happiness. A. of",
            "B. for",
            "C. on",
            "D. with",
            "A",
            "2",
            "This flying coach is bound______Karachi.",
            "A. For",
            "B. From",
            "C. To",
            "D. None",
            "A",
        ]
    )
    questions, consumed = parse_sr_delimiter_lines(lines)
    assert len(questions) == 2
    assert questions[0]["number"] == 1
    assert questions[0]["options"] == ["of", "for", "on", "with"]
    assert questions[0]["correct_index"] == 0
    assert questions[0]["answer_source"] == "key"
    assert questions[1]["options"] == ["For", "From", "To", "None"]
    assert len(consumed) > 0


def test_pipe_delimiter_lines():
    lines = _lines(["1 | What is the capital? | Karachi | Lahore | Islamabad | Quetta | C"])
    questions, consumed = parse_pipe_delimiter_lines(lines)
    assert len(questions) == 1
    assert questions[0]["number"] == 1
    assert questions[0]["options"] == ["Karachi", "Lahore", "Islamabad", "Quetta"]
    assert questions[0]["correct_index"] == 2
    assert len(consumed) == 1


def test_table_rows_grid():
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
    assert rows[0]["options"] == ["Karachi", "Lahore", "Islamabad", "Quetta"]
    assert rows[0]["correct_index"] == 2
    assert rows[0]["answer_source"] == "key"
    assert rows[1]["correct_index"] == 1
    assert pending == []
    assert len(consumed) > 0


def test_table_rows_grid_needs_two_rows():
    lines = _lines(["What is the capital?", "Karachi", "Lahore", "Islamabad", "Quetta", "C"])
    rows, pending, consumed = parse_table_rows_grid(lines)
    assert rows == [] and pending == [] and consumed == set()


def test_table_rows_grid_answer_line_is_not_a_label():
    # "Correct Answer: B) ..." must NOT anchor a table row — it is
    # an answer line for the block pass.
    lines = _lines(
        [
            "1. Who is the current President of Pakistan?",
            "A) Arif Alvi",
            "B) Asif Ali Zardari",
            "C) Mamnoon Hussain",
            "D) Shehbaz Sharif",
            "Correct Answer: B) Asif Ali Zardari",
            "2. Who is the Prime Minister?",
            "A) Imran Khan",
            "B) Nawaz Sharif",
            "C) Shehbaz Sharif",
            "D) Bilawal Bhutto Zardari",
            "Correct Answer: C) Shehbaz Sharif",
        ]
    )
    rows, pending, consumed = parse_table_rows_grid(lines)
    assert rows == [] and consumed == set()


def test_table_columns():
    lines = _lines(
        [
            "What is the capital?",
            "Karachi",
            "Lahore",
            "Islamabad",
            "Quetta",
            "Which river flows through Lahore?",
            "Indus",
            "Ravi",
            "Chenab",
            "Jhelum",
            "C",
            "B",
            "A",
        ]
    )
    # Pre-key region must group into exactly 5N items: here 10 items
    # (2 questions + 8 options) and a >= 3 key-letter run.
    questions, consumed = parse_table_columns(lines)
    assert len(questions) == 2
    assert questions[0]["correct_index"] == 2
    assert questions[1]["correct_index"] == 1
    assert len(consumed) > 0


def test_table_columns_rejects_non_5n():
    lines = _lines(["What is the capital?", "Karachi", "Lahore", "Islamabad", "C", "B", "A"])
    questions, consumed = parse_table_columns(lines)
    assert questions == [] and consumed == set()


def test_match_pdfplumber_rows_consumes_testpoint_lines():
    # TestPoint page-1 shape as the table pass actually sees it: the
    # bare Sr# lines are noise-filtered (§3.12) before the table pass,
    # so each row is a question line carrying the first option inline,
    # three option lines and the Ans letter line. The matcher must
    # consume exactly those lines so the grid/block passes cannot
    # re-parse them.
    lines = _lines(
        [
            "Page 1 of 86",
            "Sr#",
            "Question",
            "A",
            "B",
            "C",
            "D",
            "Ans",
            "Key",
            "Books are a great source _______ happiness. A. of",
            "B. for",
            "C. on",
            "D. with",
            "A",
            "This flying coach is bound______Karachi.",
            "A. For",
            "B. From",
            "C. To",
            "D. None",
            "A",
            "Green pepper is very rich __________ ",
            "vitamin C?",
            "A. of",
            "B. in",
            "C. about",
            "D. on",
            "B",
        ]
    )
    rows = [
        {
            "number": 1,
            "text": "Books are a great source _______ happiness.",
            "options": ["of", "for", "on", "with"],
            "correct_index": 0,
            "page": 1,
        },
        {
            "number": 2,
            "text": "This flying coach is bound______Karachi.",
            "options": ["For", "From", "To", "None"],
            "correct_index": 0,
            "page": 1,
        },
        {
            "number": 3,
            "text": "Green pepper is very rich __________ vitamin C?",
            "options": ["of", "in", "about", "on"],
            "correct_index": 1,
            "page": 1,
        },
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    # Header run 1-8, row 1: indices 9-13, row 2: 14-19, row 3
    # (wrapped stem): 20-26. Only the page furniture line 0 stays
    # unconsumed.
    assert consumed == set(range(1, 27))
    assert 0 not in consumed


def test_match_pdfplumber_rows_consumes_table_header():
    # The header block before a section's first row must be consumed
    # too, or the grid/block passes assemble its fragments into
    # numberless phantom questions ("C D Prepositions Ans").
    lines = _lines(
        [
            "English Important",
            "Sr#",
            "Question",
            "A",
            "B",
            "C",
            "D",
            "Prepositions",
            "Ans",
            "Key",
            "Books are a great source _______ happiness. A. of",
            "B. for",
            "C. on",
            "D. with",
            "A",
        ]
    )
    rows = [
        {
            "number": 1,
            "text": "Books are a great source _______ happiness.",
            "options": ["of", "for", "on", "with"],
            "correct_index": 0,
            "page": 1,
        }
    ]
    consumed = match_pdfplumber_rows_to_lines(rows, lines)
    # Header run 1-9 plus the row's lines 10-14; the page furniture
    # line 0 stays unconsumed.
    assert consumed == set(range(1, 15))
    assert 0 not in consumed


def test_match_pdfplumber_rows_marker_prefixed_options():
    # pdfplumber cells carry the marker ("A. from") while the line
    # stream's option rest does not ("from"). The matcher must strip
    # the marker when comparing, or no option line ever matches and
    # the grid pass re-parses the row's options as phantoms.
    lines = _lines(
        [
            "Nafeesa is afraid ___________spiders?",
            "A. from",
            "B. in",
            "C. about",
            "D. of",
            "D",
        ],
        page=2,
    )
    rows = [
        {
            "number": 18,
            "text": "Nafeesa is afraid ___________spiders?",
            "options": ["A. from", "B. in", "C. about", "D. of"],
            "correct_index": 3,
            "page": 2,
        }
    ]
    assert match_pdfplumber_rows_to_lines(rows, lines) == set(range(6))


def test_match_pdfplumber_rows_wrapped_option():
    # An option wrapped across lines ("A. She will / be praised /
    # very much / by you."): the marker line's rest is only a prefix
    # of the full option, and its continuation lines belong to the
    # same row — all must be consumed.
    lines = _lines(
        [
            "They greet me cheerfully every morning.",
            "A. She will",
            "be praised",
            "very much",
            "by you.",
            "B. He will",
            "be scolded",
            "C. They will",
            "be rewarded",
            "D. We will",
            "be ignored",
            "A",
        ],
        page=8,
    )
    rows = [
        {
            "number": 40,
            "text": "They greet me cheerfully every morning.",
            "options": [
                "She will be praised very much by you.",
                "He will be scolded",
                "They will be rewarded",
                "We will be ignored",
            ],
            "correct_index": 0,
            "page": 8,
        }
    ]
    assert match_pdfplumber_rows_to_lines(rows, lines) == set(range(12))


def test_match_pdfplumber_rows_skips_unmatchable_row():
    lines = _lines(["Some other question entirely.", "A. x", "B. y", "C. z", "D. w", "A"])
    rows = [
        {
            "number": 1,
            "text": "A question that is nowhere in these lines.",
            "options": ["of", "for", "on", "with"],
            "correct_index": 0,
            "page": 1,
        }
    ]
    # No line carries the question stem: nothing consumed. The
    # grid/block passes may still parse the lines, as before.
    assert match_pdfplumber_rows_to_lines(rows, lines) == set()
