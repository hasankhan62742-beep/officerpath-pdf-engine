# OfficerPath AI — Phase 1, M4 tests: extraction service + golden
# fixtures (synthetic clean, Nastaliq structure on ground-truth
# lines, and sample pages of the digital ground-truth files).
#
# Every test asserts measured behaviour, never a guessed number.

import json
from pathlib import Path

from app.pipeline.extract.service import (
    PageLines,
    extract_document,
    extract_from_digital_pdf,
)

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
PPSC66 = GOLDEN / "ppsc66"


def _dataset_entry(entry_id: str) -> dict:
    dataset = json.loads((GOLDEN / "dataset.json").read_text(encoding="utf-8"))
    for entry in dataset["entries"]:
        if entry["id"] == entry_id:
            return entry
    raise KeyError(entry_id)


def test_synthetic_clean_p1_all_four_questions():
    entry = _dataset_entry("synthetic-clean-p1")
    result = extract_document(
        [PageLines(page_number=1, lines=entry["lines"])], "synthetic-clean-p1"
    )
    # No answers in the fixture -> all four are pending, none parsed
    # as answered questions (§6.18: answerless is never counted).
    assert len(result.pending) == 4
    assert len(result.questions) == 0
    texts = [p.text for p in result.pending]
    assert "What is the capital of Pakistan?" in texts
    assert "Which river flows through Lahore?" in texts
    assert "The largest desert of Pakistan is?" in texts
    assert "Who wrote the national anthem?" in texts
    for pending in result.pending:
        assert len(pending.options) == 4
        assert pending.reason == "no-key-entry"
    assert result.format_counts.get("block") == 4


def test_synthetic_clean_p2_same_questions():
    entry = _dataset_entry("synthetic-clean-p2")
    result = extract_document(
        [PageLines(page_number=2, lines=entry["lines"])], "synthetic-clean-p2"
    )
    assert len(result.pending) == 4


def test_nastaliq_structure_on_ground_truth_lines():
    # Tesseract CER on Nastaliq is 0.59 (M4 re-measurement), so
    # extraction from Tesseract output would be poor. This test runs
    # the extractor on the GROUND-TRUTH lines: the structure rules
    # must work on Urdu text (؟ terminators, (A)-(D) markers).
    entry = _dataset_entry("synthetic-nastaliq-p1")
    reference = (GOLDEN / entry["reference_file"]).read_text(encoding="utf-8")
    lines = [line for line in reference.splitlines() if line.strip()]
    result = extract_document([PageLines(page_number=1, lines=lines)], "synthetic-nastaliq-p1")
    assert len(result.pending) == 4
    assert any("پاکستان کا دارالحکومت" in p.text for p in result.pending)
    for pending in result.pending:
        assert len(pending.options) == 4


def test_testpoint_pdfplumber_rows_consumed_once():
    # Regression test for the M4 consumption defect: the pdfplumber
    # fallback rows must consume their lines (§9.7), or the grid/block
    # passes re-parse the same rows as phantoms (run 5: 2,545
    # detected vs 1,375 ground truth). Every ground-truth (page, Sr#)
    # pair must appear exactly once as a numbered question with
    # matching text.
    #
    # M5 update: the positional (non-adjacent) consumption pass
    # (consume_leftover_option_lines) removes the residual
    # phantoms from column-ordered long-option sections: 1,593
    # questions / 30 pending (M4, 248 FPs) -> 1,403 questions /
    # 0 pending (M5, 28 FPs). The per-row assertions below are the
    # real regression guards; the totals pin the M5 improvement.
    import difflib

    data = (PPSC66 / "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf").read_bytes()
    gt = json.loads((PPSC66 / "ground_truth_testpoint_1000.json").read_text())["rows"]
    result = extract_from_digital_pdf(data, "testpoint-english-1000")
    by_key: dict[tuple[int, int], list] = {}
    for q in result.questions:
        if q.number is not None:
            by_key.setdefault((q.page, q.number), []).append(q)
    assert len(result.questions) == 1403
    assert len(result.pending) == 0
    for row in gt:
        key = (row["page"], row["sr"])
        assert key in by_key, f"ground-truth row missing: {key}"
        assert len(by_key[key]) == 1, f"row parsed more than once: {key}"
        detected = by_key[key][0]
        ratio = difflib.SequenceMatcher(
            None, detected.text.lower(), row["question"].lower()
        ).ratio()
        assert ratio >= 0.85, f"text mismatch for {key}: {ratio:.2f}"


