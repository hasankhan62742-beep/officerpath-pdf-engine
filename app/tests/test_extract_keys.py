# OfficerPath AI — Phase 1, M4 tests: answer keys and the
# paper-identity gate (spec §5-§6.4-6.10).

from app.pipeline.extract.keys import (
    decide_key_match,
    is_answer_key_heading,
    is_key_only_line,
    is_unknown_key_token,
    key_heading_remainder,
    normalise_bare_q_entries,
    normalise_paper_title,
    orphan_adoption_eligible,
    parse_key_entries,
    resolve_answer_token,
)

OPTIONS = ["Arif Alvi", "Asif Ali Zardari", "Mamnoon Hussain", "Shehbaz Sharif"]


def test_key_heading_forms():
    assert is_answer_key_heading("Answer Key")
    assert is_answer_key_heading("Answers")
    assert is_answer_key_heading("Correct Answers")
    assert is_answer_key_heading("(Answer Key)")
    assert is_answer_key_heading("Answer Key (January 2026)")
    # A lone singular "Answer:" never OPENS a key section — but it IS
    # an answer line (tested in test_extract_signals).
    assert not is_answer_key_heading("Answer: B")
    assert not is_answer_key_heading("Answer: (B)")


def test_key_heading_remainder():
    heading, remainder = key_heading_remainder("ANSWER KEY: 1. (B) Broke out")
    assert remainder == "1. (B) Broke out"
    heading, remainder = key_heading_remainder("ANSWER KEY: English Grammar")
    assert remainder == "English Grammar"
    # An answer value is never a subhead ("Correct Answer: B) ..."
    # is an answer LINE, not a key heading with a remainder.
    _, remainder = key_heading_remainder("Correct Answer: B) Asif Ali Zardari")
    assert remainder is None
    # A bare answer token in parens is never a subhead.
    _, remainder = key_heading_remainder("Answer Key: (B)")
    assert remainder is None


def test_parse_key_entries_token_stream():
    entries = parse_key_entries("1.C 2.A 3.B 4.D")
    assert entries == {1: "C", 2: "A", 3: "B", 4: "D"}
    entries = parse_key_entries("1. C\n2. A\n3. B")
    assert entries == {1: "C", 2: "A", 3: "B"}
    entries = parse_key_entries("Q1: C Q2: A")
    assert entries == {1: "C", 2: "A"}
    entries = parse_key_entries("13, (B) Broke out")
    assert entries[13] == "(B) Broke out"
    entries = parse_key_entries("61. (C) 3")
    assert entries[61] == "(C) 3"
    # First entry wins when a number repeats.
    entries = parse_key_entries("1. C 1. A")
    assert entries[1] == "C"
    # The lookahead blocks thousands separators and decimals.
    entries = parse_key_entries("The budget is 138,000 rupees. 43.75% growth.")
    assert entries == {}


def test_parse_key_entries_separator_less_guard():
    # Separator-less rows count only as a second pass and only when
    # the blob holds >= 3 of them.
    entries = parse_key_entries("1 B 2 C 3 D")
    assert entries == {1: "B", 2: "C", 3: "D"}
    assert parse_key_entries("1 B 2 C") == {}


def test_normalise_bare_q_entries():
    assert normalise_bare_q_entries("Q1 C") == "Q1: C"
    # "FAQ1 C" is untouched (the Q must not be part of a longer word).
    assert normalise_bare_q_entries("FAQ1 C") == "FAQ1 C"


def test_resolve_answer_token_order():
    # (1) "Option X".
    assert resolve_answer_token("Option C", OPTIONS) == 2
    # (2) paren letter wins; trailing value is a cross-check.
    assert resolve_answer_token("(C) 80", OPTIONS) == 2
    # (3) letter first, text as fallback.
    assert resolve_answer_token("B) Asif Ali Zardari", OPTIONS) == 1
    assert resolve_answer_token("2. Paris", ["Paris", "Rome", "Lima", "Oslo"]) == 1
    # (4) bare number -> index-1 (BEFORE text match: "3" is an index,
    # not option text "3").
    assert resolve_answer_token("3", ["1", "2", "3", "4"]) == 2
    # (5) single letter.
    assert resolve_answer_token("D", OPTIONS) == 3
    # (6) exact case-insensitive text match.
    assert resolve_answer_token("asif ali zardari", OPTIONS) == 1
    # (7) bare misread letter 8/0 -> B/D, only AFTER the text match.
    assert resolve_answer_token("8", OPTIONS) == 1
    assert resolve_answer_token("0", OPTIONS) == 3
    # A real numeric option value "8" still wins over the misread.
    assert resolve_answer_token("8", ["5", "8", "9", "10"]) == 1
    # Out of range: E for a 4-option question resolves to nothing.
    assert resolve_answer_token("E", OPTIONS) is None
    assert resolve_answer_token("Z", OPTIONS) is None


