# M7 parse driver (2026-11-22): run ONE parse in a FRESH process
# and report wall time + sampled concurrent tree RSS (python
# parent + live tesseract children, 100 ms sampling) + the
# recovered-question count. Fresh-process measurement matters:
# a long-lived worker retains RSS across parses (M7 finding), so
# a same-process measurement would overstate a single parse.
#
# Usage:
#   .venv/bin/python scripts/m7_parse_once.py --pdf PATH [--multi-pass]
#   .venv/bin/python scripts/m7_parse_once.py --image PATH
# Prints exactly one JSON object on stdout.
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _vmrss_kb(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        return 0
    return 0


def _child_pids(ppid: int) -> list[int]:
    out = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text().split()
            if int(stat[3]) == ppid:
                out.append(int(entry.name))
        except Exception:
            pass
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--multi-pass", action="store_true")
    parser.add_argument(
        "--dump",
        type=Path,
        default=None,
        help="also write the matched document (questions + promotion) "
        "as JSON, so a benchmark can score/calibrate without a "
        "second OCR pass",
    )
    args = parser.parse_args()
    if bool(args.pdf) == bool(args.image):
        raise SystemExit("exactly one of --pdf / --image is required")

    from app.pipeline.matching.service import (  # noqa: E402
        parse_document_bytes,
        parse_image_bytes,
    )

    data = (args.pdf or args.image).read_bytes()  # type: ignore[union-attr]
    me = os.getpid()
    stop = threading.Event()
    peak = {"tree": 0, "parent": 0, "children": 0}

    def sampler() -> None:
        while not stop.wait(0.1):
            parent = _vmrss_kb(me)
            children = sum(_vmrss_kb(p) for p in _child_pids(me))
            peak["parent"] = max(peak["parent"], parent)
            peak["children"] = max(peak["children"], children)
            peak["tree"] = max(peak["tree"], parent + children)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    t0 = time.monotonic()
    if args.pdf is not None:
        matched, _, _ = parse_document_bytes(data, "m7-parse-once", multi_pass=args.multi_pass)
    else:
        matched, _, _ = parse_image_bytes(data, "m7-parse-once")
    seconds = round(time.monotonic() - t0, 1)
    stop.set()
    thread.join(timeout=2)
    out: dict = {
        "seconds": seconds,
        "questions": len(matched.questions),
        "answered": matched.answered,
        "unknown": matched.unknown,
        "pending": len(matched.pending),
        "tree_peak_mb": round(peak["tree"] / 1024),
        "parent_peak_mb": round(peak["parent"] / 1024),
        "child_peak_mb": round(peak["children"] / 1024),
        "parent_high_water_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "multi_pass": bool(args.multi_pass),
    }
    if args.pdf is not None:
        from benchmark_m5 import _ppsc66_key_gt  # noqa: E402

        key_gt = _ppsc66_key_gt()
        recovered = {
            q.number for q in matched.questions if q.number is not None and 1 <= q.number <= 100
        }
        import re as _re

        correct = 0
        for q in matched.questions:
            if q.number in key_gt and q.correct_index >= 0:
                m = _re.search(r"\(([A-D])\)", key_gt[q.number])
                if m and ord(m.group(1)) - 65 == q.correct_index:
                    correct += 1
        out["recovered_of_100"] = len(recovered)
        out["answers_correct_vs_key"] = correct
    if args.dump is not None:
        args.dump.write_text(
            json.dumps(
                {
                    "questions": [q.to_dict() for q in matched.questions],
                    "pending": [
                        {"number": p["number"], "text": p["text"]} for p in matched.pending
                    ],
                    "promotion": matched.promotion,
                    "counts": matched.counts,
                },
                ensure_ascii=False,
            )
        )
    print(json.dumps(out))


if __name__ == "__main__":
    main()
