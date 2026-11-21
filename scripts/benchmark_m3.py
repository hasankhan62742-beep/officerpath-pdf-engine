"""M3 benchmark: run the OCR engines + layout over the golden
dataset v1 and measure CER/WER, reading order, timings and memory.

Usage (from the repo root):
    # One engine per process (fresh process => clean peak-RSS per engine):
    .venv/bin/python scripts/benchmark_m3.py --engine digital \\
        --out /tmp/m3-digital.json
    .venv/bin/python scripts/benchmark_m3.py --engine tesseract \\
        --out /tmp/m3-tesseract.json
    .venv/bin/python scripts/benchmark_m3.py --engine paddleocr \\
        --out /tmp/m3-paddleocr.json
    .venv/bin/python scripts/benchmark_m3.py --engine stored-tesseract \\
        --out /tmp/m3-stored-tesseract.json
    # Merge + print the Markdown table:
    .venv/bin/python scripts/benchmark_m3.py --merge \\
        /tmp/m3-digital.json /tmp/m3-tesseract.json \\
        /tmp/m3-paddleocr.json /tmp/m3-stored-tesseract.json \\
        --out docs/benchmarks/m3-benchmark-2026-11-21.json

Hardware is whatever runs it (labelled in the output) — VM numbers
are NOT Render numbers (Render free is 0.1 CPU / 512 MB; see
ADR-001). Peak RSS is the fresh-process peak (ru_maxrss), i.e. an
upper bound that includes the interpreter + imported libraries.

Reference kinds (see dataset.json): synthetic pages measure against
EXACT ground truth; PPSC-66 pages measure against the Gemini
reference text (how close to Gemini's reading, not to the printed
page). The stored-tesseract pass compares the 20-Nov Tesseract
output files (already in the fixtures) against the same reference —
no engine is run for it.
"""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "app" / "tests" / "fixtures" / "golden"
M2 = ROOT / "app" / "tests" / "fixtures" / "m2"
PPSC66 = ROOT / "app" / "tests" / "fixtures" / "ppsc66"


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load_dataset() -> dict:
    return json.loads((GOLDEN / "dataset.json").read_text(encoding="utf-8"))


def _reference_text(entry: dict) -> str | None:
    """Reference text for one entry: ground-truth lines joined, or
    the Gemini reference file. None when no reference exists."""
    if entry["reference_kind"] == "ground_truth":
        return "\n".join(entry["lines"])
    if entry["reference_file"]:
        path = GOLDEN / entry["reference_file"]
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def _page_bytes(entry: dict) -> tuple[bytes | None, str]:
    """(page image bytes, source) for one entry, or (None, reason)."""
    source = entry["source"]
    if source.startswith("m2/"):
        pdf_path = M2 / source[3:]
        if not pdf_path.exists():
            return None, f"missing fixture {pdf_path}"
        from app.pipeline.pdf.renderer import render_pdf_page

        rendered = render_pdf_page(pdf_path.read_bytes(), entry["page"], dpi=200)
        return rendered.png_bytes, f"{source} p{entry['page']} rendered at 200 DPI"
    if source.startswith("ppsc66/"):
        path = PPSC66 / source[7:]
        if not path.exists():
            return None, f"missing fixture {path}"
        return path.read_bytes(), f"{source}"
    return None, f"no loader for source {source!r}"


def _page_pdf_bytes(entry: dict) -> bytes | None:
    source = entry["source"]
    if source.startswith("m2/"):
        pdf_path = M2 / source[3:]
        return pdf_path.read_bytes() if pdf_path.exists() else None
    return None


def _blocks_to_lines(blocks: list) -> list[str]:
    def _order(block) -> int:
        return block.reading_order if block.reading_order is not None else 10**6

    lines: list[str] = []
    for block in sorted(blocks, key=_order):
        lines.extend(line for line in block.text.split("\n") if line.strip())
    return lines


