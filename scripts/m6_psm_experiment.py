# OfficerPath AI — M6 per-page PSM experiment (2026-11-22).
#
# Question: can the M2 page-quality metrics route the Tesseract PSM
# per page? M5 measured p3 (wants PSM 3) vs p5 (wants PSM 4) and
# concluded quality does NOT explain the difference; M6 re-measures
# on ALL 7 PPSC-66 pages (PSM 3 vs PSM 4, recovery + CER vs the
# Gemini reference text) with the quality vector per page, so
# ADR-008 rests on the full paper, not two pages.
#
# Writes incrementally to docs/benchmarks/m6-psm-experiment.json
# (repo — survives a VM replacement) and to /tmp/m6-psm-experiment.json
# (the path benchmark_m6.py also checks). A late kill must not lose
# measured pages.
#
# Usage: .venv/bin/python scripts/m6_psm_experiment.py

from __future__ import annotations

import contextlib
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "app/tests/fixtures/golden/ppsc66"
PPSC66_DIR = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = ROOT / "docs/benchmarks/m6-psm-experiment.json"
OUT_TMP = Path("/tmp/m6-psm-experiment.json")

PAGES = [1, 2, 3, 4, 5, 6, 7]


def _numbered_starts(lines: list[str]) -> list[int]:
    from app.pipeline.extract.numbers import question_number_detailed

    found: list[int] = []
    for ln in lines:
        info = question_number_detailed(ln.strip())
        if info is not None:
            found.append(info[0])
    return sorted(set(found))


def _lines_from_blocks(blocks) -> list[str]:
    lines: list[str] = []
    for block in sorted(
        blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
    ):
        lines.extend(ln for ln in block.text.split("\n") if ln.strip())
    return lines


def _run_variant(page: int, png_bytes: bytes, psm: int) -> dict:
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
    gemini = (FIX / f"ocr-p{page}.txt").read_text(encoding="utf-8")
    hyp = "\n".join(lines)
    expected = _numbered_starts(gemini.splitlines())
    starts = _numbered_starts(lines)
    recovered = [n for n in expected if n in starts]
    return {
        "page": page,
        "variant": f"psm{psm}",
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


def main() -> None:
    from app.pipeline.pdf.quality import measure_quality, png_to_gray
    from app.pipeline.pdf.renderer import render_pdf_page

    pdf_bytes = (PPSC66_DIR / "ppsc_paper_66.pdf").read_bytes()
    data: dict = {"pages": {}}
    for path in (OUT, OUT_TMP):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except Exception:
                data = {"pages": {}}

    def _write() -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        OUT.write_text(payload, encoding="utf-8")
        with contextlib.suppress(Exception):
            OUT_TMP.write_text(payload, encoding="utf-8")

    for page in PAGES:
        if str(page) in data["pages"] and "psm4" in data["pages"][str(page)].get("variants", {}):
            print(f"p{page}: already measured, skipping", flush=True)
            continue
        rendered = render_pdf_page(pdf_bytes, page, dpi=200)
        quality = measure_quality(png_to_gray(rendered.png_bytes))
        entry: dict = {"quality": quality.to_dict(), "variants": {}}
        data["pages"][str(page)] = entry
        for psm in (3, 4):
            print(f"-- p{page} psm{psm} ...", flush=True)
            row = _run_variant(page, rendered.png_bytes, psm)
            entry["variants"][f"psm{psm}"] = row
            _write()
            print(
                f"   p{page} psm{psm}: {row['recovered_of_expected']}/"
                f"{len(row['expected_numbers'])} CER {row['cer_vs_gemini']} "
                f"in {row['seconds']}s",
                flush=True,
            )
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
