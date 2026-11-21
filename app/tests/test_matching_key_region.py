# OfficerPath AI — PDF Engine (Phase 1, M6)
# Key-region location tests. The live case is the real PPSC-66
# reference text: Q98's explanation items precede the real key,
# and the M5 detector's whole-blob parse let "1. (A) Possessed"
# hijack entry 1 (1 FP). Parsing only inside the located region
# must remove the hijack.

from pathlib import Path

from app.pipeline.matching.key_region import (
    locate_key_region,
    parse_key_entries_in_region,
)

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"


def _ppsc66_key_lines() -> list[str]:
    """Full p6+p7 reference lines — the same blob the M5 live run
    parsed whole (and got the entry-1 FP from)."""
    p6 = (FIX / "ocr-p6.txt").read_text(encoding="utf-8").splitlines()
    p7 = (FIX / "ocr-p7.txt").read_text(encoding="utf-8").splitlines()
    return p6 + p7


def test_ppsc66_region_found_by_heading() -> None:
    region = locate_key_region(_ppsc66_key_lines())
    assert region.located
    assert region.method == "heading"
    assert "ANSWER KEY" in region.evidence


def test_ppsc66_entry_1_is_the_key_not_the_explanation() -> None:
    entries, region = parse_key_entries_in_region(_ppsc66_key_lines())
    assert region.located
    # The real key entry 1 is "(B) Broke out" — the explanation's
    # "(A) Possessed" must NOT win (M5 live FP).
    assert entries[1].startswith("(B)")
    assert "Possessed" not in entries[1]


def test_ppsc66_region_parses_all_100_entries() -> None:
    entries, _ = parse_key_entries_in_region(_ppsc66_key_lines())
    assert sorted(entries) == list(range(1, 101))
    assert entries[98].startswith("(A)")
    assert entries[100].startswith("(C)")


def test_ppsc66_region_ends_before_paper_67() -> None:
    region = locate_key_region(_ppsc66_key_lines())
    tail = region.lines[region.end_line : region.end_line + 3]
    assert any("MODEL PAPER 67" in ln for ln in tail)


def test_live_ppsc66_region_starts_at_first_key_entry() -> None:
    """Live Tesseract lines (PSM 3, layout-ordered, 2026-11-22):
    the key's first column (entries 1..20) precedes the heading
    in layout order, so a heading-only start would lose them.
    The back-scan must start at entry 1 — and still exclude the
    explanation items above it."""
    lines = (FIX / "ocr-live-p6p7.txt").read_text(encoding="utf-8").splitlines()
    region = locate_key_region(lines)
    assert region.located
    assert region.method == "heading"
    assert region.start_line == 31
    assert lines[region.start_line].startswith("1. (B) Broke out")
    entries, _ = parse_key_entries_in_region(lines)
    assert entries[1].startswith("(B)")
    assert "Possessed" not in entries[1]
    # The real key entries 97/98 (not the question stems, which
    # the whole-blob parse kept first and could not resolve).
    assert entries[97].startswith("(B)")
    assert entries[98].startswith("(A)")
    # 93 entries parsed — the same count as the whole-blob parse,
    # minus the two explanation hijacks, plus the real 97/98.
    assert len(entries) == 93


def test_heading_region_starts_at_entries_before_heading() -> None:
    """Synthetic layout-order case: key entries 1..3 sit ABOVE
    the heading, with an explanation item further above them
    (separated by prose). The region must start at entry 1 and
    exclude the explanation."""
    lines = [
        "98. Pick out the most effective word.",
        "(A) Possessed",
        "Explanation:",
        "1. (A) Possessed: the most suitable choice, as it",
        "highlights Macbeth's inherent qualities.",
        "2. (B) Privileged: refers to external advantages.",
        "English Grammar",
        "1. (B) Broke out",
        "2. (A) Are we being blamed",
        "3. (B) Neat and clean",
        "ANSWER KEY: Model Paper 66",
        "Vocabulary",
        "4. (A) An/the",
        "5. (B) Deceive",
    ]
    region = locate_key_region(lines)
    assert region.located
    assert region.start_line == 7
    entries, _ = parse_key_entries_in_region(lines)
    assert entries[1].startswith("(B)")
    assert sorted(entries) == [1, 2, 3, 4, 5]


def test_region_end_skips_heading_when_sequence_continues() -> None:
    """A paper heading does NOT end the region when the key
    entries continue past it (live PPSC-66 p7: layout ordering
    puts \"MODEL PAPER 67\" before key entries 90..100)."""
    lines = [
        "ANSWER KEY: Model Paper 66",
        "1. (B) Broke out",
        "2. (A) Are we being blamed",
        "3. (B) Neat and clean",
        "MODEL PAPER 67",
        "4. (A) An/the",
        "5. (B) Deceive",
        "6. (A) Refreshing",
    ]
    region = locate_key_region(lines)
    assert region.located
    assert region.end_line == len(lines)
    entries, _ = parse_key_entries_in_region(lines)
    assert sorted(entries) == [1, 2, 3, 4, 5, 6]


def test_region_end_stops_at_heading_when_sequence_restarts() -> None:
    """...but a paper heading DOES end the region when the entry
    numbers restart after it (the next paper's key)."""
    lines = [
        "ANSWER KEY: Model Paper 66",
        "1. (B) Broke out",
        "2. (A) Are we being blamed",
        "3. (B) Neat and clean",
        "MODEL PAPER 67",
        "1. (C) Something else",
        "2. (D) Another answer",
    ]
    region = locate_key_region(lines)
    assert region.located
    assert region.end_line == 4
    entries, _ = parse_key_entries_in_region(lines)
    assert sorted(entries) == [1, 2, 3]


def test_dense_run_without_heading() -> None:
    lines = [
        "Some prose about the paper.",
        "1. (A) Possessed: a long explanation of why this is the answer, with prose.",
        "2. (B) Privileged: more explanation prose here.",
        "Hence this option is less appropriate.",
        "3. (C) Empowered: yet more explanation prose.",
        "Summary: the best choice is Possessed.",
        "1. (B) Broke out",
        "2. (A) Are we being blamed",
        "3. (B) Neat and clean",
        "4. (A) An/the",
        "5. (B) Deceive",
        "6. (A) Refreshing",
        "7. (C) Goose-Geese",
        "8. (D) None of these",
        "9. (C) Bitter/ourselves",
        "10. (A) Work",
    ]
    region = locate_key_region(lines)
    assert region.located
    assert region.method == "dense-run"
    entries, _ = parse_key_entries_in_region(lines)
    assert entries[1].startswith("(B)")
    assert sorted(entries) == list(range(1, 11))


def test_no_region_when_no_heading_and_no_dense_run() -> None:
    lines = [
        "1. (A) Possessed: a long explanation of why this is the answer.",
        "Some prose in between.",
        "2. (B) Privileged: more explanation prose here.",
        "And a summary line.",
    ]
    region = locate_key_region(lines)
    assert not region.located
    assert region.method == "none"
    entries, _ = parse_key_entries_in_region(lines)
    assert entries == {}


def test_empty_lines_have_no_region() -> None:
    assert not locate_key_region([]).located
    assert parse_key_entries_in_region([])[0] == {}
