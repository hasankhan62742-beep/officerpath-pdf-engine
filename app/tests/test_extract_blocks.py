# OfficerPath AI — Phase 1, M4 tests: block parsing (spec §1.9-1.15,
# §2.7-2.10, §4.1-4.4, §6.15-6.18, §10.5).

from app.pipeline.extract.blocks import (
    compute_number_duplicates,
    compute_number_gaps,
    demote_decoded_numbers,
    interpolate_numbers,
    parse_one_liner,
    parse_standard_block,
    split_into_blocks,
)


def _lines(texts, page=1):
    return [
        {"index": i, "page": page, "text": t, "paper": "Paper 1", "part": ""}
        for i, t in enumerate(texts)
    ]


def test_standard_block_with_answer_line():
    block = _lines(
        [
            "1. Who is the current President of Pakistan?",
            "A) Arif Alvi",
            "B) Asif Ali Zardari",
            "C) Mamnoon Hussain",
            "D) Shehbaz Sharif",
            "Correct Answer: B) Asif Ali Zardari",
        ]
    )
    candidate, skip, exclude = parse_standard_block(block)
    assert skip is None and exclude is None
    assert candidate["number"] == 1
    assert candidate["text"] == "Who is the current President of Pakistan?"
    assert candidate["options"] == [
        "Arif Alvi",
        "Asif Ali Zardari",
        "Mamnoon Hussain",
        "Shehbaz Sharif",
    ]
    assert candidate["correct_index"] == 1
    assert candidate["answer_source"] == "answer-line"


def test_standard_block_tick_and_asterisk():
    block = _lines(
        [
            "1. What is the capital?",
            "(A) Karachi",
            "(B) Lahore ✓",
            "(C) Islamabad",
            "(D) Quetta",
        ]
    )
    candidate, _, _ = parse_standard_block(block)
    assert candidate["correct_index"] == 1
    assert candidate["answer_source"] == "tick"
    assert candidate["options"][1] == "Lahore"  # tick stripped, stored clean

    block = _lines(
        [
            "1. What is the capital?",
            "(A) Karachi",
            "(B) Lahore",
            "(C) Islamabad*",
            "(D) Quetta",
        ]
    )
    candidate, _, _ = parse_standard_block(block)
    assert candidate["correct_index"] == 2
    assert candidate["answer_source"] == "asterisk"


def test_standard_block_inline_options_shared_line():
    block = _lines(
        [
            "1. In which year did Pakistan come into being?",
            "(A) 1941 (B) 1942",
            "(C) 1947 (D) 1948",
        ]
    )
    candidate, _, _ = parse_standard_block(block)
    assert candidate is not None
    assert candidate["options"] == ["1941", "1942", "1947", "1948"]


def test_standard_block_three_options_excluded():
    # D6: 3-option questions are EXCLUDED with reason, never
    # normalised (Dart defines only 4 and 5->4).
    block = _lines(
        [
            "1. What is this?",
            "(A) One",
            "(B) Two",
            "(C) Three",
        ]
    )
    candidate, _, exclude = parse_standard_block(block)
    assert candidate is None
    assert exclude is not None and "3 options" in exclude


def test_standard_block_five_options_normalised():
    block = _lines(
        [
            "1. What is this?",
            "(A) One",
            "(B) Two",
            "(C) Three",
            "(D) Four",
            "(E) None of these",
            "Answer: B",
        ]
    )
    candidate, _, _ = parse_standard_block(block)
    assert candidate["options"] == ["One", "Two", "Three", "Four"]
    assert candidate["correct_index"] == 1
    assert candidate["five_normalised"] is True


def test_standard_block_five_options_no_answer_excluded():
    block = _lines(
        [
            "1. What is this?",
            "(A) One",
            "(B) Two",
            "(C) Three",
            "(D) Four",
            "(E) None of these",
        ]
    )
    candidate, _, exclude = parse_standard_block(block)
    assert candidate is None
    assert exclude is not None


