# OfficerPath AI — Phase 1, M4 tests: Q&A without options and
# flashcards (spec §10.1-10.2, D9-D10).

from app.pipeline.extract.qa import (
    build_q_only_options,
    count_answers_over_flashcard_caps,
    is_real_q_only_stem,
    scan_flashcards,
)


def _lines(texts, page=1):
    return [
        {
            "index": i,
            "page": page,
            "text": t,
            "paper": "Paper 1",
            "part": "",
            "qa_number": None,
        }
        for i, t in enumerate(texts)
    ]


def test_flashcard_question_mark_split():
    pairs, consumed = scan_flashcards(_lines(["1. Physical Part Of Computer Is Called? Hardware"]))
    assert len(pairs) == 1
    assert pairs[0]["question"] == "Physical Part Of Computer Is Called?"
    assert pairs[0]["answer"] == "Hardware"
    assert pairs[0]["number"] == 1


def test_flashcard_colon_split():
    pairs, _ = scan_flashcards(_lines(["6. Which Key Is Used For Help in PowerPoint: F1"]))
    assert len(pairs) == 1
    assert pairs[0]["question"] == ("Which Key Is Used For Help in PowerPoint:")
    assert pairs[0]["answer"] == "F1"


def test_flashcard_wrapped_answer_two_lines():
    pairs, _ = scan_flashcards(
        _lines(
            [
                "3. In Microsoft Office The Options 'Portrait\" And 'Landscape' Comes Under? Page",
                "Orientation",
            ]
        )
    )
    assert len(pairs) == 1
    assert pairs[0]["answer"] == "Page Orientation"


def test_flashcard_caps_enforced():
    # An answer over the 160-char total cap is not a flashcard.
    pairs, _ = scan_flashcards(_lines(["1. What is the long answer? " + "x" * 170]))
    assert pairs == []
    assert count_answers_over_flashcard_caps([{"answer": "x" * 161}]) == 1
    assert count_answers_over_flashcard_caps([{"answer": "Short"}]) == 0


def test_flashcard_bare_label_never_splits():
    # "Composed By:" is a label, not a question (the ":" split needs
    # a real stem of >= 3 words, the colon itself not counted).
    pairs, _ = scan_flashcards(_lines(["Composed By : Ahmad Rana (ahmad_rana15@yahoo.com)"]))
    assert pairs == []


def test_flashcard_urdu_question_mark():
    pairs, _ = scan_flashcards(_lines(["1. پاکستان کا دارالحکومت کون سا ہے؟ اسلام آباد"]))
    assert len(pairs) == 1
    assert pairs[0]["answer"] == "اسلام آباد"


def test_flashcard_does_not_swallow_next_question():
    pairs, _ = scan_flashcards(
        _lines(
            [
                "1. Physical Part Of Computer Is Called? Hardware",
                "2. File Extension Of MS Word Is? .Docx",
            ]
        )
    )
    assert len(pairs) == 2
    assert pairs[0]["answer"] == "Hardware"
    assert pairs[1]["answer"] == ".Docx"


def test_is_real_q_only_stem():
    assert is_real_q_only_stem("What is the capital of Pakistan?")
    assert not is_real_q_only_stem("Wh to e")
    assert not is_real_q_only_stem("All follo")


def test_build_q_only_options_seeded_and_distinct():
    pool = ["Islamabad", "Karachi", "Lahore", "Quetta", "Peshawar"]
    options = build_q_only_options("Islamabad", pool)
    assert options is not None
    assert len(options) == 4
    assert "Islamabad" in options
    assert len(set(options)) == 4
    # D10: seeded — identical input gives identical output.
    assert build_q_only_options("Islamabad", pool) == options
    # Fewer than 3 usable distinct distractors: excluded, never faked.
    assert build_q_only_options("Islamabad", ["Karachi", "Lahore"]) is None
    assert build_q_only_options("Islamabad", ["Islamabad", "islamabad "]) is None
