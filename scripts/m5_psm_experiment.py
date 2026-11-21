# OfficerPath AI — M5 PPSC-66 recovery experiment (scratch, NOT a deliverable).
#
# Question: why does live Tesseract (M4 baseline: 41/100 numbers) lose
# whole question ranges (Q10-Q24, Q68-Q96)? Stored-text diagnosis
# showed the question TEXT is present but the number is misread as
# punctuation (e.g. "39." -> ".", "41." -> "|."). This script tries
# bounded, cost-free variations on the two worst pages (p3: Q39-57,
# p5: Q78-96) and measures numbered-start recovery + CER vs the
# Gemini reference text, so M5 can pick a winner (or conclude the
# recovery stays OCR-bound) with evidence.
#
# Runs in the background while the M5 detectors are built. Writes
# incrementally to /tmp/m5-psm-experiment.json (a late kill must not
# lose measured variants). Raw lines per variant are saved under
# /tmp/m5-psm/ for later extraction-order tests (layout vs raw order).
#
# Usage: .venv/bin/python scripts/m5_psm_experiment.py

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "app/tests/fixtures/golden/ppsc66"
PPSC66_DIR = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = Path("/tmp/m5-psm-experiment.json")
LINES_DIR = Path("/tmp/m5-psm")
LINES_DIR.mkdir(parents=True, exist_ok=True)

PAGES = [3, 5]
EXPECTED = {3: list(range(39, 58)), 5: list(range(78, 97))}


def _lines_from_blocks(blocks) -> list[str]:
    lines: list[str] = []
    for block in sorted(
        blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
    ):
        lines.extend(ln for ln in block.text.split("\n") if ln.strip())
    return lines


def _numbered_starts(lines: list[str]) -> list[int]:
    from app.pipeline.extract.numbers import question_number_detailed

    found: list[int] = []
    for ln in lines:
        info = question_number_detailed(ln.strip())
        if info is not None:
            found.append(info[0])
    return sorted(set(found))


def _run_variant(page: int, png_bytes: bytes, psm: int, label: str) -> dict:
    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.metrics import cer
    from app.pipeline.ocr.tesseract import TesseractAdapter

    adapter = TesseractAdapter(languages="eng+urd", psm=psm)
    context = PageContext(
        document_id=uuid.uuid4(),
        page_number=page,
        storage_path="",
        classification="scanned",
        image_png=png_bytes,
    )
    start = time.monotonic()
    blocks = adapter.recognize(context)
    seconds = round(time.monotonic() - start, 2)
    lines = _lines_from_blocks(blocks)
    (LINES_DIR / f"lines_p{page}_{label}.txt").write_text("\n".join(lines), encoding="utf-8")
    gemini = (FIX / f"ocr-p{page}.txt").read_text(encoding="utf-8")
    hyp = "\n".join(lines)
    starts = _numbered_starts(lines)
    expected = EXPECTED[page]
    recovered = [n for n in expected if n in starts]
    return {
        "page": page,
        "variant": label,
        "psm": psm,
        "seconds": seconds,
        "blocks": len(blocks),
        "lines": len(lines),
        "numbered_starts": starts,
        "expected_numbers": expected,
        "recovered_of_expected": len(recovered),
        "missing_expected": [n for n in expected if n not in starts],
        "cer_vs_gemini": round(cer(gemini, hyp), 4),
    }


def _preprocessed_png(png_bytes: bytes, profile: str) -> bytes:
    from app.pipeline.preprocess.preprocessor import process_page

    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    processed = process_page(bgr, profile)
    gray = processed.gray
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("could not encode preprocessed page")
    return buf.tobytes()


def _gutter_numbers(png_bytes: bytes, page: int) -> dict:
    """Crop the left 15% of the page (the question-number gutter) and
    OCR it alone with PSM 6: do the margin numbers survive when the
    body text is out of the picture?"""
    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.tesseract import TesseractAdapter

    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    gutter = img[:, : max(1, int(w * 0.15))]
    ok, buf = cv2.imencode(".png", gutter)
    if not ok:
        raise RuntimeError("could not encode gutter crop")
    adapter = TesseractAdapter(languages="eng+urd", psm=6)
    context = PageContext(
        document_id=uuid.uuid4(),
        page_number=page,
        storage_path="",
        classification="scanned",
        image_png=buf.tobytes(),
    )
    start = time.monotonic()
    blocks = adapter.recognize(context)
    seconds = round(time.monotonic() - start, 2)
    text = "\n".join(b.text for b in blocks)
    import re

    nums = sorted({int(n) for n in re.findall(r"\b(\d{1,3})\b", text)})
    expected = EXPECTED[page]
    return {
        "page": page,
        "variant": "gutter-crop-psm6",
        "seconds": seconds,
        "numbers_found": nums,
        "recovered_of_expected": len([n for n in expected if n in nums]),
        "raw_text": text[:500],
    }


def main() -> None:
    from app.pipeline.pdf.renderer import render_pdf_page

    pdf_bytes = (PPSC66_DIR / "ppsc_paper_66.pdf").read_bytes()
    results: list[dict] = []
    if OUT.exists():
        try:
            results = json.loads(OUT.read_text(encoding="utf-8")).get("variants", [])
        except Exception:
            results = []

    def _write() -> None:
        OUT.write_text(
            json.dumps({"variants": results}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    for page in PAGES:
        rendered = render_pdf_page(pdf_bytes, page, dpi=200)
        print(
            f"== p{page}: render {rendered.width_px}x{rendered.height_px} "
            f"@ {rendered.dpi_used} DPI ==",
            flush=True,
        )
        for label, psm, png in [
            ("psm3", 3, rendered.png_bytes),
            ("psm6", 6, rendered.png_bytes),
            ("psm4", 4, rendered.png_bytes),
            ("psm11", 11, rendered.png_bytes),
        ]:
            print(f"-- p{page} {label} ...", flush=True)
            row = _run_variant(page, png, psm, label)
            results.append(row)
            _write()
            print(
                f"   recovered {row['recovered_of_expected']}/{len(EXPECTED[page])} "
                f"CER {row['cer_vs_gemini']} in {row['seconds']}s",
                flush=True,
            )
        print(f"-- p{page} preprocessed-default-psm3 ...", flush=True)
        pre_png = _preprocessed_png(rendered.png_bytes, "default")
        row = _run_variant(page, pre_png, 3, "preprocessed-default-psm3")
        results.append(row)
        _write()
        print(
            f"   recovered {row['recovered_of_expected']}/{len(EXPECTED[page])} "
            f"CER {row['cer_vs_gemini']} in {row['seconds']}s",
            flush=True,
        )
        print(f"-- p{page} 300dpi-psm3 ...", flush=True)
        rendered300 = render_pdf_page(pdf_bytes, page, dpi=300)
        row = _run_variant(page, rendered300.png_bytes, 3, "psm3-300dpi")
        results.append(row)
        _write()
        print(
            f"   recovered {row['recovered_of_expected']}/{len(EXPECTED[page])} "
            f"CER {row['cer_vs_gemini']} in {row['seconds']}s",
            flush=True,
        )
        print(f"-- p{page} gutter-crop-psm6 ...", flush=True)
        row = _gutter_numbers(rendered.png_bytes, page)
        results.append(row)
        _write()
        print(
            f"   gutter recovered {row['recovered_of_expected']}/{len(EXPECTED[page])} "
            f"in {row['seconds']}s",
            flush=True,
        )
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
