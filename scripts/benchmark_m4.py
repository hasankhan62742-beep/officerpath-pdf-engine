# OfficerPath AI — M4 benchmark (2026-11-21).
#
# Measures the M4 MCQ extractor (app/pipeline/extract/) over every
# golden fixture with ground truth, plus the PPSC-66 end-to-end
# Tesseract run and a clean Nastaliq CER re-measurement.
#
# ALL numbers are measured in this run, on THIS VM (labelled VM
# numbers — NOT Render numbers). Anything unmeasured is reported
# as UNVERIFIED. No PaddleOCR in this benchmark (deployment gate +
# OOM risk, ADR-005). No Gemini API calls; the stored Gemini
# reference texts are used for question COUNTS only, where noted.
#
# Usage: .venv/bin/python scripts/benchmark_m4.py
# Output: docs/benchmarks/m4-benchmark-2026-11-21.json + stdout summary.

from __future__ import annotations

import difflib
import json
import platform
import re
import resource
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "app/tests/fixtures/golden/ppsc66"
DATASET = ROOT / "app/tests/fixtures/golden/dataset.json"
NASTALIQ_DIR = ROOT / "app/tests/fixtures/golden/synthetic-nastaliq"
# The PPSC-66 PDF lives in the Flutter-side test fixtures (read-only).
PPSC66_DIR = Path.home() / "workspace/officerpath-ai/test-fixtures/ppsc66"
OUT = ROOT / "docs/benchmarks/m4-benchmark-2026-11-21.json"

SIM_THRESHOLD = 0.85


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _strip_option_marker(text: str) -> str:
    """Strip one leading option marker (``A. ``, ``(B) ``, ``a) ``, ...)
    from an option string for scorer comparison."""
    return re.sub(r"^[\(\[]?\s*[A-Da-d]\s*[\)\.\:\-]\s*", "", text.strip())


def _answer_letter(index: int) -> str | None:
    return chr(65 + index) if 0 <= index < 4 else None


def _match_pairs(detected: list[dict], gt: list[dict]) -> list[tuple[dict, dict]]:
    """Greedy best-similarity matching (number agreement when both
    have numbers, text similarity >= 0.85). Returns (det, gt) pairs."""
    used: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    for g in gt:
        best_idx: int | None = None
        best_sim = 0.0
        for i, d in enumerate(detected):
            if i in used:
                continue
            gn, dn = g.get("number"), d.get("number")
            if gn is not None and dn is not None and gn != dn:
                continue
            s = _sim(g.get("text", ""), d.get("text", ""))
            if s >= SIM_THRESHOLD and s > best_sim:
                best_sim = s
                best_idx = i
        if best_idx is not None:
            used.add(best_idx)
            pairs.append((detected[best_idx], g))
    return pairs


def _score_mcq(detected: list[dict], gt: list[dict], *, score_answers: bool) -> dict:
    """Question detection + option extraction + answer correctness."""
    pairs = _match_pairs(detected, gt)
    tp_q = len(pairs)
    fp_q = len(detected) - tp_q
    fn_q = len(gt) - tp_q
    question = _prf(tp_q, fp_q, fn_q)

    tp_o = fp_o = fn_o = 0
    for d, g in pairs:
        gopts = g.get("options") or []
        dopts = d.get("options") or []
        for gi, go in enumerate(gopts):
            # Strip a leading option marker ("A. ", "(B) ", "a) ", ...)
            # from BOTH sides before comparing: the extractor stores
            # options with their markers on some paths (pdfplumber
            # rows), the ground truth stores bare option text. Without
            # this, short options ("of" vs "A. of") score ~0.57 and
            # option recall is understated. This is scorer
            # normalisation, not extractor behaviour.
            det_opt = _strip_option_marker(dopts[gi]) if gi < len(dopts) else ""
            if gi < len(dopts) and _sim(go, det_opt) >= SIM_THRESHOLD:
                tp_o += 1
            else:
                fn_o += 1
        if len(dopts) > len(gopts):
            fp_o += len(dopts) - len(gopts)
    options = _prf(tp_o, fp_o, fn_o)

    answer: dict | None = None
    if score_answers:
        gt_with_answer = [g for _, g in pairs if g.get("answer")]
        tp_a = 0
        det_answered = 0
        for d, g in pairs:
            if not g.get("answer"):
                continue
            dl = _answer_letter(d.get("correct_index", -1))
            if dl is not None:
                det_answered += 1
                if dl == g["answer"]:
                    tp_a += 1
        answer = _prf(tp_a, det_answered - tp_a, len(gt_with_answer) - tp_a)
        answer["accuracy_on_matched_with_answer"] = (
            round(tp_a / len(gt_with_answer), 4) if gt_with_answer else None
        )
    return {
        "question_detection": question,
        "option_extraction": options,
        "answer_correctness": answer,
        "detected_total": len(detected),
        "ground_truth_total": len(gt),
        "matched": tp_q,
    }


