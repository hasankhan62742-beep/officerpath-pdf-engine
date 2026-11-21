"""Build the golden dataset v1 (M3): versioned ground-truth +
reference annotations for the benchmark harness.

Run from the repo root:  .venv/bin/python scripts/build_golden_dataset.py

Outputs (all under app/tests/fixtures/golden/):
- dataset.json: the manifest — version, sources, per-page entries.
  synthetic pages carry EXACT ground truth (the text the M2 fixture
  generator drew — see scripts/generate_m2_fixtures.py QUESTIONS);
  PPSC-66 pages carry the Gemini OCR text as REFERENCE (labelled as
  such — it is Gemini output, not hand-verified ground truth),
  except p-1, which was hand-verified against the page image in M3.
- ppsc66/*.txt: copies of the Gemini reference texts from the
  Flutter repo (read-only source; never modified there) + PROVENANCE.

Ground truth vs reference, stated plainly: CER/WER on synthetic
pages measure against exact ground truth. CER/WER on PPSC-66 pages
measure against the Gemini reference — i.e. "how close is this
engine to Gemini's reading", not "how close to the printed page".
The hand-verified p-1 sample bounds the reference's own error (see
dataset.json: 1 word error found in ~700 words on p-1).
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
    (OUT / "ppsc66" / "PROVENANCE.md").write_text(
        "# Golden dataset v1 — PPSC-66 reference texts (copies)\n\n"
        "Copied (not moved) from the Flutter repo's golden fixtures:\n"
        "`~/workspace/officerpath-ai/test-fixtures/ppsc66/`\n\n"
        "These are GEMINI OCR OUTPUT (model gemini-3.5-flash-lite, the\n"
        "app's own prompt), not hand-verified ground truth — except\n"
        "p-1, which was hand-verified against the page image in M3\n"
        "(see dataset.json). The Flutter repo is the source of truth\n"
        "and is NEVER modified by the engine.\n\n"
        "Files copied:\n\n" + "".join(f"- `{name}`\n" for name in copied),
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
    # Paper 60: one of the three acceptance files, but NO file for it
    # exists in the Flutter repo's test-fixtures (checked 2026-11-21:
    # no paper60 image, no Gemini reference text). The entry is kept
    # with reference_kind "none" so the gap stays visible instead of
    # silently claiming a reference that was never copied.
    entries.append(
        _entry(
            "paper60-photo",
            "scanned",
            "absent: no Paper 60 file in "
            "~/workspace/officerpath-ai/test-fixtures/ppsc66/ (checked 2026-11-21)",
            1,
            reference_kind="none",
            reference_file=None,
            lines=None,
            categories=["scanned", "photo", "english", "real"],
            notes=(
                "Paper 60 phone photo; no image and no Gemini reference "
                "text exist in the source fixtures, so the benchmark "
                "records it as not-run."
            ),
        )
    )

    dataset = {
        "version": "golden-v1",
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
            "none": (
                "no reference exists for this entry (Paper 60: file absent from source fixtures)"
            ),
        },
        "hand_verified_pages": ["ppsc66-p1"],
        "entries": entries,
    }
    (OUT / "dataset.json").write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"golden dataset v1: {len(entries)} entries, {len(copied)} reference texts copied")
    print(f"written to {OUT / 'dataset.json'}")


if __name__ == "__main__":
    main()