def test_unknown_key_token():
    assert is_unknown_key_token("?")
    assert is_unknown_key_token("??")
    assert is_unknown_key_token("unknown")
    assert not is_unknown_key_token("B")


def test_key_only_line():
    assert is_key_only_line("1. D 58. B 73. A 88. B")
    assert is_key_only_line("57. A")
    assert is_key_only_line("1 B 2 C 3 D")
    assert not is_key_only_line("B. C")  # a bare letter is a list marker
    # A question stem starting with "A" is NOT a key line.
    assert not is_key_only_line("14. A Character That Is Raised And Smaller Above The Baseline")


def test_normalise_paper_title():
    assert normalise_paper_title("Model Paper 66") == "paper 66"
    assert normalise_paper_title("PAPER 66") == "paper 66"
    assert normalise_paper_title("Model Paper 67") != "paper 66"


def test_decide_key_match_ladder():
    base = {"source_document_id": "doc-1"}
    # VERIFIED: number + title agree.
    decision = decide_key_match(
        {**base, "paper_number": "66", "paper_title": "Model Paper 66"},
        {**base, "paper_number": "66", "paper_title": "PAPER 66"},
        key_is_bare=False,
        single_paper_in_document=True,
        exclusive_coverage=True,
        position_evidence=True,
    )
    assert decision["confidence"] == "verified"
    assert decision["may_auto_assign"] is True
    # MISMATCH: different source document.
    decision = decide_key_match(
        {"source_document_id": "doc-2", "paper_number": "66"},
        {**base, "paper_number": "66"},
        key_is_bare=False,
        single_paper_in_document=True,
        exclusive_coverage=True,
        position_evidence=True,
    )
    assert decision["confidence"] == "mismatch"
    # MISMATCH: different paper number.
    decision = decide_key_match(
        {**base, "paper_number": "67"},
        {**base, "paper_number": "66"},
        key_is_bare=False,
        single_paper_in_document=True,
        exclusive_coverage=True,
        position_evidence=True,
    )
    assert decision["confidence"] == "mismatch"
    # HIGH CONFIDENCE: bare key + position + coverage + single paper.
    decision = decide_key_match(
        {**base},
        {**base},
        key_is_bare=True,
        single_paper_in_document=True,
        exclusive_coverage=True,
        position_evidence=True,
    )
    assert decision["confidence"] == "highConfidence"
    assert decision["may_auto_assign"] is False
    # NEEDS REVIEW: bare key in a multi-paper document, non-exclusive.
    decision = decide_key_match(
        {**base},
        {**base},
        key_is_bare=True,
        single_paper_in_document=False,
        exclusive_coverage=False,
        position_evidence=True,
    )
    assert decision["confidence"] == "needsReview"
    # UNVERIFIED: no identity and no evidence.
    decision = decide_key_match(
        {**base},
        {**base},
        key_is_bare=False,
        single_paper_in_document=False,
        exclusive_coverage=False,
        position_evidence=False,
    )
    assert decision["confidence"] == "unverified"


def test_orphan_adoption_conditions():
    assert orphan_adoption_eligible(
        explicit_key_count=1,
        key_paper_has_questions=False,
        all_questions_in_one_default_segment=True,
        question_numbers_unique=True,
        overlap_fraction=0.95,
    )
    # 80% threshold is the floor.
    assert not orphan_adoption_eligible(
        explicit_key_count=1,
        key_paper_has_questions=False,
        all_questions_in_one_default_segment=True,
        question_numbers_unique=True,
        overlap_fraction=0.79,
    )
    # Two explicit keys: refused.
    assert not orphan_adoption_eligible(
        explicit_key_count=2,
        key_paper_has_questions=False,
        all_questions_in_one_default_segment=True,
        question_numbers_unique=True,
        overlap_fraction=0.95,
    )