def _run_engine(engine_name: str) -> dict:
    from app.config import Settings
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.digital import DigitalExtractor
    from app.pipeline.ocr.metrics import cer, column_order_accuracy, pairwise_order_score, wer

    settings = Settings()
    dataset = _load_dataset()
    started = time.monotonic()
    engine: object | None = None
    engine_version: str | None = None
    load_seconds: float | None = None
    if engine_name == "digital":
        engine = DigitalExtractor()
        engine_version = engine.version
        load_seconds = 0.0
    elif engine_name == "tesseract":
        from app.pipeline.ocr.tesseract import TesseractAdapter

        load_start = time.monotonic()
        adapter = TesseractAdapter(
            languages=settings.tesseract_languages, psm=settings.tesseract_psm
        )
        info = adapter.probe()
        load_seconds = time.monotonic() - load_start
        if not info.available:
            return _unavailable_result(engine_name, info.reason or "unavailable")
        engine = adapter
        engine_version = info.version
    elif engine_name == "paddleocr":
        from app.pipeline.ocr.paddle import PaddleOCRAdapter

        load_start = time.monotonic()
        adapter = PaddleOCRAdapter(language=settings.paddleocr_language)
        probe = adapter.probe()
        if not probe.get("available"):
            return _unavailable_result(engine_name, str(probe.get("reason")))
        # Warm-up load (model files; timed separately, not a page time).
        try:
            adapter._load_predictor()
        except Exception as exc:
            return _unavailable_result(engine_name, f"predictor load failed: {exc}")
        load_seconds = time.monotonic() - load_start
        engine = adapter
        engine_version = adapter.version
    elif engine_name == "stored-tesseract":
        return _run_stored_tesseract()
    else:
        raise ValueError(f"unknown engine {engine_name!r}")

    analyzer = GeometryLayoutAnalyzer()
    rows: list[dict] = []
    for entry in dataset["entries"]:
        reference = _reference_text(entry)
        if reference is None:
            rows.append({"entry": entry["id"], "status": "no_reference"})
            continue
        if engine_name == "digital":
            if entry["kind"] == "scanned":
                # By design: the digital extractor only reads a text
                # layer. Scanned pages are the OCR engines' job; a
                # digital CER of 1.0 there would measure the wrong thing.
                rows.append({"entry": entry["id"], "status": "not_applicable_digital"})
                continue
            pdf_bytes = _page_pdf_bytes(entry)
            if pdf_bytes is None:
                rows.append({"entry": entry["id"], "status": "not_applicable_digital"})
                continue
            context = PageContext(
                document_id=uuid.uuid4(),
                page_number=entry["page"],
                storage_path="",
                classification=entry["kind"],
                pdf_bytes=pdf_bytes,
            )
        else:
            png_bytes, source_note = _page_bytes(entry)
            if png_bytes is None:
                rows.append({"entry": entry["id"], "status": "not_run", "reason": source_note})
                continue
            context = PageContext(
                document_id=uuid.uuid4(),
                page_number=entry["page"],
                storage_path="",
                classification=entry["kind"],
                image_png=png_bytes,
            )
        page_start = time.monotonic()
        try:
            blocks = engine.recognize(context)  # type: ignore[union-attr]
        except Exception as exc:
            rows.append({"entry": entry["id"], "status": "engine_error", "reason": str(exc)})
            continue
        seconds = time.monotonic() - page_start
        # Layout over this engine's blocks (reading order assigned here).
        layout = analyzer.analyze(context, blocks)
        # The analyser assigns reading_order per block index; apply it.
        for region in layout.get("regions", []):
            index = region["block_index"]
            if 0 <= index < len(blocks):
                blocks[index].reading_order = region["reading_order"]
        lines = _blocks_to_lines(blocks)
        hypothesis = "\n".join(lines)
        reference_lines = [line for line in reference.split("\n") if line.strip()]
        row: dict = {
            "entry": entry["id"],
            "status": "ok",
            "engine": engine_name,
            "seconds": round(seconds, 2),
            "blocks": len(blocks),
            "cer": round(cer(reference, hypothesis), 4),
            "wer": round(wer(reference, hypothesis), 4),
            "order_score": round(pairwise_order_score(reference_lines, lines), 3),
            "layout_column_count": layout.get("column_count"),
            "layout_tables": len(layout.get("tables", [])),
        }
        if entry.get("left_column_lines") and entry.get("right_column_lines"):
            row["column_order_accuracy"] = round(
                column_order_accuracy(
                    entry["left_column_lines"], entry["right_column_lines"], lines
                ),
                3,
            )
        rows.append(row)
    if engine_name == "paddleocr" and engine is not None:
        with suppress(Exception):
            engine.close()
    return {
        "engine": engine_name,
        "engine_version": engine_version,
        "load_seconds": round(load_seconds, 1) if load_seconds is not None else None,
        "total_seconds": round(time.monotonic() - started, 1),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "python": platform.python_version(),
        "machine": f"{platform.machine()} {platform.system()}",
        "rows": rows,
    }