def _score_qa(detected_qa: list[dict], gt: list[dict]) -> dict:
    """Q&A pairs: question match by text similarity, answer match by
    answer-text similarity >= 0.85 (answers are free text, no letter)."""
    pairs = _match_pairs(detected_qa, gt)
    tp_q = len(pairs)
    question = _prf(tp_q, len(detected_qa) - tp_q, len(gt) - tp_q)
    tp_a = 0
    for d, g in pairs:
        if g.get("answer") and d.get("answer") and _sim(g["answer"], d["answer"]) >= SIM_THRESHOLD:
            tp_a += 1
    gt_with_answer = [g for _, g in pairs if g.get("answer")]
    answer = _prf(tp_a, len(gt_with_answer) - tp_a, len(gt_with_answer) - tp_a)
    answer["accuracy_on_matched_with_answer"] = (
        round(tp_a / len(gt_with_answer), 4) if gt_with_answer else None
    )
    return {
        "question_detection": question,
        "option_extraction": None,
        "answer_correctness": answer,
        "detected_total": len(detected_qa),
        "ground_truth_total": len(gt),
        "matched": tp_q,
    }


def _detected_as_dicts(result) -> tuple[list[dict], list[dict]]:
    """ParseResult -> (mcq dicts, qa_pair dicts) in the scorer shape."""
    mcq = [
        {
            "number": q.number,
            "text": q.text,
            "options": list(q.options),
            "correct_index": q.correct_index,
            "page": q.page,
        }
        for q in result.questions
    ]
    # Pending questions count as detected-but-unanswered for detection
    # recall: they were found, just have no answer yet.
    for p in result.pending:
        mcq.append(
            {
                "number": p.number,
                "text": p.text,
                "options": list(p.options),
                "correct_index": -1,
                "page": p.page,
            }
        )
    qa = [
        {
            "number": p.number,
            "text": p.question,
            "options": [],
            "answer": p.answer,
            "page": p.page,
        }
        for p in result.qa_pairs
    ]
    return mcq, qa