def test_one_liner():
    entry = _lines(["2. What is the capital? (a) Karachi (b) Lahore (c) Islamabad (d) Quetta"])[0]
    candidate = parse_one_liner(entry)
    assert candidate is not None
    assert candidate["number"] == 2
    assert candidate["format"] == "one-liner"
    assert candidate["options"] == ["Karachi", "Lahore", "Islamabad", "Quetta"]
    # A compact key line (no question words) is not a one-liner.
    assert parse_one_liner(_lines(["1. A 2. B 3. C 4. D"])[0]) is None


def test_numberless_stem_recovery():
    lines = _lines(
        [
            "1. What is the capital of Pakistan?",
            "(A) Karachi",
            "(B) Lahore",
            "(C) Islamabad",
            "(D) Quetta",
            "Which river flows through Lahore?",
            "(A) Indus",
            "(B) Ravi",
            "(C) Chenab",
            "(D) Jhelum",
        ]
    )
    blocks = split_into_blocks(lines)
    assert len(blocks) == 2
    candidate, _, _ = parse_standard_block(blocks[1])
    assert candidate["text"] == "Which river flows through Lahore?"
    assert candidate["number"] is None


def test_interpolation_exact_fill_only():
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": None, "number_kind": "numberless", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 3, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    interpolate_numbers(candidates)
    assert candidates[1]["number"] == 2
    assert candidates[1]["number_kind"] == "interpolated"
    # A run that does NOT exactly fill the gap stays null.
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": None, "number_kind": "numberless", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": None, "number_kind": "numberless", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 5, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    interpolate_numbers(candidates)
    assert candidates[1]["number"] is None
    assert candidates[2]["number"] is None
    # A trailing run stays null (a new section may restart numbering).
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": None, "number_kind": "numberless", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    interpolate_numbers(candidates)
    assert candidates[1]["number"] is None
    # A leading run counts back from the first numbered block.
    candidates = [
        {"number": None, "number_kind": "numberless", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 2, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    interpolate_numbers(candidates)
    assert candidates[0]["number"] == 1


def test_decoded_number_demotion():
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 2, "number_kind": "decoded", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 3, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    demote_decoded_numbers(candidates)
    # The decoded 2 fits strictly between the trusted 1 and 3 -> kept.
    assert candidates[1]["number"] == 2
    # A decoded number duplicating a trusted number is demoted.
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 1, "number_kind": "decoded", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 3, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    demote_decoded_numbers(candidates)
    assert candidates[1]["number"] is None
    assert candidates[1]["number_kind"] == "demoted"
    # A decoded number NOT strictly after the previous trusted number
    # in reading order is demoted (here decoded 2 sits after clean 3).
    candidates = [
        {"number": 1, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 3, "number_kind": "clean", "options": ["a"] * 4, "paper": "Paper 1"},
        {"number": 2, "number_kind": "decoded", "options": ["a"] * 4, "paper": "Paper 1"},
    ]
    demote_decoded_numbers(candidates)
    assert candidates[2]["number"] is None


def test_number_gaps_and_duplicates():
    candidates = [
        {"number": 8, "number_kind": "clean", "page": 1},
        {"number": 10, "number_kind": "clean", "page": 2},
        {"number": 10, "number_kind": "clean", "page": 2},
    ]
    gaps = compute_number_gaps(candidates)
    assert len(gaps) == 1
    assert "Q9 missing between Q8 (page 1) and Q10 (page 2)" in gaps[0]
    duplicates = compute_number_duplicates(candidates)
    assert len(duplicates) == 1
    assert "Q10 appears 2 times (page 2, page 2)" in duplicates[0]
    # Bare-numbered books get NO gap report.
    assert (
        compute_number_gaps(
            [
                {"number": 8, "number_kind": "bare", "page": 1},
                {"number": 10, "number_kind": "bare", "page": 2},
            ]
        )
        == []
    )
    assert compute_number_gaps([{"number": 5, "number_kind": "clean", "page": 1}]) == []
