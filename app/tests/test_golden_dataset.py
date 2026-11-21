# OfficerPath AI — Phase 1, M3
# Golden dataset v1: manifest integrity + ground truth sanity.
# The benchmark stands on this file; if it rots, the numbers rot.

import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"
M2 = Path(__file__).resolve().parent / "fixtures" / "m2"
PPSC66 = Path(__file__).resolve().parent / "fixtures" / "ppsc66"


def _dataset():
    return json.loads((GOLDEN / "dataset.json").read_text(encoding="utf-8"))


def test_manifest_version_and_counts():
    dataset = _dataset()
    assert dataset["version"] == "golden-v2"
    assert len(dataset["entries"]) == 38  # 19 v1 + 18 v2 + 1 Nastaliq (M4)
    assert dataset["hand_verified_pages"] == ["ppsc66-p1"]


def test_every_reference_file_exists():
    dataset = _dataset()
    for entry in dataset["entries"]:
        if entry["reference_file"]:
            path = GOLDEN / entry["reference_file"]
            assert path.exists(), f"missing reference {entry['reference_file']}"
            assert path.stat().st_size > 0


def test_extracted_ground_truth_files_parse_and_count():
    """v2: every extracted_ground_truth reference must parse as JSON and
    carry the measured row count (never hand-edited)."""
    dataset = _dataset()
    extracted = [e for e in dataset["entries"] if e["reference_kind"] == "extracted_ground_truth"]
    assert len(extracted) == 4  # ca40, testpoint, computer, urdu
    for entry in extracted:
        data = json.loads((GOLDEN / entry["reference_file"]).read_text(encoding="utf-8"))
        assert isinstance(data["count"], int) and data["count"] > 0, entry["id"]


def test_paper60_photo_points_at_real_files():
    """v2 (M4 fix): the M3 'missing' claim was wrong — the photo and the
    Gemini reference both exist now."""
    dataset = _dataset()
    entry = next(e for e in dataset["entries"] if e["id"] == "paper60-photo")
    assert entry["source"] == "ppsc66/paper60-photo.jpg"
    assert entry["reference_kind"] == "gemini_reference"
    assert entry["reference_file"] == "ppsc66/paper60_gemini_ocr.txt"
    # Source/reference live under the golden dir (like the ocr-*.txt files),
    # NOT under fixtures/ppsc66/ (which holds the M3 page images).
    assert (GOLDEN / entry["source"]).exists()
    assert (GOLDEN / entry["reference_file"]).exists()


def test_every_synthetic_source_exists():
    dataset = _dataset()
    for entry in dataset["entries"]:
        if entry["source"].startswith("m2/"):
            assert (M2 / entry["source"][3:]).exists()


def test_every_ppsc66_image_exists():
    dataset = _dataset()
    for entry in dataset["entries"]:
        if entry["source"].startswith("ppsc66/p-"):
            assert (PPSC66 / entry["source"][7:]).exists()


def test_synthetic_ground_truth_has_four_questions():
    dataset = _dataset()
    entry = next(e for e in dataset["entries"] if e["id"] == "synthetic-clean-p1")
    assert entry["reference_kind"] == "ground_truth"
    stems = [line for line in entry["lines"] if line[0].isdigit() and ". " in line]
    assert len(stems) == 4


def test_two_column_entry_has_left_and_right():
    dataset = _dataset()
    entry = next(e for e in dataset["entries"] if e["id"] == "synthetic-clean-p2")
    assert entry["left_column_lines"][0].startswith("1.")
    assert entry["right_column_lines"][0].startswith("3.")


def test_ppsc66_p1_is_the_only_hand_verified_page():
    dataset = _dataset()
    verified = [e["id"] for e in dataset["entries"] if e["hand_verified"]]
    assert verified == ["ppsc66-p1"]
    p1 = next(e for e in dataset["entries"] if e["id"] == "ppsc66-p1")
    assert "Ala" in p1["notes"]  # the one reference error found by hand


def test_digital_extractor_reproduces_synthetic_ground_truth():
    """Cross-check: the ground truth must be what the digital
    extractor reads from the fixture (CER ~ 0). If this fails, the
    dataset — not the engine — is wrong."""
    import uuid

    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.digital import DigitalExtractor
    from app.pipeline.ocr.metrics import cer

    dataset = _dataset()
    entry = next(e for e in dataset["entries"] if e["id"] == "synthetic-clean-p1")
    pdf_bytes = (M2 / "clean.pdf").read_bytes()
    blocks = DigitalExtractor().recognize(
        PageContext(
            document_id=uuid.uuid4(),
            page_number=1,
            storage_path="",
            pdf_bytes=pdf_bytes,
        )
    )
    hypothesis = "\n".join(b.text for b in blocks)
    assert cer("\n".join(entry["lines"]), hypothesis) == 0.0