def _lines_from_txt(path: Path) -> list[str]:
    return [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _count_numbered_starts(lines: list[str]) -> int:
    """Count lines that start a numbered question (Gemini-reference
    question-count baseline only)."""
    from app.pipeline.extract.numbers import question_number_detailed

    count = 0
    for ln in lines:
        if question_number_detailed(ln) is not None:
            count += 1
    return count


# ------------------------------------------------------------------
# Ground-truth loaders (schemas per the M4 task brief).
# ------------------------------------------------------------------


def _load_testpoint() -> tuple[list[dict], dict]:
    data = json.loads((FIX / "ground_truth_testpoint_1000.json").read_text())
    gt = [
        {
            "number": r["sr"],
            "page": r["page"],
            "text": r["question"],
            "options": [r["a"], r["b"], r["c"], r["d"]],
            "answer": r["answer"],
        }
        for r in data["rows"]
    ]
    return gt, {
        "pdf": "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        "count": data["count"],
    }


def _load_computer() -> tuple[list[dict], dict]:
    data = json.loads((FIX / "ground_truth_computer_qa.json").read_text())
    gt = [
        {
            "number": p["number"],
            "text": p["question"],
            "options": [],
            "answer": p["answer"],
            "answer_rule": p["answer_rule"],
            "flag": p["flag"],
        }
        for p in data["pairs"]
    ]
    return gt, {"pdf": "Computer_Past_Papers_2019-2025.pdf", "count": data["count"]}


def _load_ca40() -> tuple[list[dict], dict]:
    data = json.loads((FIX / "ground_truth_ca40.json").read_text())
    gt = [
        {
            "number": q["number"],
            "text": q["question"],
            "options": [q["a"], q["b"], q["c"], q["d"]],
            "answer": q["answer"],
        }
        for q in data["questions"]
    ]
    return gt, {"pdf": "ppsc-current-affairs-40-mcqs.pdf", "count": data["count"]}


def _load_urdu_noa() -> tuple[list[dict], dict]:
    data = json.loads((FIX / "ground_truth_urdu_noa.json").read_text())
    gt = [
        {
            "number": q["number"],
            "text": q["question"],
            "options": [q["a"], q["b"], q["c"], q["d"]],
            "answer": q["answer"].upper() if q.get("answer") else None,
        }
        for q in data["questions"]
    ]
    return gt, {"pdf": "PDF_Urdu_MCQs_NOA.pdf", "count": data["count"]}


def _load_ca_monthly() -> dict[str, tuple[list[dict], dict]]:
    out = {}
    for slug, pdf in [
        ("march", "Current-Affairs-March-2025-in-PDF.pdf"),
        ("april", "Current-Affairs-April-2025-in-PDF-Free-Version.pdf"),
        ("june", "Current-Affairs-June-2025-in-PDF__1.pdf"),
        ("july", "Current-Affairs-July-2025-in-PDF.pdf"),
        ("pakistan_august", "Pakistan-Current-Affairs-August-2025-in-PDF.pdf"),
    ]:
        data = json.loads((FIX / f"extracted_ca_monthly_{slug}_2025.json").read_text())
        gt = [
            {
                "number": None,  # monthly files have no printed numbers
                "index": q["index"],
                "page": q["page"],
                "text": q["question"],
                "options": [q["a"], q["b"], q["c"], q["d"]],
                "answer": None,  # ANSWERS UNKNOWN — never scored
            }
            for q in data["questions"]
        ]
        out[slug] = (gt, {"pdf": pdf, "count": data["count"]})
    return out


def _load_pak_study() -> tuple[set[int], dict]:
    data = json.loads((FIX / "extracted_pak_study_1000_ranges.json").read_text())
    numbers = set()
    for page in data["per_page"]:
        numbers.update(page["numbers"])
    return numbers, {
        "pdf": "Pak_Study_1000__MCQs_for_ETEA.pdf",
        "total_questions_found": data["total_questions_found"],
        "number_min": data["number_min"],
        "number_max": data["number_max"],
    }


# ------------------------------------------------------------------
# Fixture runs.
# ------------------------------------------------------------------


def _run_digital_pdf(pdf_name: str, source_id: str) -> dict:
    """Run extract_from_digital_pdf; return ParseResult + seconds."""
    from app.pipeline.extract.service import extract_from_digital_pdf

    pdf_bytes = (FIX / pdf_name).read_bytes()
    start = time.monotonic()
    result = extract_from_digital_pdf(pdf_bytes, source_id)
    return {"result": result, "seconds": round(time.monotonic() - start, 2)}


def _run_lines(lines: list[str], source_id: str, *, is_ocr: bool) -> dict:
    from app.pipeline.extract.service import PageLines, extract_document

    start = time.monotonic()
    result = extract_document(
        [PageLines(page_number=1, lines=lines, is_ocr=is_ocr)],
        source_document_id=source_id,
    )
    return {"result": result, "seconds": round(time.monotonic() - start, 2)}


def _score_digital_fixtures() -> dict:
    fixtures: dict = {}

    # TestPoint — Sr# table (D8 path).
    gt, meta = _load_testpoint()
    run = _run_digital_pdf(meta["pdf"], "testpoint-english-1000")
    det, _qa = _detected_as_dicts(run["result"])
    fixtures["testpoint_english_1000"] = {
        **meta,
        "kind": "digital",
        "seconds": run["seconds"],
        "metrics": _score_mcq(det, gt, score_answers=True),
        "parse_counts": _parse_counts(run["result"]),
    }

    # Computer Q&A — qa_pair path.
    gt, meta = _load_computer()
    run = _run_digital_pdf(meta["pdf"], "computer-past-papers-2019-2025")
    _mcq, qa = _detected_as_dicts(run["result"])
    fixtures["computer_past_papers_qa"] = {
        **meta,
        "kind": "digital",
        "seconds": run["seconds"],
        "metrics": _score_qa(qa, gt),
        "parse_counts": _parse_counts(run["result"]),
        "mcq_detected_also": len(_mcq),
    }

    # CA40 — standard blocks, bold answer lines.
    gt, meta = _load_ca40()
    run = _run_digital_pdf(meta["pdf"], "ppsc-ca-40-mcqs")
    det, _qa = _detected_as_dicts(run["result"])
    fixtures["ca40"] = {
        **meta,
        "kind": "digital",
        "seconds": run["seconds"],
        "metrics": _score_mcq(det, gt, score_answers=True),
        "parse_counts": _parse_counts(run["result"]),
    }

    # Urdu NOA — lowercase markers.
    gt, meta = _load_urdu_noa()
    run = _run_digital_pdf(meta["pdf"], "urdu-mcqs-noa")
    det, _qa = _detected_as_dicts(run["result"])
    fixtures["urdu_noa"] = {
        **meta,
        "kind": "digital",
        "seconds": run["seconds"],
        "metrics": _score_mcq(det, gt, score_answers=True),
        "parse_counts": _parse_counts(run["result"]),
    }

    # CA monthly — question+options only, answers UNKNOWN.
    for slug, (gt, meta) in _load_ca_monthly().items():
        run = _run_digital_pdf(meta["pdf"], f"ca-monthly-{slug}-2025")
        det, _qa = _detected_as_dicts(run["result"])
        fixtures[f"ca_monthly_{slug}_2025"] = {
            **meta,
            "kind": "digital",
            "seconds": run["seconds"],
            "metrics": _score_mcq(det, gt, score_answers=False),
            "parse_counts": _parse_counts(run["result"]),
        }

    # Pak Study — numbers only.
    gt_numbers, meta = _load_pak_study()
    run = _run_digital_pdf(meta["pdf"], "pak-study-1000-etea")
    det, _qa = _detected_as_dicts(run["result"])
    det_numbers = {d["number"] for d in det if d.get("number") is not None}
    tp = len(det_numbers & gt_numbers)
    fixtures["pak_study_1000_numbers_only"] = {
        **meta,
        "kind": "digital",
        "seconds": run["seconds"],
        "metrics": {"number_detection": _prf(tp, len(det_numbers) - tp, len(gt_numbers) - tp)},
        "parse_counts": _parse_counts(run["result"]),
        "detected_unique_numbers": len(det_numbers),
        "ground_truth_unique_numbers": len(gt_numbers),
    }
    return fixtures


def _parse_counts(result) -> dict:
    return {
        "questions": len(result.questions),
        "qa_pairs": len(result.qa_pairs),
        "pending": len(result.pending),
        "skipped": len(result.skipped),
        "excluded": len(result.excluded),
        "key_sections_found": result.key_sections_found,
        "key_entries_applied": result.key_entries_applied,
        "unmatched_key_entries": len(result.unmatched_key_entries),
        "number_gaps": len(result.number_gaps),
        "number_duplicates": len(result.number_duplicates),
        "options_complete_4_of_4": sum(1 for q in result.questions if len(q.options) == 4),
    }


def _run_synthetic() -> dict:
    dataset = json.loads(DATASET.read_text())
    entries = {e["id"]: e for e in dataset["entries"]}
    out: dict = {}
    for entry_id in ("synthetic-clean-p1", "synthetic-clean-p2"):
        entry = entries[entry_id]
        lines = [ln for ln in entry.get("lines", []) if ln.strip()]
        run = _run_lines(lines, entry_id, is_ocr=False)
        r = run["result"]
        out[entry_id] = {
            "kind": "digital",
            "expected_questions": 4,
            "seconds": run["seconds"],
            "questions": len(r.questions),
            "pending": len(r.pending),
            "options_complete_4_of_4": sum(1 for q in r.questions if len(q.options) == 4),
            "skipped": len(r.skipped),
            "excluded": len(r.excluded),
            "note": "Exact-option assertions live in test_extract_service; "
            "benchmark reports counts only.",
        }
    # Nastaliq — structure only, on the GROUND-TRUTH lines (Tesseract
    # CER ~0.59 makes extraction from Tesseract text poor by design).
    entry = entries["synthetic-nastaliq-p1"]
    lines = [ln for ln in entry.get("lines", []) if ln.strip()]
    run = _run_lines(lines, "synthetic-nastaliq-p1", is_ocr=False)
    r = run["result"]
    out["synthetic-nastaliq-p1"] = {
        "kind": "scanned_ground_truth_lines",
        "expected_questions": 4,
        "seconds": run["seconds"],
        "questions": len(r.questions),
        "pending": len(r.pending),
        "options_complete_4_of_4": sum(
            1
            for q in r.questions + [type("P", (), {"options": p.options})() for p in r.pending]
            if len(q.options) == 4
        ),
        "skipped": len(r.skipped),
        "excluded": len(r.excluded),
        "note": "Extractor on ground-truth lines only; Tesseract CER measured separately below.",
    }
    return out


def _run_stored_tesseract_scanned() -> dict:
    """PPSC-66 pages + table photos + Paper 60, from stored Tesseract
    text files (ocr-tess-p*.txt). Gemini refs give question COUNTS only."""
    from app.pipeline.extract.keys import parse_key_entries
    from app.pipeline.extract.service import PageLines, extract_document

    out: dict = {}
    pages: list = []
    for page in range(1, 8):
        tess = FIX / f"ocr-tess-p{page}.txt"
        gemini = FIX / f"ocr-p{page}.txt"
        lines = _lines_from_txt(tess)
        gemini_lines = _lines_from_txt(gemini) if gemini.exists() else []
        start = time.monotonic()
        result = extract_document(
            [PageLines(page_number=page, lines=lines, is_ocr=True)],
            source_document_id=f"ppsc66-p{page}",
        )
        out[f"ppsc66-p{page}"] = {
            "kind": "scanned_stored_tesseract",
            "seconds": round(time.monotonic() - start, 2),
            "questions": len(result.questions),
            "pending": len(result.pending),
            "options_complete_4_of_4": sum(1 for q in result.questions if len(q.options) == 4),
            "key_sections_found": result.key_sections_found,
            "key_entries_applied": result.key_entries_applied,
            "unmatched_key_entries": len(result.unmatched_key_entries),
            "gemini_reference_question_starts": _count_numbered_starts(gemini_lines),
            "note": "Gemini count is a question-count baseline only; "
            "no per-question ground truth for PPSC-66.",
        }
        pages.append(PageLines(page_number=page, lines=lines, is_ocr=True))
    # Whole-document run (key on p7 joins under the strict paper rule).
    start = time.monotonic()
    whole = extract_document(pages, source_document_id="ppsc66-stored-tesseract")
    out["ppsc66_whole_document_stored_tesseract"] = {
        "kind": "scanned_stored_tesseract",
        "seconds": round(time.monotonic() - start, 2),
        "questions": len(whole.questions),
        "pending": len(whole.pending),
        "options_complete_4_of_4": sum(1 for q in whole.questions if len(q.options) == 4),
        "key_sections_found": whole.key_sections_found,
        "key_entries_applied": whole.key_entries_applied,
        "unmatched_key_entries": whole.unmatched_key_entries,
        "number_gaps": whole.number_gaps,
        "number_duplicates": whole.number_duplicates,
    }
    # p7 key parsed standalone (compact token-stream coverage, D16).
    p7_lines = _lines_from_txt(FIX / "ocr-tess-p7.txt")
    p7_entries = parse_key_entries("\n".join(p7_lines))
    out["ppsc66_p7_key_standalone"] = {
        "kind": "scanned_stored_tesseract",
        "key_entries_parsed_from_tesseract_text": len(p7_entries),
        "key_numbers": sorted(p7_entries),
    }
    # Table photos (stored Tesseract) — counts only, no GT.
    for slug, gemini_file in [
        ("computer-q67-81", "ocr-table-computer-gemini.txt"),
        ("interjection-q230-257", "ocr-table-interjection-gemini.txt"),
    ]:
        tess = FIX / f"ocr-tess-table-{slug.split('-')[0]}.txt"
        gemini = FIX / gemini_file
        lines = _lines_from_txt(tess) if tess.exists() else []
        gemini_lines = _lines_from_txt(gemini) if gemini.exists() else []
        run = _run_lines(lines, f"ppsc66-table-{slug}", is_ocr=True)
        r = run["result"]
        out[f"ppsc66-table-{slug}"] = {
            "kind": "scanned_stored_tesseract",
            "seconds": run["seconds"],
            "questions": len(r.questions),
            "pending": len(r.pending),
            "options_complete_4_of_4": sum(1 for q in r.questions if len(q.options) == 4),
            "gemini_reference_question_starts": _count_numbered_starts(gemini_lines),
            "note": "Counts only; no per-question ground truth for the table photos.",
        }
    # Paper 60 photo — Gemini reference text, counts only (Q1–Q21 seen).
    lines = _lines_from_txt(FIX / "paper60_gemini_ocr.txt")
    run = _run_lines(lines, "paper60-photo", is_ocr=False)
    r = run["result"]
    out["paper60_photo_gemini_text"] = {
        "kind": "scanned_gemini_reference_text",
        "expected_questions": 21,
        "seconds": run["seconds"],
        "questions": len(r.questions),
        "pending": len(r.pending),
        "options_complete_4_of_4": sum(1 for q in r.questions if len(q.options) == 4),
        "note": "Extractor on the Gemini reference text (not OCR output); "
        "counts only, no per-question ground truth.",
    }
    return out


# ------------------------------------------------------------------
# PPSC-66 live end-to-end (server OCR only: Tesseract eng+urd PSM 3,
# 200 DPI render via the M2 pipeline, layout reading order).
# ------------------------------------------------------------------


def _run_ppsc66_live() -> dict:
    from app.config import Settings
    from app.pipeline.extract.keys import parse_key_entries
    from app.pipeline.extract.service import PageLines, extract_document
    from app.pipeline.interfaces import PageContext
    from app.pipeline.layout.analyzer import GeometryLayoutAnalyzer
    from app.pipeline.ocr.digital import DigitalExtractor
    from app.pipeline.ocr.tesseract import TesseractAdapter
    from app.pipeline.pdf.renderer import render_pdf_page

    settings = Settings()
    pdf_path = PPSC66_DIR / "ppsc_paper_66.pdf"
    if not pdf_path.exists():
        return {"status": "missing_pdf", "path": str(pdf_path)}
    pdf_bytes = pdf_path.read_bytes()
    adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=settings.tesseract_psm)
    info = adapter.probe()
    if not info.available:
        return {"status": "tesseract_unavailable", "reason": info.reason}
    analyzer = GeometryLayoutAnalyzer()
    digital = DigitalExtractor()
    pages: list = []
    per_page: dict = {}
    total_start = time.monotonic()
    for page in range(1, 8):
        start = time.monotonic()
        # Digital extractor first: PPSC-66 is a CamScanner scan, so
        # the text layer is expected to be empty; this is verified,
        # not assumed.
        context_d = PageContext(
            document_id=uuid.uuid4(),
            page_number=page,
            storage_path="",
            classification="scanned",
            pdf_bytes=pdf_bytes,
        )
        digital_blocks = digital.recognize(context_d)
        digital_text = "\n".join(b.text for b in digital_blocks).strip()
        rendered = render_pdf_page(pdf_bytes, page, dpi=200)
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=page,
            storage_path="",
            classification="scanned",
            image_png=rendered.png_bytes,
        )
        blocks = adapter.recognize(context)
        layout = analyzer.analyze(context, blocks)
        for region in layout.get("regions", []):
            idx = region["block_index"]
            if 0 <= idx < len(blocks):
                blocks[idx].reading_order = region["reading_order"]
        lines = []
        for block in sorted(
            blocks, key=lambda b: b.reading_order if b.reading_order is not None else 10**6
        ):
            lines.extend(ln for ln in block.text.split("\n") if ln.strip())
        gemini_lines = _lines_from_txt(FIX / f"ocr-p{page}.txt")
        per_page[f"p{page}"] = {
            "seconds": round(time.monotonic() - start, 2),
            "digital_text_chars": len(digital_text),
            "blocks": len(blocks),
            "lines": len(lines),
            "layout_column_count": layout.get("column_count"),
            "layout_tables": len(layout.get("tables", [])),
            "dpi_used": rendered.dpi_used,
            "render_width_px": rendered.width_px,
            "render_height_px": rendered.height_px,
            "gemini_reference_question_starts": _count_numbered_starts(gemini_lines),
        }
        pages.append(PageLines(page_number=page, lines=lines, is_ocr=True))
    extract_start = time.monotonic()
    result = extract_document(pages, source_document_id="ppsc-66")
    extract_seconds = round(time.monotonic() - extract_start, 2)
    # p7 key parsed standalone from the LIVE Tesseract lines.
    p7_lines = pages[6].lines
    p7_entries = parse_key_entries("\n".join(p7_lines))
    detected_numbers = sorted(
        {q.number for q in result.questions if q.number is not None}
        | {p.number for p in result.pending if p.number is not None}
    )
    numbers_1_100 = [n for n in detected_numbers if 1 <= n <= 100]
    return {
        "status": "ok",
        "engine": "tesseract",
        "engine_version": info.version,
        "languages": settings.tesseract_languages,
        "psm": settings.tesseract_psm,
        "dpi": 200,
        "total_seconds": round(time.monotonic() - total_start, 2),
        "extract_seconds": extract_seconds,
        "per_page": per_page,
        "questions": len(result.questions),
        "pending": len(result.pending),
        "questions_recovered_of_100": len(numbers_1_100),
        "detected_numbers_1_100": numbers_1_100,
        "options_complete_4_of_4": sum(1 for q in result.questions if len(q.options) == 4),
        "key_sections_found": result.key_sections_found,
        "key_entries_applied": result.key_entries_applied,
        "unmatched_key_entries": result.unmatched_key_entries,
        "p7_key_entries_parsed_live": len(p7_entries),
        "p7_key_numbers_live": sorted(p7_entries),
        "number_gaps": result.number_gaps,
        "number_duplicates": result.number_duplicates,
        "skipped": len(result.skipped),
        "excluded": len(result.excluded),
    }


