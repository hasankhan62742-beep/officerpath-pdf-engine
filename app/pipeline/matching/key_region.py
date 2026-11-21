# OfficerPath AI — PDF Engine (Phase 1, M6)
# Key-region location: find WHERE the trailing answer key actually
# starts before parsing it.
#
# Why this exists (measured, M5): the live PPSC-66 key text (full
# p6+p7 OCR lines) contains Q98's explanation items BEFORE the real
# key — "1. (A) Possessed: The most suitable choice, ..." — and
# ``parse_key_entries`` keeps the FIRST occurrence, so entry 1 was
# hijacked (live key 1 FP). The explanation precedes the key; the
# key itself starts at a heading ("ANSWER KEY: Model Paper 66") and
# continues as a dense run of one-entry-per-line entries (1..78 on
# p6, 79..100 on p7) until the next paper's heading ("MODEL PAPER
# 67"). Parsing only inside the located region removes the hijack.
#
# Location methods, in order:
# 1. "heading" — a key heading line (``is_answer_key_heading`` or a
#    heading-with-remainder from ``key_heading_remainder``). The
#    region starts at the heading line, BACK-SCANNED to the first
#    line of the key's entry run: measured (M6, live PPSC-66 p6),
#    layout ordering puts the heading AFTER the key's first column,
#    so entries 1..20 precede the heading and a heading-only start
#    loses them. The back-scan walks up from the heading over
#    entry-like lines whose numbers strictly decrease going up
#    (OCR may drop entries, so any decrease counts), allowing gaps
#    of <= _BACK_MAX_GAP non-entry lines; a number that does not
#    decrease (an explanation item above the key) or a longer gap
#    ends the scan.
# 2. "dense-run" — the first run of >= 5 entry-like lines whose
#    numbers ascend consecutively (1,2,3,...) at density >= 0.8,
#    allowing gaps of <= 2 non-entry lines (subheads / wrapped
#    values). Explanation items fail this: their run is short
#    (3 items) and a number reset ends it, while a real key runs
#    1..N without a reset.
# 3. "none" — no heading and no dense run: the key region is NOT
#    located and the caller must say so, never guess.
#
# Region end: the first paper heading AFTER the start (a following
# paper, e.g. "MODEL PAPER 67"), or the end of the lines. Entries
# after the end belong to the next paper, never to this key.
# BUT a paper heading does not end the region when the key entries
# continue past it: measured (M6, live PPSC-66 p7), layout ordering
# places the "MODEL PAPER 67" heading BEFORE key entries 90..100
# (the heading is a page footer that the geometry analyser orders
# before the tail of the key). A heading ends the region only when
# the entry numbers after it do NOT continue the ascending sequence
# (a restart near 1 means the next paper's key); when they continue,
# the heading is a layout artifact and scanning continues.

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipeline.extract.keys import (
    KEY_ENTRY_START_RE,
    PAPER_HEADING_RE,
    is_answer_key_heading,
    key_heading_remainder,
    parse_key_entries,
)
from app.pipeline.extract.numbers import decode_ocr_number

#: Minimum entry-like lines in a dense run.
DENSE_MIN_ENTRY_LINES = 5
#: Maximum consecutive non-entry lines allowed inside a run
#: (key section subheads / wrapped value lines).
DENSE_MAX_GAP = 2
#: Minimum density (entry lines / span) of a qualifying run.
DENSE_MIN_DENSITY = 0.8
#: How far past a paper heading to look for the next key entry
#: when deciding whether the sequence continues past the heading.
_HEADING_PEEK_LINES = 30
#: Largest number jump that still counts as "the sequence
#: continues" past a paper heading (OCR garbles some entries).
_HEADING_MAX_JUMP = 10
#: Largest gap of consecutive non-entry lines allowed while
#: back-scanning from a key heading to the first entry of the
#: key's run. Measured (M6, live PPSC-66 p6): key entries span
#: at most ~4 lines (entry line + wrapped continuations), while
#: the explanation prose above the key is 5+ lines — so 4 keeps
#: the run and stops before the explanation. The number check
#: (strictly decreasing going up) is the primary guard; the gap
#: is secondary.
_BACK_MAX_GAP = 4


@dataclass
class KeyRegion:
    """Where the trailing key lives inside a line blob."""

    start_line: int = -1  # -1 = not located
    end_line: int = -1  # exclusive; -1 = not located
    method: str = "none"  # heading | dense-run | none
    evidence: str = ""  # heading text or density stats
    lines: list[str] = field(default_factory=list)

    @property
    def located(self) -> bool:
        return self.start_line >= 0 and self.end_line > self.start_line

    @property
    def region_text(self) -> str:
        if not self.located:
            return ""
        return "\n".join(self.lines[self.start_line : self.end_line])

    def to_dict(self) -> dict:
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "method": self.method,
            "evidence": self.evidence,
            "located": self.located,
        }


def _is_entry_like(line: str) -> int | None:
    """The entry number when the line STARTS with a key entry
    (number + separator + answer letter), else None. The match
    must start at the line start: a mid-line "1." (e.g. inside a
    sentence) is not an entry."""
    text = line.strip()
    if not text:
        return None
    match = KEY_ENTRY_START_RE.match(text)
    if match is None:
        return None
    # decode_ocr_number handles OCR-misread digits ("S" -> 5) the
    # same way the key parser does; a plain int() would drop them.
    return decode_ocr_number(match.group(1))


