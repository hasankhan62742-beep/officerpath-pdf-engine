# OfficerPath AI — Phase 1, M5
# Trailing-key detector tests: noise filtering, paper-identity
# gate, unmatched entries, unknown tokens.

from app.pipeline.answers.key_detector import detect_trailing_key
from app.pipeline.extract.models import ExtractedQuestion


def _question(number: int) -> ExtractedQuestion:
    return ExtractedQuestion(
        number=number,
        text=f"Question {number}?",
        options=["Alpha", "Beta", "Gamma", "Delta"],
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
    )


def _questions(numbers: list[int]) -> list[ExtractedQuestion]:
    return [_question(n) for n in numbers]


def test_key_applies_matching_entries() -> None:
    detection = detect_trailing_key(
        "1. (B) Beta\n2. (D) Delta\n3. (A) Alpha\n",
        questions=_questions([1, 2, 3]),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert detection.decision["confidence"] in ("verified", "highConfidence")
    assert {e.question_number: e.correct_index for e in detection.applied} == {
        1: 1,
        2: 3,
        3: 0,
    }
    assert detection.unmatched == []
    assert detection.filtered == []


def test_noise_numbers_outside_paper_range_are_filtered() -> None:
    # PPSC-66 p7 live parse: 1088/1258/1335/2021 are OCR noise.
    detection = detect_trailing_key(
        "1. (B)\n1088. (A)\n1258. (C)\n1335. (D)\n2021. (A)\n2. (A)\n",
        questions=_questions([1, 2]),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert {e.question_number for e in detection.applied} == {1, 2}
    filtered_numbers = {f["number"] for f in detection.filtered}
    assert filtered_numbers == {1088, 1258, 1335, 2021}
    assert all("outside paper range" in f["reason"] for f in detection.filtered)


def test_entries_outside_range_are_filtered_not_unmatched() -> None:
    # Questions 1–2 only: entries 21/22 are outside the paper's
    # question range, so they are noise-filtered, not "unmatched".
    detection = detect_trailing_key(
        "1. (B)\n21. (C)\n22. (A)\n",
        questions=_questions([1, 2]),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert {e.question_number for e in detection.applied} == {1}
    assert detection.unmatched == []
    filtered_numbers = {f["number"] for f in detection.filtered}
    assert filtered_numbers == {21, 22}
    assert all("outside paper range" in f["reason"] for f in detection.filtered)


def test_in_range_entry_with_no_question_is_unmatched() -> None:
    # Questions 1 and 3 exist (2 was never detected): entry 2 is
    # in range 1..3 but has no question to join — unmatched.
    detection = detect_trailing_key(
        "1. (B)\n2. (C)\n3. (A)\n",
        questions=_questions([1, 3]),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert {e.question_number for e in detection.applied} == {1, 3}
    assert detection.unmatched == [2]


def test_unknown_key_token_is_excluded_never_guessed() -> None:
    detection = detect_trailing_key(
        "1. (B)\n2. ?\n",
        questions=_questions([1, 2]),
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert {e.question_number for e in detection.applied} == {1}
    assert any(f["number"] == 2 and "unknown" in f["reason"] for f in detection.filtered)


def test_paper_identity_mismatch_withholds_the_whole_key() -> None:
    detection = detect_trailing_key(
        "1. (B)\n2. (A)\n",
        questions=_questions([1, 2]),
        paper_identity={"paper_number": "67", "paper_title": "Paper 67"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    # The key's identity (Paper 67) disagrees with the questions'
    # identity (Paper 66) -> mismatch -> nothing applied.
    assert detection.decision["confidence"] == "mismatch"
    assert detection.applied == []
    assert detection.unmatched == [1, 2]


def test_no_questions_means_key_withheld() -> None:
    detection = detect_trailing_key(
        "1. (B)\n2. (A)\n",
        questions=[],
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
    )
    assert detection.applied == []
    assert detection.unmatched == [1, 2]
    assert any("no questions" in n for n in detection.notes)


def test_following_paper_question_text_does_not_join() -> None:
    # Paper 67's questions swallowed into the key section: their
    # values are stems, not answer tokens, so they are rejected at
    # the resolve step (recorded, never applied).
    detection = detect_trailing_key(
        "79. (B) Develop\n80. (C) Take into account\n"
        "1. Who took presidency of G20 from Japan recently:\n"
        "2. The current Pope of Roman Catholic church is:\n",
        questions=[_question(n) for n in [79, 80]],
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=False,
        single_paper_in_document=True,
    )
    assert {e.question_number for e in detection.applied} == {79, 80}
    # The Paper 67 stems parse as entries 1/2 but have no matching
    # question in THIS paper (questions are 79–80), so they are
    # reported unmatched — never joined as answers.
    assert detection.unmatched == [1, 2]


def test_default_paper_label_is_not_a_conflicting_identity() -> None:
    # The extractor stamps "Paper 1" (service.DEFAULT_PAPER_LABEL)
    # when no paper heading was found — that is the absence of
    # identity, not a different paper. A Paper-66 key must not be
    # withheld on a placeholder label (measured on PPSC-66 live:
    # questions carry the default label, key says Paper 66).
    default = ExtractedQuestion(
        number=1,
        text="Question 1?",
        options=["Alpha", "Beta", "Gamma", "Delta"],
        paper_identity={
            "source_document_id": "doc-1",
            "paper_number": "1",
            "paper_title": "Paper 1",
            "exam": None,
            "year": None,
        },
    )
    detection = detect_trailing_key(
        "1. (B) Beta\n2. (D) Delta\n",
        questions=[default, _question(2)],
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=True,
        single_paper_in_document=True,
    )
    assert detection.decision["confidence"] in ("verified", "highConfidence")
    assert {e.question_number for e in detection.applied} == {1, 2}


def test_real_different_paper_label_still_mismatches() -> None:
    # The default-label fix must not open the gate: a REAL
    # different paper label still withholds the whole key.
    other = ExtractedQuestion(
        number=1,
        text="Question 1?",
        options=["Alpha", "Beta", "Gamma", "Delta"],
        paper_identity={
            "source_document_id": "doc-1",
            "paper_number": "67",
            "paper_title": "Paper 67",
            "exam": None,
            "year": None,
        },
    )
    detection = detect_trailing_key(
        "1. (B) Beta\n2. (D) Delta\n",
        questions=[other, _question(2)],
        paper_identity={"paper_number": "66", "paper_title": "Paper 66"},
        source_document_id="doc-1",
        key_is_bare=True,
        single_paper_in_document=True,
    )
    assert detection.decision["confidence"] == "mismatch"
    assert detection.applied == []