# ------------------------------------------------------------------
# Nastaliq clean CER re-measurement (single process, no contention).
# ------------------------------------------------------------------


def _run_nastaliq_cer() -> dict:
    from app.config import Settings
    from app.pipeline.interfaces import PageContext
    from app.pipeline.ocr.metrics import cer
    from app.pipeline.ocr.tesseract import TesseractAdapter

    settings = Settings()
    png = (NASTALIQ_DIR / "nastaliq-p1.png").read_bytes()
    reference = (NASTALIQ_DIR / "nastaliq-p1.txt").read_text(encoding="utf-8")
    adapter = TesseractAdapter(languages=settings.tesseract_languages, psm=settings.tesseract_psm)
    info = adapter.probe()
    if not info.available:
        return {"status": "tesseract_unavailable", "reason": info.reason}
    context = PageContext(
        document_id=uuid.uuid4(),
        page_number=1,
        storage_path="",
        classification="scanned",
        image_png=png,
    )
    start = time.monotonic()
    blocks = adapter.recognize(context)
    seconds = round(time.monotonic() - start, 2)
    hypothesis = "\n".join(b.text for b in blocks)
    return {
        "status": "ok",
        "engine": "tesseract",
        "engine_version": info.version,
        "languages": settings.tesseract_languages,
        "psm": settings.tesseract_psm,
        "seconds": seconds,
        "blocks": len(blocks),
        "cer": round(cer(reference, hypothesis), 4),
        "reference_chars": len(reference),
        "hypothesis_chars": len(hypothesis),
        "note": "Clean single-process run; M4's earlier 0.5933 was a contended run.",
    }