def _dense_run_start(lines: list[str]) -> tuple[int, str] | None:
    """First RUN of >= DENSE_MIN_ENTRY_LINES entry-like lines whose
    numbers ascend consecutively (1,2,3,...) at density >=
    DENSE_MIN_DENSITY, allowing gaps of <= DENSE_MAX_GAP non-entry
    lines (section subheads / wrapped value lines). A number that
    is not prev+1 ENDS the run and starts a new one — so a window
    straddling explanation items (1,2,3) and the real key (1..10)
    does not qualify at the explanation: the explanation run is
    only 3 long, the key run is 10 long and starts at the key."""
    run_start: int | None = None
    run_numbers: list[int] = []
    last_entry_index = -1
    gap = 0

    def _evaluate() -> tuple[int, str] | None:
        if run_start is None or len(run_numbers) < DENSE_MIN_ENTRY_LINES:
            return None
        span = last_entry_index - run_start + 1
        density = len(run_numbers) / span if span > 0 else 0.0
        if density < DENSE_MIN_DENSITY:
            return None
        return run_start, (
            f"dense key run: {len(run_numbers)} entries "
            f"({run_numbers[0]}..{run_numbers[-1]}), density {density:.2f}"
        )

    for i, line in enumerate(lines):
        number = _is_entry_like(line)
        if number is None:
            gap += 1
            if gap > DENSE_MAX_GAP:
                found = _evaluate()
                if found is not None:
                    return found
                run_start = None
                run_numbers = []
                last_entry_index = -1
                gap = 0
            continue
        if run_start is None:
            run_start, run_numbers, last_entry_index, gap = i, [number], i, 0
        elif number == run_numbers[-1] + 1:
            run_numbers.append(number)
            last_entry_index = i
            gap = 0
        else:
            found = _evaluate()
            if found is not None:
                return found
            run_start, run_numbers, last_entry_index, gap = i, [number], i, 0
    return _evaluate()


def _back_scan_start(clean: list[str], heading_at: int) -> int:
    """First line of the key's entry run, scanning upward from a
    key heading. Entry-like lines must strictly decrease going up
    (OCR may drop entries, so any decrease counts); gaps of at
    most _BACK_MAX_GAP non-entry lines are allowed. A number that
    does not decrease (an explanation item sitting above the key,
    e.g. "2. (B) Privileged" above key entry 1) or a longer gap
    ends the scan. Returns the heading itself when no entry
    precedes it."""
    start = heading_at
    last_seen: int | None = None
    gap = 0
    for i in range(heading_at - 1, -1, -1):
        number = _is_entry_like(clean[i])
        if number is None:
            gap += 1
            if gap > _BACK_MAX_GAP:
                break
            continue
        if last_seen is not None and number >= last_seen:
            break
        last_seen = number
        gap = 0
        start = i
    return start


def locate_key_region(lines: list[str]) -> KeyRegion:
    """Locate the trailing-key region inside ``lines``. Returns a
    KeyRegion with method "none" when no region can be located —
    the caller must report that, never parse the whole blob."""
    clean = [ln.rstrip() for ln in lines]
    # Method 1: key heading.
    heading_at: int | None = None
    heading_text = ""
    for i, line in enumerate(clean):
        if is_answer_key_heading(line):
            heading_at = i
            heading_text = line.strip()
            break
        _, remainder = key_heading_remainder(line)
        if remainder is not None:
            heading_at = i
            heading_text = line.strip()
            break
    start: int | None = heading_at
    method = "heading" if heading_at is not None else ""
    evidence = f"key heading: {heading_text!r}" if heading_at is not None else ""
    if heading_at is not None:
        # The heading labels the key block but is not necessarily
        # its first line in layout order (live PPSC-66: the key's
        # first column precedes the heading). Back-scan to the
        # run's first entry.
        back = _back_scan_start(clean, heading_at)
        if back < heading_at:
            evidence += f"; key run starts {heading_at - back} lines above the heading"
            start = back
    # Method 2: dense run (only when no heading was found).
    if start is None:
        found = _dense_run_start(clean)
        if found is not None:
            start, evidence = found
            method = "dense-run"
    if start is None:
        return KeyRegion(lines=clean, method="none", evidence="no key heading and no dense key run")
    # Region end: the first paper heading after the start, unless
    # the entry numbers continue past it (layout artifact — see the
    # module docstring). Scan forward tracking the last entry
    # number; at a heading, peek at the next entry-like line within
    # _HEADING_PEEK_LINES: it continues the sequence when it is
    # greater than the last number seen and within _HEADING_MAX_JUMP
    # of it (OCR can garble a few entries); a restart or a long
    # silence after the heading ends the region there.
    end = len(clean)
    last_number: int | None = None
    for i in range(start + 1, len(clean)):
        number = _is_entry_like(clean[i])
        if number is not None:
            last_number = number
            continue
        if not PAPER_HEADING_RE.match(clean[i].strip()):
            continue
        following: int | None = None
        for j in range(i + 1, min(len(clean), i + 1 + _HEADING_PEEK_LINES)):
            following = _is_entry_like(clean[j])
            if following is not None:
                break
        if (
            last_number is not None
            and following is not None
            and last_number < following <= last_number + _HEADING_MAX_JUMP
        ):
            continue
        end = i
        break
    return KeyRegion(
        start_line=start,
        end_line=end,
        method=method,
        evidence=evidence,
        lines=clean,
    )


def parse_key_entries_in_region(lines: list[str]) -> tuple[dict[int, str], KeyRegion]:
    """Locate the key region and parse entries ONLY inside it.
    Returns (entries, region). When the region is not located the
    entries are empty — never parse the whole blob."""
    region = locate_key_region(lines)
    if not region.located:
        return {}, region
    return parse_key_entries(region.region_text), region
