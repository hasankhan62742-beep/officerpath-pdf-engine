# PPSC-66 fixture pages — provenance

Copied (not moved) from the Flutter repo's golden fixtures:
`~/workspace/officerpath-ai/test-fixtures/ppsc66/`

The Flutter repo is the source of truth and is NEVER modified by
the engine. These copies exist so M2/M3 tests can run inside the
engine repo without a cross-repo dependency at test time.

Files copied:

- `p-1.png`
- `p-2.png`
- `p-3.png`
- `p-4.png`
- `p-5.png`
- `p-6.png`
- `p-7.png`
- `table-computer-q67-81.jpg`
- `table-interjection-q230-257.jpg`

Content: 7 page renders of the PPSC Model Paper 66 (7-page
CamScanner scan, 100 MCQs, two-column, (A)-(D) 2x2) plus two
photographed answer-key tables. The pages are SCANNED images
(no text layer) — the M2 classification expectation is
`scanned` for every page.
