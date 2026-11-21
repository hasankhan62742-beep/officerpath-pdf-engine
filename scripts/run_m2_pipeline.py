"""Run the M2 PDF stage on one file and print the per-page results.

Usage (from the repo root):
    .venv/bin/python scripts/run_m2_pipeline.py <file.pdf|image> [--dpi 200]

This is the M7 worker's future call in miniature: it validates the
file, runs analysis -> classification -> rendering -> preprocessing
page by page, stores the renders under a temp storage dir, and prints
quality before/after per page. No database, no Supabase, no deploy —
the NullStageRecorder logs stage transitions only.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.pipeline.ingestion.service import NullStageRecorder
from app.pipeline.pdf.service import run_pdf_stage
from app.storage.local import LocalDiskStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M2 PDF stage on one file.")
    parser.add_argument("file", help="PDF or image file to process")
    parser.add_argument("--dpi", type=int, default=200, help="render DPI (default 200)")
    parser.add_argument("--profile", default="auto", help="preprocess profile or 'auto'")
    args = parser.parse_args()
    path = Path(args.file)
    data = path.read_bytes()
    settings = Settings(render_dpi=args.dpi, preprocess_profile=args.profile)
    with tempfile.TemporaryDirectory(prefix="officerpath-m2-") as tmp:
        storage = LocalDiskStorage(tmp)
        result = run_pdf_stage(
            document_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            filename=path.name,
            data=data,
            settings=settings,
            storage=storage,
            recorder=NullStageRecorder(),
        )
    print(f"document: {result.document_id}")
    print(f"pages processed: {result.pages_processed}, failed: {result.pages_failed}")
    for page in result.pages:
        print(
            json.dumps(
                {
                    "page": page.page_number,
                    "classification": page.classification,
                    "profile": page.profile_name,
                    "quality_before": page.quality_before,
                    "quality_after": page.quality_after,
                    "original_render": page.original_render_path,
                    "processed_render": page.processed_render_path,
                    "highlights": len(page.highlight_regions),
                    "error": page.error,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