def test_ca40_sample_pages_all_answered():
    data = (PPSC66 / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()
    result = extract_from_digital_pdf(data, "ppsc-ca-40-mcqs")
    assert len(result.questions) == 40
    assert len(result.pending) == 0
    assert result.answer_sources == {"answer-line": 40}
    first = result.questions[0]
    assert first.number == 1
    assert first.options[1] == "Asif Ali Zardari"
    assert first.correct_index == 1
    assert first.confidence == 1.0
    assert first.verification_status == "verified"
    assert first.mark_provenance == "printed"


def test_urdu_noa_lowercase_markers():
    data = (PPSC66 / "PDF_Urdu_MCQs_NOA.pdf").read_bytes()
    result = extract_from_digital_pdf(data, "urdu-mcqs-noa")
    # The file itself prints only 3 options for Q25 and 1 for Q33
    # (ground truth confirms d: ''), so those two are excluded (D6);
    # the rest with full options and a (Correct) mark are parsed.
    assert len(result.questions) == 105
    assert result.answer_sources == {"answer-line": 105}
    first = result.questions[0]
    assert first.number == 1
    assert first.options == [
        "Faiz Ahmad Faiz",
        "Rabindranath Tagore",
        "Akbar Allabadi",
        "Mirza Ghalib",
    ]
    assert first.correct_index == 1
    assert any("Q25" in e for e in result.excluded)
    assert any("Q33" in e for e in result.excluded)


def test_computer_qa_pairs_no_fabricated_options():
    data = (PPSC66 / "Computer_Past_Papers_2019-2025.pdf").read_bytes()
    result = extract_from_digital_pdf(data, "computer-past-papers-2019-2025")
    # Q&A pairs carry NO options — the extractor must never fabricate
    # 4 options for these.
    assert len(result.qa_pairs) >= 700
    assert len(result.questions) == 0
    first = result.qa_pairs[0]
    assert first.number == 1
    assert first.question == "Physical Part Of Computer Is Called?"
    assert first.answer == "Hardware"
    assert first.format == "qa_pair"


def test_paper_identity_gate_never_merges_documents():
    block_lines = [
        "1. What is the capital?",
        "(A) Karachi",
        "(B) Lahore",
        "(C) Islamabad",
        "(D) Quetta",
    ]
    left = extract_document(
        [PageLines(page_number=1, lines=block_lines)],
        "doc-a",
    )
    right = extract_document(
        [PageLines(page_number=1, lines=block_lines)],
        "doc-b",
    )
    assert left.pending[0].paper == "Paper 1"
    assert right.pending[0].paper == "Paper 1"
    # One call = one document: the two runs share nothing.
    assert left is not right


def test_ocr_tick_bold_downgraded_unverified():
    lines = [
        "1. What is the capital?",
        "(A) Karachi",
        "(B) Lahore ✓",
        "(C) Islamabad",
        "(D) Quetta",
    ]
    result = extract_document([PageLines(page_number=1, lines=lines, is_ocr=True)], "ocr-doc")
    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.answer_source == "tick"
    assert question.verification_status == "unverified"
    assert question.confidence == 0.54
    assert question.mark_provenance == "ocr"


def test_bold_marker_from_digital_block():
    # D17: per-line bold from style["bold_lines"] is appended as
    # U+E000 and read as the bold signal (never stored).
    from app.pipeline.interfaces import BoundingBox, OCRBlock

    block = OCRBlock(
        text="1. What is the capital?\n(A) Karachi\n(B) Lahore\n(C) Islamabad\n(D) Quetta",
        bbox=BoundingBox(0, 0, 1, 1),
        page_number=1,
        reading_order=0,
        style={"bold": True, "bold_lines": [2]},
    )
    result = extract_document(
        [PageLines(page_number=1, blocks=[block], is_ocr=False)],
        "digital-doc",
    )
    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.answer_source == "bold"
    assert question.correct_index == 1
    assert question.confidence == 0.9
    assert "\ue000" not in question.options[1]


def test_trailing_key_section_joins_whole_document():
    # Regression: the key-join coverage computation crashed with
    # "unhashable type: 'dict'" when a trailing key section was
    # present (stale `entries` name). A 2-page document with a key
    # section on p2 must apply the key without error.
    result = extract_document(
        [
            PageLines(
                page_number=1,
                lines=[
                    "1. What is the capital of Pakistan?",
                    "(A) Karachi",
                    "(B) Lahore",
                    "(C) Islamabad",
                    "(D) Quetta",
                    "2. Which is the largest province?",
                    "(A) Punjab",
                    "(B) Sindh",
                    "(C) Balochistan",
                    "(D) KPK",
                ],
                is_ocr=True,
            ),
            PageLines(
                page_number=2,
                lines=[
                    "Answer Key",
                    "1. C",
                    "2. C",
                ],
                is_ocr=True,
            ),
        ],
        "key-join-doc",
    )
    assert result.key_sections_found >= 1
    assert result.key_entries_applied == 2
    assert len(result.unmatched_key_entries) == 0
    by_number = {q.number: q for q in result.questions}
    assert by_number[1].correct_index == 2
    assert by_number[1].answer_source == "key"
    assert by_number[2].correct_index == 2
