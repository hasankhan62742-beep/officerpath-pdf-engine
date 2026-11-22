# M7 DPI experiment: does rendering PPSC-66 at 150 DPI instead
# of 200 keep the same recovery? Same OCR (PSM 3 + layout) +
# extract + resolve + match flow as the M6 live promotion arm,
# scored against the Gemini key GT. VM numbers.
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

from benchmark_m6 import _ppsc66_key_gt  # noqa: E402

from app.config import Settings  # noqa: E402
from app.pipeline.answers.service import apply_resolution  # noqa: E402
from app.pipeline.extract.service import extract_from_ocr_blocks  # noqa: E402
from app.pipeline.interfaces import PageContext  # noqa: E402
from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer  # noqa: E402
from app.pipeline.matching import match_document  # noqa: E402
from app.pipeline.matching.promotion import promote_pending  # noqa: E402
from app.pipeline.matching.service import resolve_with_key_detection  # noqa: E402
from app.pipeline.ocr.psm import select_psm  # noqa: E402
from app.pipeline.ocr.tesseract import TesseractAdapter  # noqa: E402
from app.pipeline.pdf.quality import measure_quality, png_to_gray  # noqa: E402
from app.pipeline.pdf.renderer import render_pdf_page  # noqa: E402

FLUTTER_FIX = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"


def run(dpi: int) -> dict:
    settings = Settings()
    pdf = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    analyzer = GeometryLayoutAnalyzer()
    all_blocks, lines = [], []
    t0 = time.monotonic()
    for page_number in range(1, 8):
        rendered = render_pdf_page(pdf, page_number, dpi=dpi)
        quality = measure_quality(png_to_gray(rendered.png_bytes))
        adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=select_psm(quality))
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page_number,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        blocks = adapter.recognize(context)
        layout = analyzer.analyze(context, blocks)
        for region in layout.get("regions", []):
            idx = region["block_index"]
            if 0 <= idx < len(blocks):
                blocks[idx].reading_order = region["reading_order"]
        ordered = sorted(
            blocks,
            key=lambda b: b.reading_order if b.reading_order is not None else 10**6,
        )
        all_blocks.extend(ordered)
        lines.extend(ln for b in ordered for ln in b.text.splitlines() if ln.strip())
    result = extract_from_ocr_blocks(all_blocks, "m7-dpi")
    resolution, _ = resolve_with_key_detection(result, lines, "m7-dpi")
    apply_resolution(result, resolution)
    promotion_report = promote_pending(result, resolution)
    matched = match_document(
        result,
        resolution,
        promoted_numbers=set(promotion_report.promoted),
        promotion_report=promotion_report,
    )
    seconds = round(time.monotonic() - t0, 1)
    recovered = {
        q.number for q in matched.questions if q.number is not None and 1 <= q.number <= 100
    }
    key_gt = _ppsc66_key_gt()
    correct = 0
    for q in matched.questions:
        if q.number in key_gt and q.correct_index >= 0:
            import re as _re

            m = _re.search(r"\(([A-D])\)", key_gt[q.number])
            if m and ord(m.group(1)) - 65 == q.correct_index:
                correct += 1
    return {
        "dpi": dpi,
        "seconds": seconds,
        "questions": len(matched.questions),
        "answered": matched.answered,
        "recovered_of_100": len(recovered),
        "answers_correct_vs_key": correct,
    }


if __name__ == "__main__":
    for dpi in (200, 150):
        print(run(dpi), flush=True)