# ------------------------------------------------------------------
# D9 / D16 measurements.
# ------------------------------------------------------------------


def _run_d9_d16() -> dict:
    from app.pipeline.extract.markers import INLINE_MARKER_RE
    from app.pipeline.extract.qa import count_answers_over_flashcard_caps

    # D9: how many Computer Q&A ground-truth answers exceed the Dart
    # flashcard caps (answer <=100 chars/line, <=2 lines, <=160 total)?
    data = json.loads((FIX / "ground_truth_computer_qa.json").read_text())
    over_count = count_answers_over_flashcard_caps(data["pairs"])
    over = [
        {"number": p["number"], "answer": p["answer"], "chars": len(p["answer"])}
        for p in data["pairs"]
        if len(p["answer"] or "") > 160
    ]
    # D16: count lines carrying >=3 inline option markers (3/4-column
    # inline options) across the digital fixtures' text layers.
    import fitz

    marker_line_counts: dict[str, int] = {}
    for pdf_name in [
        "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        "Computer_Past_Papers_2019-2025.pdf",
        "ppsc-current-affairs-40-mcqs.pdf",
        "PDF_Urdu_MCQs_NOA.pdf",
        "Current-Affairs-March-2025-in-PDF.pdf",
        "Current-Affairs-April-2025-in-PDF-Free-Version.pdf",
        "Current-Affairs-June-2025-in-PDF__1.pdf",
        "Current-Affairs-July-2025-in-PDF.pdf",
        "Pakistan-Current-Affairs-August-2025-in-PDF.pdf",
        "Pak_Study_1000__MCQs_for_ETEA.pdf",
    ]:
        doc = fitz.open(FIX / pdf_name)
        count = 0
        for page in doc:
            for ln in page.get_text().split("\n"):
                if len(INLINE_MARKER_RE.findall(ln)) >= 3:
                    count += 1
        doc.close()
        marker_line_counts[pdf_name] = count
    return {
        "d9_flashcard_caps": {
            "answers_over_caps": over_count,
            "of_total": data["count"],
            "longest_answers_over_160_chars": over[:5],
        },
        "d16_inline_option_lines": {
            "lines_with_3_or_more_inline_markers_per_pdf": marker_line_counts,
            "total": sum(marker_line_counts.values()),
            "note": "3/4-column single-line option layouts are UNVERIFIED "
            "if the total is 0 — no fixture exercises that shape.",
        },
    }