def _unavailable_result(engine_name: str, reason: str) -> dict:
    return {
        "engine": engine_name,
        "engine_version": None,
        "load_seconds": None,
        "total_seconds": 0.0,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "python": platform.python_version(),
        "machine": f"{platform.machine()} {platform.system()}",
        "unavailable": reason,
        "rows": [],
    }


def _run_stored_tesseract() -> dict:
    """Compare the 20-Nov stored Tesseract output files against the
    Gemini reference (no engine run). The files are ocr-tess-*.txt in
    the golden ppsc66 copies."""
    from app.pipeline.ocr.metrics import cer, pairwise_order_score, wer

    dataset = _load_dataset()
    rows: list[dict] = []
    for entry in dataset["entries"]:
        if entry["id"].startswith("ppsc66-table-computer"):
            stored = GOLDEN / "ppsc66" / "ocr-tess-table-computer.txt"
        elif entry["id"].startswith("ppsc66-table-interjection"):
            stored = GOLDEN / "ppsc66" / "ocr-tess-table-interjection.txt"
        elif entry["id"].startswith("ppsc66-p"):
            stored = GOLDEN / "ppsc66" / f"ocr-tess-p{entry['page']}.txt"
        else:
            continue
        reference = _reference_text(entry)
        if reference is None or not stored.exists():
            rows.append({"entry": entry["id"], "status": "no_reference"})
            continue
        hypothesis = stored.read_text(encoding="utf-8")
        reference_lines = [line for line in reference.split("\n") if line.strip()]
        hyp_lines = [line for line in hypothesis.split("\n") if line.strip()]
        rows.append(
            {
                "entry": entry["id"],
                "status": "ok",
                "engine": "stored-tesseract",
                "seconds": 0.0,
                "blocks": None,
                "cer": round(cer(reference, hypothesis), 4),
                "wer": round(wer(reference, hypothesis), 4),
                "order_score": round(pairwise_order_score(reference_lines, hyp_lines), 3),
                "layout_column_count": None,
                "layout_tables": None,
            }
        )
    return {
        "engine": "stored-tesseract",
        "engine_version": "5.3.4 (stored output, 20 Nov 2026)",
        "load_seconds": 0.0,
        "total_seconds": 0.0,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "python": platform.python_version(),
        "machine": f"{platform.machine()} {platform.system()}",
        "rows": rows,
    }


def _merge(paths: list[str], out: str) -> None:
    merged = {
        "dataset_version": _load_dataset()["version"],
        "created": "2026-11-21",
        "hardware_note": "VM numbers — NOT Render numbers (Render free: 0.1 CPU / 512 MB)",
        "engines": {},
    }
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merged["engines"][data["engine"]] = data
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"merged benchmark written to {out}")
    print()
    print("| Engine | Entry | CER | WER | Order | s | Blocks | Cols |")
    print("|---|---|---|---|---|---|---|---|")
    for engine_name, data in merged["engines"].items():
        if "unavailable" in data:
            print(f"| {engine_name} | UNAVAILABLE: {data['unavailable']} | | | | | | |")
            continue
        for row in data["rows"]:
            if row.get("status") != "ok":
                print(f"| {engine_name} | {row['entry']} | {row.get('status')} | | | | | |")
                continue
            print(
                f"| {engine_name} | {row['entry']} | {row['cer']} | {row['wer']} | "
                f"{row['order_score']} | {row['seconds']} | {row['blocks']} | "
                f"{row.get('layout_column_count')} |"
            )
    print()
    for engine_name, data in merged["engines"].items():
        load = data.get("load_seconds")
        load_text = f"{load}s" if load is not None else "n/a (per-page processes)"
        print(
            f"{engine_name}: version={data.get('engine_version')} "
            f"load={load_text} total={data.get('total_seconds')}s "
            f"peak_rss={data.get('peak_rss_mb')} MB"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="M3 OCR benchmark harness")
    parser.add_argument(
        "--engine", choices=["digital", "tesseract", "paddleocr", "stored-tesseract"]
    )
    parser.add_argument("--merge", nargs="+", metavar="PARTIAL_JSON")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.merge:
        _merge(args.merge, args.out)
        return
    if not args.engine:
        parser.error("--engine or --merge is required")
    result = _run_engine(args.engine)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{args.engine}: wrote {args.out} ({len(result['rows'])} rows, "
        f"peak RSS {result['peak_rss_mb']} MB)"
    )


if __name__ == "__main__":
    main()
