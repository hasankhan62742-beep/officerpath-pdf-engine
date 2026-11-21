# OfficerPath AI — M5 PPSC-66 full-run experiment (scratch, NOT a deliverable).
#
# Compares three live-Tesseract paths over all 7 pages at 200 DPI
# and measures end-to-end recovery (extracted question numbers
# 1..100) for each:
#   psm3-raw:    PSM 3, raw Tesseract block order (no layout stage)
#   psm3-layout: PSM 3 + GeometryLayoutAnalyzer reading order
#                (the M4 live path — is the layout step helping or
#                hurting recovery?)
#   psm4-raw:    PSM 4, raw order (p5 prefers PSM 4 in the
#                per-page experiment)
# Plus a per-page-best oracle (best numbered-start recovery per
# page across the per-page experiment) as an upper bound.
#
# Writes incrementally to /tmp/m5-full-experiment.json. Raw lines
# per page per variant are saved under /tmp/m5-full/.
#
# Usage: .venv/bin/python scripts/m5_full_run_experiment.py

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
PPSC66_DIR = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = Path("/tmp/m5-full-experiment.json")
LINES_DIR = Path("/tmp/m5-full")
LINES_DIR.mkdir(parents=True, exist_ok=True)


def _lines_from_blocks(blocks) -> list[str]:
    lines: list[str] = []
    for block in sorted(
        blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
    ):
        lines.extend(ln for ln in block.text.split("\n") if ln.strip())
    return lines


def _run_variant(pdf_bytes: bytes, psm: int, use_layout: bool, label: str) -> dict:
    from app.pipeline.extract.service import PageLines, extract_document
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.renderer import render_pdf_page

    adapter = TesseractAdapter(languages="eng+urd", psm=psm)
    analyzer = GeometryLayoutAnalyzer()
    pages: list = []
    per_page: dict = {}
    total_start = time.monotonic()
    for page in range(1, 8):
        start = time.monotonic()
        rendered = render_pdf_page(pdf_bytes, page, dpi=200)
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        blocks = adapter.recognize(context)
        if use_layout:
            layout = analyzer.analyze(context, blocks)
            for region in layout.get("regions", []):
                idx = region["block_index"]
                if 0 <= idx < len(blocks):
                    blocks[idx].reading_order = region["reading_order"]
        lines = _lines_from_blocks(blocks)
        (LINES_DIR / f"lines_p{page}_{label}.txt").write_text("\n".join(lines), encoding="utf-8")
        pages.append(PageLines(page_number=page, lines=lines, is_ocr=True))
        per_page[f"p{page}"] = {
            "seconds": round(time.monotonic() - start, 2),
            "blocks": len(blocks),
            "lines": len(lines),
            "layout_column_count": layout.get("column_count") if use_layout else None,
        }
        print(
            f"  {label} p{page}: {len(blocks)} blocks, {len(lines)} lines, "
            f"{per_page[f'p{page}']['seconds']}s",
            flush=True,
        )
    extract_start = time.monotonic()
    result = extract_document(pages, source_document_id="ppsc-66")
    extract_seconds = round(time.monotonic() - extract_start, 2)
    detected_numbers = sorted(
        {q.number for q in result.questions if q.number is not None}
        | {p.number for p in result.pending if p.number is not None}
    )
    numbers_1_100 = [n for n in detected_numbers if 1 <= n <= 100]
    return {
        "variant": label,
        "psm": psm,
        "use_layout": use_layout,
        "total_seconds": round(time.monotonic() - total_start, 2),
        "extract_seconds": extract_seconds,
        "per_page": per_page,
        "questions": len(result.questions),
        "pending": len(result.pending),
        "questions_recovered_of_100": len(numbers_1_100),
        "detected_numbers_1_100": numbers_1_100,
        "missing_numbers_1_100": [n for n in range(1, 101) if n not in numbers_1_100],
        "options_complete_4_of_4": sum(1 for q in result.questions if len(q.options) == 4),
        "key_sections_found": result.key_sections_found,
        "key_entries_applied": result.key_entries_applied,
        "unmatched_key_entries": result.unmatched_key_entries,
        "number_gaps": result.number_gaps,
        "number_duplicates": result.number_duplicates,
        "skipped": len(result.skipped),
        "excluded": len(result.excluded),
    }


def main() -> None:
    results: dict = {}
    if OUT.exists():
        try:
            results = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            results = {}

    def _write() -> None:
        OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    pdf_bytes = (PPSC66_DIR / "ppsc_paper_66.pdf").read_bytes()
    for label, psm, use_layout in [
        ("psm3-raw", 3, False),
        ("psm3-layout", 3, True),
        ("psm4-raw", 4, False),
    ]:
        print(f"== variant {label} ==", flush=True)
        row = _run_variant(pdf_bytes, psm, use_layout, label)
        results[label] = row
        _write()
        print(
            f"  {label}: recovered {row['questions_recovered_of_100']}/100, "
            f"questions={row['questions']} pending={row['pending']} "
            f"key_applied={row['key_entries_applied']} "
            f"in {row['total_seconds']}s",
            flush=True,
        )
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
