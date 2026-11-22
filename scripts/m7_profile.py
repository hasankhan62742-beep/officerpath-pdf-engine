# M7 profile (2026-11-22): find the pipeline bottleneck before
# optimising anything. PPSC-66 single-path with cProfile + stage
# timings, TestPoint digital, CA40 digital. VM numbers only.
import cProfile
import io
import pstats
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.pipeline.matching.service import parse_document_bytes  # noqa: E402

FLUTTER_FIX = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
FIX = Path("app/tests/fixtures/golden/ppsc66")


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _child_rss_mb() -> float:
    # Max RSS of any waited-for child (tesseract subprocesses).
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0


def _stage_timer():
    times: dict[str, float] = {}
    last = {"stage": None, "t": None}

    def hook(stage: str, payload: dict | None = None) -> None:
        now = time.perf_counter()
        if last["stage"] is not None and last["t"] is not None:
            times[last["stage"]] = times.get(last["stage"], 0.0) + (now - last["t"])
        last["stage"] = stage
        last["t"] = now

    return hook, times


def _run(label: str, data: bytes, filename: str, **kw) -> None:
    hook, times = _stage_timer()
    rss0 = _rss_mb()
    t0 = time.perf_counter()
    matched, report, debug = parse_document_bytes(data, "profile", on_stage=hook, **kw)
    dt = time.perf_counter() - t0
    print(
        f"== {label}: {dt:.1f}s  self-RSS {_rss_mb():.0f}MB "
        f"(+{_rss_mb() - rss0:.0f})  max-child-RSS {_child_rss_mb():.0f}MB "
        f"matched={len(matched.questions)} "
        f"answered={sum(1 for q in matched.questions if q.correct_index >= 0)}"
    )
    for stage, secs in sorted(times.items(), key=lambda kv: -kv[1]):
        print(f"    stage {stage}: {secs:.1f}s")


def main() -> None:
    p66 = (FLUTTER_FIX / "ppsc_paper_66.pdf").read_bytes()
    tp = (FLUTTER_FIX / "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf").read_bytes()
    ca40 = (FLUTTER_FIX / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()

    pr = cProfile.Profile()
    pr.enable()
    _run("PPSC-66 single-path", p66, "ppsc_paper_66.pdf")
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(18)
    print("---- cProfile top cumulative (PPSC-66) ----")
    print("\n".join(s.getvalue().splitlines()[4:24]))

    _run("TestPoint digital", tp, "testpoint.pdf")
    _run("CA40 digital", ca40, "ca40.pdf")


if __name__ == "__main__":
    main()
