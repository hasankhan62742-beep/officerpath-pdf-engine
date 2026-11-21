"""One PaddleOCR page, in a fresh minimal process.

Run by scripts/benchmark_paddleocr_perpage.py (one subprocess per
page). Kept minimal on purpose: the full-pipeline PaddleOCR process
grows its ONNX arenas across pages and was OOM-killed (exit 137)
when run as one process over the whole dataset on this VM — see
docs/benchmarks/BENCHMARK_M3_2026-11-21.md. A fresh process per page
isolates that growth and reports an honest per-page peak RSS.

Usage:
    HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/_paddleocr_one.py \
        --image /tmp/page.png --entry ppsc66-p1 --reference ref.txt \
        --page 1 [--left ref-left.txt] [--right ref-right.txt]

Prints one JSON object on stdout: entry, status, cer, wer,
order_score, column_order_accuracy, seconds, blocks, layout
columns/tables, peak_rss_mb.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="One PaddleOCR page")
    parser.add_argument("--image", required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--left")
    parser.add_argument("--right")
    args = parser.parse_args()

    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.metrics import (
        cer,
        column_order_accuracy,
        pairwise_order_score,
        wer,
    )
    from app.pipeline.ocr.paddle import PaddleOCRAdapter

    reference = Path(args.reference).read_text(encoding="utf-8")
    png_bytes = Path(args.image).read_bytes()
    adapter = PaddleOCRAdapter(language="ar")
    load_start = time.monotonic()
    try:
        adapter._load_predictor()
    except Exception as exc:  # noqa: BLE001 - report as a row, not a crash
        print(
            json.dumps(
                {
                    "entry": args.entry,
                    "status": "engine_error",
                    "reason": f"predictor load failed: {exc}",
                    "peak_rss_mb": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1
                    ),
                }
            )
        )
        return
    load_seconds = time.monotonic() - load_start
    context = PageContext(
        document_id=uuid.uuid4(),
        page_number=args.page,
        storage_path="",
        classification="scanned",
        image_png=png_bytes,
    )
    page_start = time.monotonic()
    try:
        blocks = adapter.recognize(context)
    except Exception as exc:  # noqa: BLE001 - report as a row, not a crash
        print(
            json.dumps(
                {
                    "entry": args.entry,
                    "status": "engine_error",
                    "reason": str(exc),
                    "peak_rss_mb": round(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1
                    ),
                }
            )
        )
        return
    seconds = time.monotonic() - page_start
    layout = GeometryLayoutAnalyzer().analyze(context, blocks)
    for region in layout.get("regions", []):
        index = region["block_index"]
        if 0 <= index < len(blocks):
            blocks[index].reading_order = region["reading_order"]
    lines = []
    for block in sorted(
        blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
    ):
        lines.extend(line for line in block.text.split("\n") if line.strip())
    hypothesis = "\n".join(lines)
    reference_lines = [line for line in reference.split("\n") if line.strip()]
    row: dict = {
        "entry": args.entry,
        "status": "ok",
        "engine": "paddleocr",
        "load_seconds": round(load_seconds, 1),
        "seconds": round(seconds, 2),
        "blocks": len(blocks),
        "cer": round(cer(reference, hypothesis), 4),
        "wer": round(wer(reference, hypothesis), 4),
        "order_score": round(pairwise_order_score(reference_lines, lines), 3),
        "layout_column_count": layout.get("column_count"),
        "layout_tables": len(layout.get("tables", [])),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
    }
    if args.left and args.right:
        left_lines = Path(args.left).read_text(encoding="utf-8").splitlines()
        right_lines = Path(args.right).read_text(encoding="utf-8").splitlines()
        row["column_order_accuracy"] = round(
            column_order_accuracy(left_lines, right_lines, lines), 3
        )
    print(json.dumps(row))
    with suppress(Exception):
        adapter.close()


if __name__ == "__main__":
    main()
