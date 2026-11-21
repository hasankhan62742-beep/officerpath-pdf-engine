# Golden dataset v1 — PPSC-66 reference texts (copies)

Copied (not moved) from the Flutter repo's golden fixtures:
`~/workspace/officerpath-ai/test-fixtures/ppsc66/`

These are GEMINI OCR OUTPUT (model gemini-3.5-flash-lite, the
app's own prompt), not hand-verified ground truth — except
p-1, which was hand-verified against the page image in M3
(see dataset.json). The Flutter repo is the source of truth
and is NEVER modified by the engine.

Files copied:

- `ocr-p1.txt`
- `ocr-p2.txt`
- `ocr-p3-a.txt`
- `ocr-p3-bL1.txt`
- `ocr-p3-bL2a.txt`
- `ocr-p3-bL2b.txt`
- `ocr-p3-bR.txt`
- `ocr-p3-q2.txt`
- `ocr-p3-top.txt`
- `ocr-p3.txt`
- `ocr-p4.txt`
- `ocr-p5.txt`
- `ocr-p6.txt`
- `ocr-p7.txt`
- `ocr-table-computer-gemini.txt`
- `ocr-table-interjection-gemini.txt`
- `ocr-tess-p1.txt`
- `ocr-tess-p2.txt`
- `ocr-tess-p3.txt`
- `ocr-tess-p4.txt`
- `ocr-tess-p5.txt`
- `ocr-tess-p6.txt`
- `ocr-tess-p7.txt`
- `ocr-tess-table-computer.txt`
- `ocr-tess-table-interjection.txt`
- `paper60_gemini_ocr.txt`
- `table-interjection-q230-257-resent-20261121.jpg`
- `table-computer-q67-81-resent-20261121.jpg`
- `ppsc-current-affairs-40-mcqs.pdf`
- `Current-Affairs-March-2025-in-PDF.pdf`
- `Current-Affairs-April-2025-in-PDF-Free-Version.pdf`
- `Current-Affairs-June-2025-in-PDF__1.pdf`
- `Current-Affairs-July-2025-in-PDF.pdf`
- `Pakistan-Current-Affairs-August-2025-in-PDF.pdf`
- `English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf`
- `Computer_Past_Papers_2019-2025.pdf`
- `PDF_Urdu_MCQs_NOA.pdf`
- `Pak_Study_1000__MCQs_for_ETEA.pdf`
- `Science_test_NOA.pdf`
- `Math_test_NOA.pdf`
- `Past_Paper_Assistant__S_GAD.pdf`
- `Capsule_of_GK.pdf`
- `3000B.c_to_2023_History_Notes_by_gkwithadnan.pdf`
- `Pak_Affairs_by_CSPs.pdf`

## Golden dataset v2 (M4, 2026-11-21) — added fixtures

The 18 v2 files above (re-sent table photos, monthly Current
Affairs PDFs, TestPoint 1000, Computer past papers, Urdu NOA,
Pak Study 1000, scanned NOA tests, Capsule of GK, History notes,
Pak Affairs notes) were copied md5-verified from the same source
folder. Ground truth for the digital ones was extracted
programmatically — see scripts/extract_golden_v2_ground_truth.py
and the ppsc66/ground_truth_*.json / extracted_*.json files.
