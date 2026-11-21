"""PaddleOCR benchmark, one fresh process per page.

The single-process pass (scripts/benchmark_m3.py --engine paddleocr)
was OOM-killed (exit 137) on this VM: the PaddleX OCR pipeline
(doc preprocessor + UVDoc + textline orientation + det + rec, all
ONNX sessions) grows its arenas across pages, and the VM had only
~1.8 GB available at the time. This driver runs each page in its own
process (scripts/_paddleocr_one.py) and merges the rows into the
same partial-JSON shape as benchmark_m3.py, so --merge accepts it.

Usage (from the repo root):
    HF_HUB_DISABLE_XET=1 .venv/bin/python \\
        scripts/benchmark_paddleocr_perpage.py \\
        --out /tmp/m3-bench/paddleocr.json

Default entries (8): the clean synthetic page, the two-column
synthetic page, the scanned synthetic page, PPSC-66 p.1, p.3 and
p.6, and both table photos. Override with --entries (comma list of
dataset entry ids). Pages not run are recorded as status
"not_run_subset" in the merged file's note, never as numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ENTRIES = [
    "synthetic-clean-p1",
    "synthetic-clean-p2",
    "synthetic-scanned-p1",
    "ppsc66-p1",
    "ppsc66-p3",
    "ppsc66-p6",
    "ppsc66-table-computer-q67-81",
    "ppsc66-table-interjection-q230-257",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="PaddleOCR per-page benchmark")
    parser.add_argument("--entries", default=",".join(DEFAULT_ENTRIES))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import benchmark_m3  # noqa: PLC0415 - reuse dataset + image loaders

    dataset = benchmark_m3._load_dataset()
    wanted = set(args.entries.split(","))
    rows: list[dict] = []
    started = time.monotonic()
    env = dict(os.environ)
    env["HF_HUB_DISABLE_XET"] = "1"
    with tempfile.TemporaryDirectory(prefix="m3-paddle-") as tmp:
        tmp_path = Path(tmp)
        for entry in dataset["entries"]:
            if entry["id"] not in wanted:
                continue
            reference = benchmark_m3._reference_text(entry)
            if reference is None:
                rows.append({"entry": entry["id"], "status": "no_reference"})
                continue
            png_bytes, source_note = benchmark_m3._page_bytes(entry)
            if png_bytes is None:
                rows.append({"entry": entry["id"], "status": "not_run", "reason": source_note})
                continue
            image_path = tmp_path / f"{entry['id']}.png"
            image_path.write_bytes(png_bytes)
            reference_path = tmp_path / f"{entry['id']}.ref.txt"
            reference_path.write_text(reference, encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "_paddleocr_one.py"),
                "--image",
                str(image_path),
                "--entry",
                entry["id"],
                "--reference",
                str(reference_path),
                "--page",
                str(entry["page"]),
            ]
            if entry.get("left_column_lines") and entry.get("right_column_lines"):
                left_path = tmp_path / f"{entry['id']}.left.txt"
                right_path = tmp_path / f"{entry['id']}.right.txt"
                left_path.write_text("\n".join(entry["left_column_lines"]), encoding="utf-8")
                right_path.write_text("\n".join(entry["right_column_lines"]), encoding="utf-8")
                command += ["--left", str(left_path), "--right", str(right_path)]
            completed = subprocess.run(
                command, capture_output=True, text=True, env=env, timeout=600
            )
            if completed.returncode != 0:
                reason = (completed.stderr.strip().splitlines() or ["exit != 0"])[-1]
                if completed.returncode in (-9, 137):
                    reason = "oom_killed (exit 137) in the per-page process"
                rows.append({"entry": entry["id"], "status": "engine_error", "reason": reason})
                print(f"{entry['id']}: FAILED ({reason})", flush=True)
                continue
            row = json.loads(completed.stdout.strip().splitlines()[-1])
            rows.append(row)
            print(
                f"{row['entry']}: CER={row.get('cer')} WER={row.get('wer')} "
                f"{row.get('seconds')}s peak={row.get('peak_rss_mb')}MB",
                flush=True,
            )
    result = {
        "engine": "paddleocr",
        "engine_version": "3.7.0 (PP-OCRv5 server det + arabic mobile rec, onnxruntime 1.32.0)",
        "load_seconds": None,
        "total_seconds": round(time.monotonic() - started, 1),
        # Max single-page peak RSS across the per-page processes
        # (each process loads the full pipeline once).
        "peak_rss_mb": max(
            (
                r.get("peak_rss_mb") or 0
                for r in rows
                if isinstance(r.get("peak_rss_mb"), (int, float))
            ),
            default=None,
        ),
        "python": platform.python_version(),
        "machine": f"{platform.machine()} {platform.system()}",
        "method": "per-page subprocess (single-process pass OOM-killed, exit 137)",
        "entries_run": sorted(wanted),
        "rows": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"paddleocr (per-page): wrote {args.out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