# ------------------------------------------------------------------
# Aggregation + main.
# ------------------------------------------------------------------


def _aggregate(fixtures: dict) -> dict:
    """Overall P/R/F1 across the scored MCQ fixtures (digital) and
    across all scored fixtures. CA monthly has no answers; Computer
    Q&A is scored separately (qa_pair)."""
    # Only MCQ fixtures (option_extraction is None for qa_pair).
    digital = [
        f
        for f in fixtures.values()
        if f.get("kind") == "digital"
        and f["metrics"].get("question_detection")
        and f["metrics"].get("option_extraction") is not None
    ]
    tp_q = sum(f["metrics"]["question_detection"]["tp"] for f in digital)
    fp_q = sum(f["metrics"]["question_detection"]["fp"] for f in digital)
    fn_q = sum(f["metrics"]["question_detection"]["fn"] for f in digital)
    tp_o = sum(f["metrics"]["option_extraction"]["tp"] for f in digital)
    fp_o = sum(f["metrics"]["option_extraction"]["fp"] for f in digital)
    fn_o = sum(f["metrics"]["option_extraction"]["fn"] for f in digital)
    tp_a = fp_a = fn_a = 0
    for f in digital:
        a = f["metrics"].get("answer_correctness")
        if a:
            tp_a += a["tp"]
            fp_a += a["fp"]
            fn_a += a["fn"]
    return {
        "digital_mcq_fixtures": {
            "question_detection": _prf(tp_q, fp_q, fn_q),
            "option_extraction": _prf(tp_o, fp_o, fn_o),
            "answer_correctness": _prf(tp_a, fp_a, fn_a) if tp_a + fp_a + fn_a else None,
        }
    }


