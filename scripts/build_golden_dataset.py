"""Build the golden dataset v2 (M4): versioned ground-truth +
reference annotations for the benchmark harness.

Run from the repo root:  .venv/bin/python scripts/build_golden_dataset.py

PREREQUISITE: run scripts/extract_golden_v2_ground_truth.py first — the
v2 ground-truth / extraction JSONs it writes are read here for the
per-entry counts in the notes. (The v1 synthetic + PPSC-66 entries need
no extraction.)

Outputs (all under app/tests/fixtures/golden/):
- dataset.json: the manifest — version, sources, per-page entries.
  synthetic pages carry EXACT ground truth (the text the M2 fixture
  generator drew — see scripts/generate_m2_fixtures.py QUESTIONS);
  PPSC-66 pages carry the Gemini OCR text as REFERENCE (labelled as
  such — it is Gemini output, not hand-verified ground truth),
  except p-1, which was hand-verified against the page image in M3.
  v2 entries carry EXTRACTED ground truth (programmatically read from
  each file's own text layer — inline answer marking — NOT hand-verified)
  or NO reference where the file marks no answers.
- ppsc66/*.txt: copies of the Gemini reference texts from the
  Flutter repo (read-only source; never modified there) + PROVENANCE.

Ground truth vs reference, stated plainly: CER/WER on synthetic
pages measure against exact ground truth. CER/WER on PPSC-66 pages
measure against the Gemini reference — i.e. "how close is this
engine to Gemini's reading", not "how close to the printed page".
The hand-verified p-1 sample bounds the reference's own error (see
dataset.json: 1 word error found in ~700 words on p-1). Extracted
ground truth (v2) is only as good as the file's own inline marking —
each JSON records its gaps, duplicates and unparseable rows.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "tests" / "fixtures" / "golden"
FLUTTER_FIXTURES = Path("/home/hatch/workspace/officerpath-ai/test-fixtures/ppsc66")
M2_FIXTURES = ROOT / "app" / "tests" / "fixtures" / "m2"

# Exact text as PyMuPDF reads it from scripts/generate_m2_fixtures.py
# (QUESTIONS). The digital extractor must reproduce this (CER ~ 0) —
# the benchmark cross-checks the ground truth itself this way.
# NOTE: the generator writes the title with an em dash ("—"), but
# Helvetica's WinAnsi mapping extracts as a middle dot ("·") — the
# ground truth records the extracted form, VERIFIED with fitz.
SYNTHETIC_LINES = [
    "Model Paper · General Knowledge (fixture)",
    "1. What is the capital of Pakistan?",
    "(A) Karachi",
    "(B) Lahore",
    "(C) Islamabad",
    "(D) Quetta",
    "2. Which river flows through Lahore?",
    "(A) Indus",
    "(B) Ravi",
    "(C) Chenab",
    "(D) Jhelum",
    "3. The largest desert of Pakistan is?",
    "(A) Thar",
    "(B) Cholistan",
    "(C) Kharan",
    "(D) Naran",
    "4. Who wrote the national anthem?",
    "(A) Iqbal",
    "(B) Hafeez Jalandhari",
    "(C) Faiz",
    "(D) Ghalib",
]
# clean.pdf page 2 is two-column: Q1-Q2 left, Q3-Q4 right.
SYNTHETIC_LEFT_P2 = SYNTHETIC_LINES[1:11]
SYNTHETIC_RIGHT_P2 = SYNTHETIC_LINES[11:]


def _entry(
    entry_id: str,
    kind: str,
    source: str,
    page: int,
    *,
    reference_kind: str,
    reference_file: str | None,
    lines: list[str] | None,
    left_lines: list[str] | None = None,
    right_lines: list[str] | None = None,
    categories: list[str] | None = None,
    hand_verified: bool = False,
    notes: str = "",
) -> dict:
    return {
        "id": entry_id,
        "kind": kind,
        "source": source,
        "page": page,
        "reference_kind": reference_kind,
        "reference_file": reference_file,
        "lines": lines,
        "left_column_lines": left_lines,
        "right_column_lines": right_lines,
        "categories": categories or [],
        "hand_verified": hand_verified,
        "notes": notes,
    }


def _gt(out_ppsc: Path, name: str) -> dict:
    """Read one extraction JSON (written by extract_golden_v2_ground_truth.py)."""
    return json.loads((out_ppsc / name).read_text(encoding="utf-8"))


def main() -> None:
    out_ppsc = OUT / "ppsc66"
    out_ppsc.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in sorted(FLUTTER_FIXTURES.glob("ocr-*.txt")) + [
        FLUTTER_FIXTURES / "paper60_gemini_ocr.txt",
    ]:
        if not name.exists():
            continue
        shutil.copy2(name, out_ppsc / name.name)
        copied.append(name.name)
    # v2 fixtures: copies of the new files sent 2026-11-21 (md5-verified at
    # copy time; see the M4 report). Only copy when the source exists.
    v2_files = [
        "table-interjection-q230-257-resent-20261121.jpg",
        "table-computer-q67-81-resent-20261121.jpg",
        "ppsc-current-affairs-40-mcqs.pdf",
        "Current-Affairs-March-2025-in-PDF.pdf",
        "Current-Affairs-April-2025-in-PDF-Free-Version.pdf",
        "Current-Affairs-June-2025-in-PDF__1.pdf",
        "Current-Affairs-July-2025-in-PDF.pdf",
        "Pakistan-Current-Affairs-August-2025-in-PDF.pdf",
        "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        "Computer_Past_Papers_2019-2025.pdf",
        "PDF_Urdu_MCQs_NOA.pdf",
        "Pak_Study_1000__MCQs_for_ETEA.pdf",
        "Science_test_NOA.pdf",
        "Math_test_NOA.pdf",
        "Past_Paper_Assistant__S_GAD.pdf",
        "Capsule_of_GK.pdf",
        "3000B.c_to_2023_History_Notes_by_gkwithadnan.pdf",
        "Pak_Affairs_by_CSPs.pdf",
    ]
    for name in v2_files:
        src = FLUTTER_FIXTURES / name
        if src.exists():
            shutil.copy2(src, out_ppsc / name)
            copied.append(name)
    (OUT / "ppsc66" / "PROVENANCE.md").write_text(
        "# Golden dataset v1 — PPSC-66 reference texts (copies)\n\n"
        "Copied (not moved) from the Flutter repo's golden fixtures:\n"
        "`~/workspace/officerpath-ai/test-fixtures/ppsc66/`\n\n"
        "These are GEMINI OCR OUTPUT (model gemini-3.5-flash-lite, the\n"
        "app's own prompt), not hand-verified ground truth — except\n"
        "p-1, which was hand-verified against the page image in M3\n"
        "(see dataset.json). The Flutter repo is the source of truth\n"
        "and is NEVER modified by the engine.\n\n"
        "Files copied:\n\n"
        + "".join(f"- `{name}`\n" for name in copied)
        + "\n## Golden dataset v2 (M4, 2026-11-21) — added fixtures\n\n"
        "The 18 v2 files above (re-sent table photos, monthly Current\n"
        "Affairs PDFs, TestPoint 1000, Computer past papers, Urdu NOA,\n"
        "Pak Study 1000, scanned NOA tests, Capsule of GK, History notes,\n"
        "Pak Affairs notes) were copied md5-verified from the same source\n"
        "folder. Ground truth for the digital ones was extracted\n"
        "programmatically — see scripts/extract_golden_v2_ground_truth.py\n"
        "and the ppsc66/ground_truth_*.json / extracted_*.json files.\n",
        encoding="utf-8",
    )

    entries: list[dict] = []
    # --- Synthetic fixtures: exact ground truth. ---
    for file_name, pages in [
        ("clean.pdf", [1, 2]),
        ("scanned.pdf", [1]),
        ("mixed.pdf", [1, 2]),
        ("skewed.pdf", [1]),
        ("low_contrast.pdf", [1]),
        ("noisy.pdf", [1]),
    ]:
        for page in pages:
            if file_name == "clean.pdf" and page == 2:
                entries.append(
                    _entry(
                        "synthetic-clean-p2",
                        "digital",
                        "m2/clean.pdf",
                        2,
                        reference_kind="ground_truth",
                        reference_file=None,
                        lines=SYNTHETIC_LINES,
                        left_lines=SYNTHETIC_LEFT_P2,
                        right_lines=SYNTHETIC_RIGHT_P2,
                        categories=["digital", "two-column", "english", "marks"],
                        notes="Page 2 is two-column: Q1-Q2 left, Q3-Q4 right.",
                    )
                )
                continue
            digital_files = ("clean.pdf", "mixed.pdf", "low_contrast.pdf")
            is_digital_page = file_name in digital_files and not (
                file_name == "mixed.pdf" and page == 2
            )
            kind = "digital" if is_digital_page else "scanned"
            entries.append(
                _entry(
                    f"synthetic-{file_name[:-4]}-p{page}",
                    kind,
                    f"m2/{file_name}",
                    page,
                    reference_kind="ground_truth",
                    reference_file=None,
                    lines=SYNTHETIC_LINES,
                    categories=["synthetic", kind, "english", "marks"],
                    notes="Same 4 MCQs as clean p1 (image variants share its text).",
                )
            )
    entries.append(
        _entry(
            "synthetic-blank-p1",
            "blank",
            "m2/blank.pdf",
            1,
            reference_kind="ground_truth",
            reference_file=None,
            lines=[],
            categories=["synthetic", "blank"],
            notes="Empty page: every engine must return no blocks.",
        )
    )
    # --- Nastaliq fixture (M4): exact ground truth, rendered with
    # Noto Nastaliq Urdu (scripts/render_nastaliq_fixture.py). The
    # same 4 MCQs as the synthetic English fixture, translated. ---
    nastaliq_lines = (
        (OUT / "synthetic-nastaliq" / "nastaliq-p1.txt").read_text(encoding="utf-8").splitlines()
    )
    entries.append(
        _entry(
            "synthetic-nastaliq-p1",
            "scanned",
            "synthetic-nastaliq/nastaliq-p1.png",
            1,
            reference_kind="ground_truth",
            reference_file="synthetic-nastaliq/nastaliq-p1.txt",
            lines=nastaliq_lines,
            categories=["synthetic", "scanned", "urdu", "nastaliq"],
            notes=(
                "4 Urdu MCQs in Nastaliq (Noto Nastaliq Urdu, rendered "
                "with PIL raqm/harfbuzz shaping). Tesseract Nastaliq "
                "CER measured in M4 — see "
                "docs/benchmarks/BENCHMARK_M4_2026-11-21.md."
            ),
        )
    )
    # --- PPSC-66 real pages: Gemini reference (p-1 hand-verified). ---
    for page in range(1, 8):
        entries.append(
            _entry(
                f"ppsc66-p{page}",
                "scanned",
                f"ppsc66/p-{page}.png",
                page,
                reference_kind="gemini_reference"
                if page != 1
                else "gemini_reference_hand_verified",
                reference_file=f"ppsc66/ocr-p{page}.txt",
                lines=None,
                categories=["scanned", "two-column", "english", "real", "camscanner"],
                hand_verified=(page == 1),
                notes=(
                    "Hand-verified against the page image in M3: 1 word error "
                    "found in ~700 words — '(C) Ala' should be '(C) A/a'. "
                    "Q1-Q9 numbers are cut off at the scan's left edge and "
                    "are absent from the reference (not a Gemini error)."
                    if page == 1
                    else "Gemini reference text; NOT hand-verified ground truth."
                ),
            )
        )
    for name, ref_file, label in [
        (
            "table-computer-q67-81",
            "ocr-table-computer-gemini.txt",
            "table photo: computer Q67-81",
        ),
        (
            "table-interjection-q230-257",
            "ocr-table-interjection-gemini.txt",
            "table photo: interjection Q230-257",
        ),
    ]:
        entries.append(
            _entry(
                f"ppsc66-{name}",
                "scanned",
                f"ppsc66/{name}.jpg",
                1,
                reference_kind="gemini_reference",
                reference_file=f"ppsc66/{ref_file}",
                lines=None,
                categories=["scanned", "table-photo", "english", "real"],
                notes=f"{label}; Gemini reference text, not hand-verified.",
            )
        )
    # Paper 60 (M4 FIX): the photo was never missing — it was in the
    # media library all along (IMG_20261119_151817_041.jpg, 19 Nov 2026),
    # recovered 2026-11-21, NOT re-sent by the owner. The M3 entry saying
    # "no image and no Gemini reference text exist" was wrong on both
    # counts: the Gemini reference text existed in the Flutter repo's
    # test/fixtures/. Viewed in M4: "PAPER 60 — DATA ENTRY OPERATOR
    # (Police)", two-column, Q1–Q21 visible, answers star-marked
    # (Q1 (C) F5*, Q2 (B) HTML*), handwritten "Dot Matrix printer /
    # impact printer" note.
    entries.append(
        _entry(
            "paper60-photo",
            "scanned",
            "ppsc66/paper60-photo.jpg",
            1,
            reference_kind="gemini_reference",
            reference_file="ppsc66/paper60_gemini_ocr.txt",
            lines=None,
            categories=["scanned", "photo", "english", "real"],
            notes=(
                "Paper 60 phone photo; recovered from the media library "
                "(IMG_20261119_151817_041.jpg, 19 Nov 2026), NOT re-sent "
                "by the owner — the M3 'missing' claim was wrong. Gemini "
                "reference text, not hand-verified."
            ),
        )
    )
    # --- v2 entries (M4): counts read from the extraction JSONs. ---
    ca40 = _gt(out_ppsc, "ground_truth_ca40.json")
    tp = _gt(out_ppsc, "ground_truth_testpoint_1000.json")
    comp = _gt(out_ppsc, "ground_truth_computer_qa.json")
    urdu = _gt(out_ppsc, "ground_truth_urdu_noa.json")
    pak = _gt(out_ppsc, "extracted_pak_study_1000_ranges.json")
    monthly = {
        label: _gt(out_ppsc, fname)
        for label, fname in [
            ("march", "extracted_ca_monthly_march_2025.json"),
            ("april", "extracted_ca_monthly_april_2025.json"),
            ("june", "extracted_ca_monthly_june_2025.json"),
            ("july", "extracted_ca_monthly_july_2025.json"),
            ("august", "extracted_ca_monthly_pakistan_august_2025.json"),
        ]
    }

    def _monthly_entry(entry_id, pdf_file, pages, label, extract_file, extra_note=""):
        m = monthly[label]
        hist = m["explanation_option_match_histogram"]
        return _entry(
            entry_id,
            "digital",
            f"ppsc66/{pdf_file}",
            None,
            reference_kind="none",
            reference_file=None,
            lines=None,
            categories=["digital", "english", "real", "current-affairs", "answers-unknown"],
            notes=(
                f"mcqsplanet.com, {pages}pp, {m['count']} MCQs (1 per content page: "
                "question + A–D + explanation). Answers UNKNOWN: no option span "
                f"is bold or coloured and no 'Correct Answer' line exists "
                f"(verified over {m['option_spans_checked']} option spans); the "
                "explanation is prose that may or may not contain the answer "
                f"text (explanation matched exactly one option in {hist['1']}/"
                f"{m['count']} questions, none in {hist['0']}, more than one "
                f"in {hist['>1']}) — NOT a reliable mechanism, so no answer "
                f"is recorded. Questions only: ppsc66/{extract_file}." + extra_note
            ),
        )

    entries.extend(
        [
            _monthly_entry(
                "ca-monthly-march-2025",
                "Current-Affairs-March-2025-in-PDF.pdf",
                32,
                "march",
                "extracted_ca_monthly_march_2025.json",
            ),
            _monthly_entry(
                "ca-monthly-april-2025",
                "Current-Affairs-April-2025-in-PDF-Free-Version.pdf",
                34,
                "april",
                "extracted_ca_monthly_april_2025.json",
            ),
            _monthly_entry(
                "ca-monthly-june-2025",
                "Current-Affairs-June-2025-in-PDF__1.pdf",
                37,
                "june",
                "extracted_ca_monthly_june_2025.json",
                extra_note=" One sampled explanation states a figure "
                "(8 dead) matching no option (options 5/9/12/15) — "
                "the explanation cannot be trusted as the answer key.",
            ),
            _monthly_entry(
                "ca-monthly-july-2025",
                "Current-Affairs-July-2025-in-PDF.pdf",
                32,
                "july",
                "extracted_ca_monthly_july_2025.json",
            ),
            _monthly_entry(
                "ca-monthly-pakistan-august-2025",
                "Pakistan-Current-Affairs-August-2025-in-PDF.pdf",
                22,
                "august",
                "extracted_ca_monthly_pakistan_august_2025.json",
            ),
        ]
    )

    entries.extend(
        [
            _entry(
                "ppsc66-table-interjection-q230-257-resent",
                "scanned",
                "ppsc66/table-interjection-q230-257-resent-20261121.jpg",
                1,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "table-photo", "english", "real", "resent-2026-11-21"],
                notes=(
                    "Re-capture (2026-11-21) of the same Q230–257 Interjection / "
                    "Parts of Speech / Gerund table page as "
                    "ppsc66-table-interjection-q230-257; different md5 "
                    "(0309372a…), kept as a separate version. No Gemini "
                    "reference for this capture; OCR-only."
                ),
            ),
            _entry(
                "ppsc66-table-computer-q67-81-resent",
                "scanned",
                "ppsc66/table-computer-q67-81-resent-20261121.jpg",
                1,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "table-photo", "english", "real", "resent-2026-11-21"],
                notes=(
                    "Re-capture (2026-11-21) of the same Q67–81 MS Word table "
                    "page ('Page 5 of 71') as ppsc66-table-computer-q67-81; "
                    "different md5 (927ccc5e…), kept as a separate version. No "
                    "Gemini reference for this capture; OCR-only."
                ),
            ),
            _entry(
                "ppsc-ca-40-mcqs",
                "digital",
                "ppsc66/ppsc-current-affairs-40-mcqs.pdf",
                None,
                reference_kind="extracted_ground_truth",
                reference_file="ppsc66/ground_truth_ca40.json",
                lines=None,
                categories=["digital", "english", "real", "current-affairs", "inline-answers"],
                notes=(
                    f"6-page digital CA paper, {ca40['count']} MCQs; answers from "
                    "the bold 'Correct Answer: X) ...' line after each "
                    "question's four options (extracted ground truth, not "
                    "hand-verified). No separate key."
                ),
            ),
            _entry(
                "testpoint-english-1000",
                "digital",
                "ppsc66/English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
                None,
                reference_kind="extracted_ground_truth",
                reference_file="ppsc66/ground_truth_testpoint_1000.json",
                lines=None,
                categories=["digital", "table", "english", "real", "inline-answers"],
                notes=(
                    f"Table-format MCQs (Sr# | Question | A–D | Ans); "
                    f"{tp['count']} rows extracted — the '1000' in the filename "
                    "is NOT the row count, and Sr# restarts per topic section "
                    f"({tp['pages_where_numbering_restarts']} restarts; Sr# "
                    f"{tp['sr_min']}..{tp['sr_max']}, "
                    f"{tp['sr_values_occurring_more_than_once']} values occur "
                    "more than once), so rows are keyed by (page, sr), not Sr# "
                    "alone. Extracted ground truth, not hand-verified."
                ),
            ),
            _entry(
                "computer-past-papers-2019-2025",
                "digital",
                "ppsc66/Computer_Past_Papers_2019-2025.pdf",
                None,
                reference_kind="extracted_ground_truth",
                reference_file="ppsc66/ground_truth_computer_qa.json",
                lines=None,
                categories=["digital", "english", "real", "qa-no-options", "inline-answers"],
                notes=(
                    f"Q&A pairs with NO options (new document type — the "
                    "extractor must NOT force 4 options); answer = text after "
                    f"'?' (':' / ';' / final '.' fallbacks); {comp['count']} "
                    f"pairs, Q{comp['number_min']}–{comp['number_max']}; numbers "
                    f"{comp['gaps']} absent from the text layer; "
                    f"{comp['duplicates']} each carry two different questions "
                    "in the source; "
                    f"{len(comp['pairs_with_empty_answer'])} pairs "
                    f"({comp['pairs_with_empty_answer']}) have no separable "
                    "answer in the text layer. Extracted ground truth, not "
                    "hand-verified."
                ),
            ),
            _entry(
                "urdu-mcqs-noa",
                "digital",
                "ppsc66/PDF_Urdu_MCQs_NOA.pdf",
                None,
                reference_kind="extracted_ground_truth",
                reference_file="ppsc66/ground_truth_urdu_noa.json",
                lines=None,
                categories=[
                    "digital",
                    "english",
                    "urdu-topic",
                    "real",
                    "lowercase-markers",
                    "inline-answers",
                ],
                notes=(
                    f"NOA 'History and Personalities'; questions in English, "
                    f"options lowercase a.–d.; answers marked '(Correct)' in "
                    f"the text layer: {urdu['with_answer']}/{urdu['count']} "
                    f"with an answer, without: {urdu['without_answer']}, "
                    f"double-marked: {urdu['multiple_marked']}, missing an "
                    f"option letter: {urdu['missing_option_letters']} — the "
                    "text layer is jumbled (blocks out of reading order, some "
                    "'d.' markers missing). First Urdu-topic MCQ file in the "
                    "set. Extracted ground truth, not hand-verified."
                ),
            ),
            _entry(
                "pak-study-1000-etea",
                "digital",
                "ppsc66/Pak_Study_1000__MCQs_for_ETEA.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["digital", "english", "real", "scale-test"],
                notes=(
                    f"Pak Study MCQs, header 'Part 1 of 5' (file actually spans "
                    f"Parts 1–5); {pak['total_questions_found']} questions, "
                    f"Q{pak['number_min']}–{pak['number_max']}, no gaps; NO "
                    "answer marking in the text layer (0 occurrences of "
                    "'(Correct)' / 'Correct Answer' / 'Ans:' / 'Answer:'); "
                    f"{len(pak['zero_char_pages'])} zero-char pages "
                    f"({pak['zero_char_pages']}); pp. 273–280 are back matter "
                    "(ads/contents), no questions. Question numbers per page: "
                    "ppsc66/extracted_pak_study_1000_ranges.json."
                ),
            ),
            _entry(
                "science-test-noa",
                "scanned",
                "ppsc66/Science_test_NOA.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "english", "real", "camscanner"],
                notes=(
                    "CamScanner scan, 13pp (312 chars of watermark text only), "
                    "OCR-only; same class as PPSC-66."
                ),
            ),
            _entry(
                "math-test-noa",
                "scanned",
                "ppsc66/Math_test_NOA.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "english", "real", "camscanner", "math"],
                notes=(
                    "CamScanner scan, 13pp (watermark text only), OCR-only; "
                    "math formulas/symbols are the hardest OCR case in the set."
                ),
            ),
            _entry(
                "past-paper-assistant-sgad",
                "scanned",
                "ppsc66/Past_Paper_Assistant__S_GAD.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "english", "real", "camscanner"],
                notes=(
                    "CamScanner scan, 5pp (55 chars watermark only, 2 "
                    "images/page), OCR-only; Assistant (S&GAD) past paper."
                ),
            ),
            _entry(
                "capsule-gk",
                "scanned",
                "ppsc66/Capsule_of_GK.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "english", "real", "scale-test", "stress-test"],
                notes=(
                    "Essentially scanned, 195pp (7,417 chars, watermark text "
                    "only), 1 image/page; largest fixture; OCR-only — do NOT "
                    "run full OCR in M4; M7 stress test."
                ),
            ),
            _entry(
                "history-notes-3000bc-2023",
                "scanned",
                "ppsc66/3000B.c_to_2023_History_Notes_by_gkwithadnan.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["scanned", "english", "real", "notes"],
                notes=(
                    "Pure scanned notes book, 13pp (ZERO text-layer chars, 1 "
                    "image/page); long-form scanned notes, not MCQs; OCR-only."
                ),
            ),
            _entry(
                "pak-affairs-notes-csps",
                "digital",
                "ppsc66/Pak_Affairs_by_CSPs.pdf",
                None,
                reference_kind="none",
                reference_file=None,
                lines=None,
                categories=["digital", "english", "real", "notes"],
                notes=(
                    "Study NOTES book, 75pp (92,472 chars), NOT an MCQ paper — "
                    "long-form notes document type. Carries a copyright notice; "
                    "test fixture only, never redistribute."
                ),
            ),
        ]
    )

    dataset = {
        "version": "golden-v2",
        "created": "2026-11-21",
        "sources": {
            "synthetic": "scripts/generate_m2_fixtures.py (M2, deterministic)",
            "ppsc66": "~/workspace/officerpath-ai/test-fixtures/ppsc66/ (copies)",
        },
        "reference_kinds": {
            "ground_truth": "exact text drawn into the fixture (synthetic only)",
            "gemini_reference": ("Gemini 3.5-flash-lite OCR output (reference, not ground truth)"),
            "gemini_reference_hand_verified": (
                "Gemini reference, hand-checked vs the image (p-1 only)"
            ),
            "extracted_ground_truth": (
                "programmatically extracted from the file's own text layer "
                "(inline answer marking), NOT hand-verified — see "
                "scripts/extract_golden_v2_ground_truth.py"
            ),
            "none": "no reference exists for this entry",
        },
        "hand_verified_pages": ["ppsc66-p1"],
        "entries": entries,
    }
    (OUT / "dataset.json").write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"golden dataset v2: {len(entries)} entries, {len(copied)} reference texts copied")
    print(f"written to {OUT / 'dataset.json'}")


if __name__ == "__main__":
    main()
