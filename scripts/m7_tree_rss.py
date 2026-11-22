# M7 Render-free fit: peak CONCURRENT tree RSS (python parent +
# live tesseract children) of one PPSC-66 parse in a FRESH
# process, sampled every 100ms. Also reports whether
# gc.collect() + malloc_trim returns the retained RSS.
# Usage: python /tmp/tree_rss.py [--multi-pass]
import contextlib
import ctypes
import gc
import resource
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.pipeline.matching.service import parse_document_bytes  # noqa: E402

FLUTTER_FIX = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"


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
    multi = "--multi-pass" in sys.argv
    stop = threading.Event()
    peak = {"tree": 0, "parent": 0, "children": 0}
    me = __import__("os").getpid()

    def sampler() -> None:
        while not stop.wait(0.1):
            parent = _vmrss_kb(me)
            children = sum(_vmrss_kb(p) for p in _child_pids(me))
            peak["parent"] = max(peak["parent"], parent)
            peak["children"] = max(peak["children"], children)
            peak["tree"] = max(peak["tree"], parent + children)

    t = threading.Thread(target=sampler, daemon=True)
    t.start()
    baseline = _vmrss_kb(me)
    p66 = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    t0 = time.monotonic()
    matched, _, _ = parse_document_bytes(p66, "m7-treerss", multi_pass=multi)
    dt = time.monotonic() - t0
    stop.set()
    t.join(timeout=2)
    before = _vmrss_kb(me)
    gc.collect()
    with contextlib.suppress(Exception):
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    after = _vmrss_kb(me)
    print(f"baseline parent VmRSS (imports loaded): {baseline / 1024:.0f} MB")
    print(
        f"mode={'multi-pass' if multi else 'single-path'} seconds={dt:.1f} "
        f"matched={len(matched.questions)} answered={matched.answered}"
    )
    print(f"peak parent VmRSS: {peak['parent'] / 1024:.0f} MB")
    print(f"peak live-children VmRSS: {peak['children'] / 1024:.0f} MB")
    print(f"peak concurrent tree RSS: {peak['tree'] / 1024:.0f} MB")
    print(
        f"largest single child high-water (RUSAGE_CHILDREN): "
        f"{resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024:.0f} MB"
    )
    print(
        f"parent VmRSS at end: {before / 1024:.0f} MB; after gc+malloc_trim: {after / 1024:.0f} MB"
    )
    print(
        f"process high-water ru_maxrss: "
        f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB"
    )


if __name__ == "__main__":
    main()