def main() -> None:
    started = time.monotonic()
    report: dict = {
        "benchmark": "m4-extraction",
        "date": "2026-11-21",
        "environment": "VM numbers (this machine), NOT Render numbers",
        "python": platform.python_version(),
        "machine": f"{platform.machine()} {platform.system()}",
        "notes": [
            "Extractor: app/pipeline/extract (Dart parser port, M4).",
            "Matching: normalised text similarity >= 0.85 (difflib) AND "
            "numbers agree when both have numbers; options per-letter >= 0.85; "
            "answers by letter (answer text for qa_pair).",
            "Pending questions count as detected for question recall.",
            "No PaddleOCR (ADR-005 deployment gate + OOM risk). No Gemini API calls.",
        ],
    }

    def _safe(name: str, fn):
        print(f"== M4 benchmark: {name} ==")
        try:
            return fn()
        except Exception as exc:  # keep the rest of the run measurable
            import traceback

            traceback.print_exc()
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    def _write(section_key: str) -> None:
        # Incremental write: a late crash or runtime restart must
        # never lose measured sections (the JSON is the record).
        report["total_seconds"] = round(time.monotonic() - started, 1)
        report["peak_rss_mb"] = round(_peak_rss_mb(), 1)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    digital = _safe("digital fixtures", _score_digital_fixtures)
    report["digital_fixtures"] = digital
    _write("digital_fixtures")
    report["synthetic"] = _safe("synthetic / Nastaliq structure", _run_synthetic)
    _write("synthetic")
    report["stored_tesseract_scanned"] = _safe(
        "stored-Tesseract scanned", _run_stored_tesseract_scanned
    )
    _write("stored_tesseract_scanned")
    report["ppsc66_live_tesseract"] = _safe("PPSC-66 live end-to-end (Tesseract)", _run_ppsc66_live)
    _write("ppsc66_live_tesseract")
    report["nastaliq_cer_clean"] = _safe("Nastaliq clean CER", _run_nastaliq_cer)
    _write("nastaliq_cer_clean")
    report["d9_d16"] = _safe("D9 / D16", _run_d9_d16)
    report["overall"] = _aggregate(digital)
    _write("overall")

    # Human-readable summary.
    print(
        f"\nM4 benchmark complete in {report['total_seconds']}s, "
        f"peak RSS {report['peak_rss_mb']} MB"
    )
    print(f"JSON: {OUT}\n")
    print("--- per-fixture (digital) ---")
    for name, f in digital.items():
        m = f["metrics"]
        q = m["question_detection"]
        o = m["option_extraction"]
        a = m["answer_correctness"]
        a_txt = f" ans P/R/F1 {a['precision']}/{a['recall']}/{a['f1']}" if a else " ans N/A"
        o_txt = f"Opt P/R/F1 {o['precision']}/{o['recall']}/{o['f1']}" if o else "Opt N/A (qa_pair)"
        print(
            f"{name}: {f['seconds']}s det={m['detected_total']} gt={m['ground_truth_total']} "
            f"Q P/R/F1 {q['precision']}/{q['recall']}/{q['f1']} "
            f"{o_txt}{a_txt}"
        )
    print("\n--- overall (digital MCQ fixtures) ---")
    print(json.dumps(report["overall"], indent=2))
    p66 = report["ppsc66_live_tesseract"]
    if p66.get("status") == "ok":
        print(
            "\n--- PPSC-66 live (Tesseract) ---\n"
            f"questions={p66['questions']} pending={p66['pending']} "
            f"recovered_of_100={p66['questions_recovered_of_100']} "
            f"options_4of4={p66['options_complete_4_of_4']} "
            f"key_applied={p66['key_entries_applied']} "
            f"unmatched_key={len(p66['unmatched_key_entries'])} "
            f"p7_key_parsed={p66['p7_key_entries_parsed_live']} "
            f"total={p66['total_seconds']}s"
        )
    nc = report["nastaliq_cer_clean"]
    if nc.get("status") == "ok":
        print(
            f"\n--- Nastaliq clean ---\nCER={nc['cer']} "
            f"seconds={nc['seconds']} blocks={nc['blocks']}"
        )
    print(
        f"\nD9: {report['d9_d16']['d9_flashcard_caps']['answers_over_caps']} "
        "Computer answers over flashcard caps"
    )
    print(
        f"D16: {report['d9_d16']['d16_inline_option_lines']['total']} "
        "lines with >=3 inline option markers"
    )


if __name__ == "__main__":
    main()
