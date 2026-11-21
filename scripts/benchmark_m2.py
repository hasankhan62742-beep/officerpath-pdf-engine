"""M2 benchmark: run the PDF stage over every fixture + the PPSC-66
pages and print a measured table (timings, peak RSS, quality
before/after). Used for the numbers in docs/milestones/MILESTONE_2_REPORT.md.

Usage (from the repo root):
    .venv/bin/python scripts/benchmark_m2.py

Hardware is whatever runs it (labelled in the output) — the VM numbers
are NOT Render numbers (Render free is 0.1 CPU / 512 MB; see ADR-001).
Peak RSS is the process peak (ru_maxrss), i.e. an upper bound that
includes the Python interpreter + imported OpenCV/PyMuPDF.
"""

from __future__ import annotations

import resource
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.pipeline.ingestion.service import NullStageRecorder
from app.pipeline.pdf.service import run_pdf_stage
from app.storage.local import LocalDiskStorage

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "app" / "tests" / "fixtures" / "m2"
PPSC66 = ROOT / "app" / "tests" / "fixtures" / "ppsc66"


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> None:
    import platform

    print(f"python: {platform.python_version()} on {platform.machine()} {platform.system()}")
    print(f"baseline peak RSS: {_peak_rss_mb():.1f} MB")
    targets = [
        ("clean.pdf", FIXTURES / "clean.pdf"),
        ("scanned.pdf", FIXTURES / "scanned.pdf"),
        ("mixed.pdf", FIXTURES / "mixed.pdf"),
        ("skewed.pdf", FIXTURES / "skewed.pdf"),
        ("low_contrast.pdf", FIXTURES / "low_contrast.pdf"),
        ("noisy.pdf", FIXTURES / "noisy.pdf"),
        ("blank.pdf", FIXTURES / "blank.pdf"),
    ] + [(f"ppsc66 p-{n}.png", PPSC66 / f"p-{n}.png") for n in range(1, 8)]
    with tempfile.TemporaryDirectory(prefix="officerpath-m2-bench-") as tmp:
        storage = LocalDiskStorage(tmp)
        settings = Settings()
        for name, path in targets:
            data = path.read_bytes()
            start = time.perf_counter()
            result = run_pdf_stage(
                document_id=uuid.uuid4(),
                job_id=uuid.uuid4(),
                filename=path.name,
                data=data,
                settings=settings,
                storage=storage,
                recorder=NullStageRecorder(),
            )
            elapsed = time.perf_counter() - start
            for page in result.pages:
                before = page.quality_before or {}
                after = page.quality_after or {}
                print(
                    f"{name} p{page.page_number}: {page.classification} "
                    f"profile={page.profile_name or '-'} "
                    f"skew {before.get('skew_degrees')} -> {after.get('skew_degrees')} "
                    f"blur {before.get('blur_score')} -> {after.get('blur_score')} "
                    f"contrast {before.get('contrast_score')} -> {after.get('contrast_score')} "
                    f"noise {before.get('noise_score')} -> {after.get('noise_score')} "
                    f"ink {before.get('ink_coverage')} -> {after.get('ink_coverage')} "
                    f"highlights={len(page.highlight_regions)} "
                    f"error={page.error}"
                )
            print(
                f"  -> {name}: {result.pages_processed} page(s) in {elapsed:.2f}s "
                f"({elapsed / max(result.pages_processed, 1):.2f}s/page), "
                f"failed={result.pages_failed}, peak RSS={_peak_rss_mb():.1f} MB"
            )
    print(f"final peak RSS: {_peak_rss_mb():.1f} MB")


if __name__ == "__main__":
    main()
