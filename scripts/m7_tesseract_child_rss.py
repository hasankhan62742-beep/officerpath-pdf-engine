# Per-page tesseract child RSS on PPSC-66: which page spikes?
import resource
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from app.config import Settings  # noqa: E402
from app.pipeline.interfaces import PageContext  # noqa: E402
from app.pipeline.ocr.tesseract import TesseractAdapter  # noqa: E402
from app.pipeline.pdf.renderer import render_pdf_page  # noqa: E402

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
    import os

    me = os.getpid()
    p66 = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    settings = Settings()
    for page in range(1, 8):
        rendered = render_pdf_page(p66, page, dpi=200)
        adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=3)
        ctx = PageContext(
            document_id=uuid.uuid4(),
            page_number=page,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        stop = threading.Event()
        peak = {"child": 0}

        def sampler(stop: threading.Event = stop, peak: dict = peak) -> None:
            while not stop.wait(0.01):
                for p in _child_pids(me):
                    peak["child"] = max(peak["child"], _vmrss_kb(p))

        t = threading.Thread(target=sampler, daemon=True)
        t0 = time.monotonic()
        t.start()
        blocks = adapter.recognize(ctx)
        dt = time.monotonic() - t0
        stop.set()
        t.join(timeout=2)
        child_hw = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
        print(
            f"p{page}: {dt:.1f}s blocks={len(blocks)} "
            f"sampled-child-peak={peak['child'] / 1024:.0f}MB "
            f"child-high-water-so-far={child_hw:.0f}MB",
            flush=True,
        )


if __name__ == "__main__":
    main()
