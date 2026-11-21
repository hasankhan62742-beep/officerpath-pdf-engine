"""Copy the PPSC-66 real fixture pages into the engine repo (read-only source).

Run from the repo root:  .venv/bin/python scripts/copy_ppsc66_fixtures.py

Copies ~/workspace/officerpath-ai/test-fixtures/ppsc66/p-1.png .. p-7.png
plus the two table photos into app/tests/fixtures/ppsc66/ and writes a
PROVENANCE.md. The Flutter repo is NEVER modified — this only reads it.
Re-running the script re-copies (overwrites the copies, not the source).
"""

from __future__ import annotations

import shutil
from pathlib import Path

SRC = Path.home() / "workspace" / "officerpath-ai" / "test-fixtures" / "ppsc66"
OUT = Path(__file__).resolve().parent.parent / "app" / "tests" / "fixtures" / "ppsc66"

FILES = [f"p-{n}.png" for n in range(1, 8)] + [
    "table-computer-q67-81.jpg",
    "table-interjection-q230-257.jpg",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in FILES:
        src = SRC / name
        if not src.exists():
            print(f"MISSING (skipped): {src}")
            continue
        shutil.copyfile(src, OUT / name)
        copied.append(name)
    (OUT / "PROVENANCE.md").write_text(
        "# PPSC-66 fixture pages — provenance\n\n"
        "Copied (not moved) from the Flutter repo's golden fixtures:\n"
        "`~/workspace/officerpath-ai/test-fixtures/ppsc66/`\n\n"
        "The Flutter repo is the source of truth and is NEVER modified by\n"
        "the engine. These copies exist so M2/M3 tests can run inside the\n"
        "engine repo without a cross-repo dependency at test time.\n\n"
        "Files copied:\n\n" + "".join(f"- `{name}`\n" for name in copied) + "\n"
        "Content: 7 page renders of the PPSC Model Paper 66 (7-page\n"
        "CamScanner scan, 100 MCQs, two-column, (A)-(D) 2x2) plus two\n"
        "photographed answer-key tables. The pages are SCANNED images\n"
        "(no text layer) — the M2 classification expectation is\n"
        "`scanned` for every page.\n"
    )
    print(f"copied {len(copied)} files to {OUT}")


if __name__ == "__main__":
    main()
