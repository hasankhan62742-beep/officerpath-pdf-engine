# OfficerPath AI — Phase 1, M4 tests: candidate scoring (M4 addition
# over Dart) and validation (spec §4.5-4.6, §8.2, D12).

from app.pipeline.extract.models import ExtractedQuestion, ParseResult
from app.pipeline.extract.scoring import score_candidate
from app.pipeline.extract.validate import looks_fabricated, validate_parse_result


def test_score_candidate_clean_full_marks():
    confidence, signals = score_candidate(
        number_kind="clean",
        n_options=4,
        marker_styles=["(A)", "(A)", "(A)", "(A)"],
        position_continuous=True,
        column_consistent=True,
    )
    assert confidence == 1.0
    assert signals["number_pattern"] == 1.0
    assert signals["option_completeness"] == 1.0


def test_score_candidate_numberless_partial():
    confidence, signals = score_candidate(
        number_kind="numberless",
        n_options=4,
        marker_styles=["(A)", "(A)", "(A)", "(A)"],
        position_continuous=True,
        column_consistent=True,
    )
    # 0.35*0.3 + 0.30 + 0.15 + 0.10 + 0.10 = 0.755
    assert confidence == 0.755
    assert signals["number_pattern"] == 0.3


def test_score_candidate_mixed_markers_and_missing_option():
    confidence, signals = score_candidate(
        number_kind="decoded",
        n_options=3,
        marker_styles=["(A)", "A.", "(A)", "(A)"],
        position_continuous=False,
        column_consistent=False,
    )
    assert signals["marker_consistency"] == 0.5
    assert signals["option_completeness"] == 0.75
    assert 0.0 <= confidence <= 1.0


def _result_with_questions():
    result = ParseResult()
    result.questions.append(
        ExtractedQuestion(
            number=1,
            text="What is the capital?",
            options=["Karachi", "Lahore", "Islamabad", "Quetta"],
            correct_index=2,
            answer_source="key",
            confidence=1.0,
            verified=True,
            verification_status="verified",
            page=1,
        )
    )
    return result


def test_validate_clean_result_has_no_issues():
    assert validate_parse_result(_result_with_questions()) == []


def test_validate_missing_answer_is_info():
    result = _result_with_questions()
    result.questions[0].correct_index = -1
    issues = validate_parse_result(result)
    assert any(i["kind"] == "missingAnswer" and i["severity"] == "info" for i in issues)


def test_validate_duplicate_text_and_number_are_errors():
    result = _result_with_questions()
    twin = ExtractedQuestion(
        number=1,
        text="What is the capital?",
        options=["Karachi", "Lahore", "Islamabad", "Quetta"],
        correct_index=2,
        answer_source="key",
        page=2,
    )
    result.questions.append(twin)
    issues = validate_parse_result(result)
    assert any(i["kind"] == "duplicateQuestion" and i["severity"] == "error" for i in issues)
    assert any(i["kind"] == "duplicateNumber" and i["severity"] == "error" for i in issues)


def test_validate_unmatched_key_entry_is_warning():
    result = _result_with_questions()
    result.unmatched_key_entries.append("Paper 2 key entry 61 — no matching question")
    issues = validate_parse_result(result)
    assert any(i["kind"] == "unmatchedKeyEntry" and i["severity"] == "warning" for i in issues)


def test_looks_fabricated():
    # Only for flashcard/q-only sources.
    assert looks_fabricated("(A) Karachi", "block") is None
    assert looks_fabricated("(A) Karachi", "flashcard") is not None
    assert looks_fabricated("- Karachi", "flashcard") is not None
    # Instruction verbs are exempt from the bare-label check.
    assert looks_fabricated("Name the capital:", "flashcard") is None
    assert looks_fabricated("The capital city:", "flashcard") is not None
    # A real question is not fabricated.
    assert looks_fabricated("What is the capital of Pakistan?", "flashcard") is None
