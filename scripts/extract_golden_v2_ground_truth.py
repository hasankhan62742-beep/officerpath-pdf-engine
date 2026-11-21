"""M4 golden dataset v2 — ground-truth extraction (programmatic only).

Run from the repo root:  .venv/bin/python scripts/extract_golden_v2_ground_truth.py

Extracts, from the digital text layer of the new v2 fixtures (copies in
app/tests/fixtures/golden/ppsc66/), WITHOUT hand-typing any answer:

- TestPoint 1000 MCQs: pdfplumber table rows (Sr#, question, A-D, Ans).
- Computer Past Papers 2019-2025: (number, question, answer) Q&A pairs;
  the answer is the text after "?" (fallback: after ":" / after last ".").
- PPSC Current Affairs 40 MCQs: (number, question, A-D, answer) from the
  bold "Correct Answer: X) ..." lines in the text layer.
- Monthly CA PDFs (mcqsplanet.com, Mar/Apr/Jun/Jul/Aug 2025): question +
  options + explanation ONLY. The answer-marking mechanism was checked
  span-by-span (bold flags + colour): no option is ever bold or coloured
  and no "Correct Answer" line exists, so answers are UNKNOWN here. The
  script records, per question, which option texts occur in the
  explanation as a (noisy) statistic — NOT as ground truth.
- Urdu MCQs (NOA): (number, question, a-d, answer) — answers ARE marked
  inline with "(Correct)" in the text layer.
- Pak Study 1000 (ETEA): question numbers per page range only; the file
  carries no answer marking in its text layer (checked).

Every output JSON carries a "count" measured by this script. Never edit
the counts by hand; re-run the script instead.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
G = ROOT / "app" / "tests" / "fixtures" / "golden" / "ppsc66"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _write(name: str, payload: dict) -> Path:
    path = G / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- TestPoint
def extract_testpoint() -> dict:
    path = G / "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf"
    rows: list[dict] = []
    seen: dict[int, int] = {}
    bad_ans = 0
    restarts = 0
    prev_last: int | None = None
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            page_srs: list[int] = []
            for table in page.extract_tables() or []:
                for cells in table:
                    if len(cells) < 7:
                        continue
                    sr_raw = _clean(cells[0])
                    if not sr_raw.isdigit():
                        continue
                    sr = int(sr_raw)
                    ans = _clean(cells[6])
                    opts = []
                    for col in cells[2:6]:
                        opts.append(re.sub(r"^[A-D]\.\s*", "", _clean(col)))
                    if ans not in ("A", "B", "C", "D"):
                        bad_ans += 1
                        continue
                    seen[sr] = seen.get(sr, 0) + 1
                    page_srs.append(sr)
                    rows.append(
                        {
                            "sr": sr,
                            "page": pno,
                            "question": _clean(cells[1]),
                            "a": opts[0],
                            "b": opts[1],
                            "c": opts[2],
                            "d": opts[3],
                            "answer": ans,
                        }
                    )
            if page_srs and prev_last is not None and min(page_srs) < prev_last:
                restarts += 1
            if page_srs:
                prev_last = max(page_srs)
    nums = [r["sr"] for r in rows]
    # Sr# restarts per topic section (Prepositions, Synonyms, ...), so it is
    # NOT a global 1..1000 sequence: report the occurrence distribution.
    dist: dict[str, int] = {}
    for _n, c in seen.items():
        dist[str(c)] = dist.get(str(c), 0) + 1
    payload = {
        "source": "ppsc66/English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        "extraction": "pdfplumber table cells; columns Sr# | Question | A | B | C | D | Ans; "
        "rows kept only when Sr# is an integer and Ans is a single letter A-D.",
        "count": len(rows),
        "sr_min": min(nums) if nums else None,
        "sr_max": max(nums) if nums else None,
        "sr_numbering": "RESTARTS per topic section (Prepositions, Synonyms, ...): Sr# is "
        "NOT globally unique — key rows by (page, sr). Do NOT claim a 1..1000 sequence.",
        "sr_occurrence_distribution": dist,
        "sr_values_occurring_more_than_once": sum(1 for c in seen.values() if c > 1),
        "pages_where_numbering_restarts": restarts,
        "rows_with_non_letter_ans_skipped": bad_ans,
        "rows": rows,
    }
    _write("ground_truth_testpoint_1000.json", payload)
    print(
        f"testpoint: {len(rows)} rows, sr {payload['sr_min']}..{payload['sr_max']}, "
        f"occurrence_dist={dist}, restarts={restarts}, bad_ans_skipped={bad_ans}"
    )
    return payload


# ------------------------------------------------------- Computer past papers
def _split_qa(number: int, chunk: str) -> dict:
    """Split one numbered chunk into question/answer by the file's own
    punctuation. Attempts in order, each accepted only if it yields a
    non-empty answer:
      1. first '?' — answer is the text after it; if empty, the answer sits
         before the '?' after a ':' (e.g. "...Hosts: SMTP?").
      2. first ':' — but only when the text before it contains a space, so
         a token-internal colon ("B2:B6 ...") is not mistaken for one.
      3. first ';' — e.g. "...Different Parts; Power Supply"; rejected when
         the ';' is the last character (Q297's answer is "Ctrl+Shift+;").
      4. last '.' — e.g. "...Bits. 8".
    Otherwise the answer is not separable from the text layer (recorded as
    empty with rule "unknown"; never invented)."""
    chunk = _clean(chunk)
    flag = None
    q, a, rule = chunk, "", "unknown"
    if "?" in chunk:
        q1, a1 = chunk.split("?", 1)
        q1, a1 = q1.strip() + "?", a1.strip()
        if a1:
            q, a, rule = q1, a1, "question_mark"
        elif ":" in q1:
            q2, a2 = q1[:-1].rsplit(":", 1)
            q, a, rule = q2.strip(), a2.strip(), "colon_before_question_mark"
    if rule == "unknown" and ":" in chunk:
        q1, a1 = chunk.split(":", 1)
        if " " in q1.strip() and a1.strip():
            q, a, rule = q1.strip(), a1.strip(), "colon"
    if rule == "unknown" and ";" in chunk:
        q1, a1 = chunk.split(";", 1)
        if a1.strip():
            q, a, rule = q1.strip(), a1.strip(), "semicolon"
    if rule == "unknown" and "." in chunk:
        q1, a1 = chunk.rsplit(".", 1)
        if a1.strip():
            q, a, rule = q1.strip() + ".", a1.strip(), "final_period"
    if re.match(r"^\d+\b", q):
        # Q10's leading "15" looks like a stray source number; Q67/Q469/Q630
        # leading numbers are part of the question text ("1024 Kilobytes...",
        # "8/9 Write...", "1000 Million Bytes..."). Flagged, not removed.
        flag = "question_starts_with_number"
    return {"number": number, "question": q, "answer": a, "answer_rule": rule, "flag": flag}


def extract_computer_qa() -> dict:
    path = G / "Computer_Past_Papers_2019-2025.pdf"
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    # Split on "N. " markers at line starts. No whitespace is required after
    # the period: the source also writes "879.--------Function..." and
    # '900."Foxpro" Is : ...'. Line-start anchoring keeps "4.7 GB" (mid-line)
    # and similar decimals out.
    parts = re.split(r"(?m)^(\d+)\.\s*", text)
    # parts: [preamble, "1", chunk1, "2", chunk2, ...]
    pairs: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        pairs.append(_split_qa(int(parts[i]), parts[i + 1]))
    nums = [p["number"] for p in pairs]
    gaps = [n for n in range(min(nums), max(nums) + 1) if n not in set(nums)] if nums else []
    dups = sorted({n for n in nums if nums.count(n) > 1})
    empty = [p["number"] for p in pairs if not p["answer"]]
    flagged = [p["number"] for p in pairs if p["flag"]]
    short_q = [p["number"] for p in pairs if len(p["question"]) < 12]
    payload = {
        "source": "ppsc66/Computer_Past_Papers_2019-2025.pdf",
        "extraction": "PyMuPDF text layer, split on line-start 'N. ' markers; answer = "
        "text after '?' (fallback: ':' with a space before it, ';', last '.'); "
        "each split accepted only with a non-empty answer. No options "
        "exist in this file; the answer sits right after the question. "
        "Duplicate numbers 643/644 are IN THE SOURCE (two different questions "
        "share each number); numbers 670 and 860 do not occur in the text layer.",
        "count": len(pairs),
        "number_min": min(nums) if nums else None,
        "number_max": max(nums) if nums else None,
        "gaps": gaps,
        "duplicates": dups,
        "pairs_with_empty_answer": empty,
        "flagged_pairs": flagged,
        "pairs_with_very_short_question": short_q,
        "pairs": pairs,
    }
    _write("ground_truth_computer_qa.json", payload)
    print(
        f"computer_qa: {len(pairs)} pairs, {payload['number_min']}..{payload['number_max']}, "
        f"gaps={gaps}, dups={dups}, empty_answer={empty}, flagged={flagged}, short_q={short_q}"
    )
    return payload


# ------------------------------------------------------------ CA 40 (explicit)
def extract_ca40() -> dict:
    path = G / "ppsc-current-affairs-40-mcqs.pdf"
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    pattern = re.compile(
        r"(?m)^(\d+)\.\s+(.*?)\nA\)\s*(.*?)\nB\)\s*(.*?)\nC\)\s*(.*?)\nD\)\s*(.*?)\n"
        r"Correct Answer:\s*([A-D])\)\s*(.*?)(?=\n\d+\.\s|\Z)",
        re.DOTALL,
    )
    questions: list[dict] = []
    mismatched = []
    for m in pattern.finditer(text):
        num = int(m.group(1))
        opts = [_clean(m.group(i)) for i in (3, 4, 5, 6)]
        ans = m.group(7)
        # The captured answer text runs on into the next section header /
        # page footer ("... | 40 MCQs Page 2", "Note: ..."), so take the
        # option text that is a prefix of it — the Correct Answer line
        # repeats the option verbatim.
        ans_raw = _clean(m.group(8))
        prefix = [o for o in opts if ans_raw.startswith(o)]
        if len(prefix) == 1:
            ans_text = prefix[0]
        else:
            ans_text = ans_raw
            mismatched.append(num)
        questions.append(
            {
                "number": num,
                "question": _clean(m.group(2)),
                "a": opts[0],
                "b": opts[1],
                "c": opts[2],
                "d": opts[3],
                "answer": ans,
                "answer_text": ans_text,
            }
        )
    nums = [q["number"] for q in questions]
    payload = {
        "source": "ppsc66/ppsc-current-affairs-40-mcqs.pdf",
        "extraction": "PyMuPDF text layer; answer from the bold 'Correct Answer: X) ...' "
        "line after each question's four options.",
        "count": len(questions),
        "number_min": min(nums) if nums else None,
        "number_max": max(nums) if nums else None,
        "answer_text_mismatches": mismatched,
        "questions": questions,
    }
    _write("ground_truth_ca40.json", payload)
    print(
        f"ca40: {len(questions)} questions, {payload['number_min']}..{payload['number_max']}, "
        f"answer_text_mismatches={mismatched}"
    )
    return payload


# ------------------------------------------------------- Monthly CA (unknown)
def _option_in_explanation(option: str, explanation: str) -> bool:
    opt = _clean(option).lower()
    if not opt:
        return False
    # Whole-phrase match with word boundaries; short numerics need the
    # boundary so "5" does not match inside "15".
    pattern = r"(?<!\w)" + re.escape(opt) + r"(?!\w)"
    return re.search(pattern, _clean(explanation).lower()) is not None


def extract_monthly_ca(fname: str, out_name: str) -> dict:
    path = G / fname
    doc = fitz.open(path)
    questions: list[dict] = []
    option_spans_checked = 0
    bold_or_coloured_options = 0
    for pno, page in enumerate(doc, start=1):
        spans = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans.extend(line["spans"])
        current: dict | None = None
        for span in spans:
            text = span["text"].strip()
            if not text or text == "Mcqsplanet.com":
                continue
            is_bold = bool(span["flags"] & 16)
            opt_m = re.match(r"^([A-D])\.\s+(.*)$", text, re.DOTALL)
            if is_bold and not opt_m:
                # New question starts (bold stem, possibly multi-line).
                if current is not None and current["options"]:
                    questions.append(current)
                current = {"page": pno, "question": text, "options": {}, "explanation": ""}
                continue
            if current is None:
                continue
            if opt_m:
                option_spans_checked += 1
                if is_bold or span["color"] != 0:
                    bold_or_coloured_options += 1
                current["options"][opt_m.group(1)] = _clean(opt_m.group(2))
            elif current["options"]:
                current["explanation"] = _clean(current["explanation"] + " " + text)
            else:
                current["question"] = _clean(current["question"] + " " + text)
        if current is not None and current["options"]:
            questions.append(current)
    out_questions = []
    match_hist = {"0": 0, "1": 0, ">1": 0}
    for idx, q in enumerate(questions, start=1):
        opts = {k: q["options"].get(k, "") for k in "ABCD"}
        matched = [k for k in "ABCD" if _option_in_explanation(opts[k], q["explanation"])]
        key = "1" if len(matched) == 1 else ("0" if not matched else ">1")
        match_hist[key] += 1
        out_questions.append(
            {
                "index": idx,
                "page": q["page"],
                "question": q["question"],
                "a": opts["A"],
                "b": opts["B"],
                "c": opts["C"],
                "d": opts["D"],
                "explanation": q["explanation"],
                "answer": None,
                "explanation_option_matches": matched,
            }
        )
    payload = {
        "source": f"ppsc66/{fname}",
        "extraction": "PyMuPDF span dict; question = bold spans, options = "
        "'A. '...'D. ' spans, explanation = following plain spans.",
        "answer_mechanism": "UNKNOWN — verified span-by-span: no option span is "
        "bold or coloured and no 'Correct Answer' line exists; the explanation "
        "is prose that may or may not contain the answer text, so no answer "
        "is recorded. 'explanation_option_matches' is a noisy statistic only.",
        "count": len(out_questions),
        "option_spans_checked": option_spans_checked,
        "bold_or_coloured_option_spans": bold_or_coloured_options,
        "explanation_option_match_histogram": match_hist,
        "questions": out_questions,
    }
    _write(out_name, payload)
    print(
        f"{fname}: {len(out_questions)} questions, option_spans={option_spans_checked}, "
        f"bold/coloured_options={bold_or_coloured_options}, match_hist={match_hist}"
    )
    return payload


# ------------------------------------------------------------- Urdu NOA
def extract_urdu_noa() -> dict:
    path = G / "PDF_Urdu_MCQs_NOA.pdf"
    doc = fitz.open(path)
    lines = "\n".join(page.get_text() for page in doc).splitlines()
    questions: list[dict] = []
    current: dict | None = None
    current_opt: str | None = None
    # Header/footer lines repeat on every page and would otherwise be glued
    # onto the surrounding option text (the text layer is jumbled: blocks
    # appear out of reading order, e.g. Q49-54 after Q55).
    SKIP_LINES = {
        "Composed By : Ahmad Rana (ahmad_rana15@yahoo.com)",
        "National Officers Academy (NOA | CSS/PMS/PCS)",
        "History and Personalities",
        "Books and Dramas",
    }

    def flush():
        nonlocal current, current_opt
        if current is not None:
            questions.append(current)
        current, current_opt = None, None

    for raw in lines:
        line = raw.strip()
        if not line or line in SKIP_LINES or line.startswith("Composed By"):
            continue
        qm = re.match(r"^(\d+)\.\s*(.*)$", line)
        om = re.match(r"^([a-d])\.\s*(.*)$", line)
        if qm:
            flush()
            current = {
                "number": int(qm.group(1)),
                "question": _clean(qm.group(2)),
                "options": {},
                "answer": None,
            }
            current_opt = None
            continue
        if current is None:
            continue
        if om:
            current_opt = om.group(1)
            current["options"][current_opt] = _clean(om.group(2))
            continue
        # Continuation line: belongs to the current option, else the stem.
        if current_opt is not None:
            current["options"][current_opt] = _clean(current["options"][current_opt] + " " + line)
        else:
            current["question"] = _clean(current["question"] + " " + line)
    flush()
    questions.sort(key=lambda q: q["number"])
    out, no_answer, multi_answer, missing_opts = [], [], [], []
    for q in questions:
        opts = {k: q["options"].get(k, "") for k in "abcd"}
        marked = [k for k in "abcd" if "(Correct)" in opts[k]]
        for k in "abcd":
            opts[k] = _clean(opts[k].replace("(Correct)", ""))
        if len(marked) == 1:
            q["answer"] = marked[0]
        elif not marked:
            no_answer.append(q["number"])
        else:
            multi_answer.append(q["number"])
        if sorted(q["options"]) != ["a", "b", "c", "d"]:
            missing_opts.append(q["number"])
        out.append(
            {
                "number": q["number"],
                "question": q["question"],
                "a": opts["a"],
                "b": opts["b"],
                "c": opts["c"],
                "d": opts["d"],
                "answer": q["answer"],
            }
        )
    nums = [q["number"] for q in out]
    gaps = [n for n in range(min(nums), max(nums) + 1) if n not in set(nums)] if nums else []
    payload = {
        "source": "ppsc66/PDF_Urdu_MCQs_NOA.pdf",
        "extraction": "PyMuPDF text layer, line-based; options are lowercase a.-d.; "
        "the answer is the option whose text carries '(Correct)'. Questions are "
        "in English (topic: Urdu history/personalities). The text layer is "
        "JUMBLED (blocks out of reading order, e.g. Q49-54 after Q55; some "
        "'d.' markers missing, their text merged into the previous option), "
        "so questions are sorted by number here and imperfect rows are flagged "
        "below instead of silently repaired. Header/footer lines are skipped.",
        "count": len(out),
        "number_min": min(nums) if nums else None,
        "number_max": max(nums) if nums else None,
        "gaps": gaps,
        "with_answer": sum(1 for q in out if q["answer"]),
        "without_answer": no_answer,
        "multiple_marked": multi_answer,
        "missing_option_letters": missing_opts,
        "questions": out,
    }
    _write("ground_truth_urdu_noa.json", payload)
    print(
        f"urdu_noa: {len(out)} questions, {payload['number_min']}..{payload['number_max']}, "
        f"gaps={gaps}, with_answer={payload['with_answer']}, "
        f"without_answer={no_answer}, multi={multi_answer}, missing_opts={missing_opts}"
    )
    return payload


# ---------------------------------------------------------- Pak Study ranges
def extract_pak_study_ranges() -> dict:
    path = G / "Pak_Study_1000__MCQs_for_ETEA.pdf"
    doc = fitz.open(path)
    full = "\n".join(page.get_text() for page in doc)
    markers = {
        "(Correct)": full.count("(Correct)"),
        "Correct Answer": full.count("Correct Answer"),
        "Ans:": len(re.findall(r"\bAns\s*:", full)),
        "Answer:": len(re.findall(r"\bAnswer\s*:", full)),
    }
    per_page: list[dict] = []
    all_nums: list[int] = []
    zero_pages: list[int] = []
    dropped_years: list[dict] = []
    for pno, page in enumerate(doc, start=1):
        text = page.get_text()
        if not text.strip():
            zero_pages.append(pno)
        nums = sorted({int(m) for m in re.findall(r"(?m)^\s*(\d+)\.\s", text)})
        # False positive: a year at a line start mid-sentence, e.g. p147
        # "...formed in\n1946. Who was the Prime Minister...?" — drop a
        # year-like number (1900-2099) that sits far from the page's other
        # question numbers, and record it instead of silently deleting it.
        if len(nums) > 1:
            others = [n for n in nums if not (1900 <= n <= 2099)]
            for n in [n for n in nums if 1900 <= n <= 2099]:
                if all(abs(n - o) > 10 for o in others):
                    nums.remove(n)
                    dropped_years.append({"page": pno, "number": n})
        if nums:
            all_nums.extend(nums)
        per_page.append(
            {
                "page": pno,
                "numbers": nums,
                "min": min(nums) if nums else None,
                "max": max(nums) if nums else None,
            }
        )
    gaps = (
        [n for n in range(min(all_nums), max(all_nums) + 1) if n not in set(all_nums)]
        if all_nums
        else []
    )
    dups = sorted({n for n in all_nums if all_nums.count(n) > 1})
    payload = {
        "source": "ppsc66/Pak_Study_1000__MCQs_for_ETEA.pdf",
        "extraction": "PyMuPDF text layer; per page, question numbers matching "
        "line-start 'N. ' markers. No answers extracted: the text layer carries "
        "no answer marking (marker counts below).",
        "pages": len(doc),
        "zero_char_pages": zero_pages,
        "total_questions_found": len(all_nums),
        "number_min": min(all_nums) if all_nums else None,
        "number_max": max(all_nums) if all_nums else None,
        "gaps": gaps,
        "duplicates": dups,
        "answer_marker_counts_in_text_layer": markers,
        "false_positive_year_markers_dropped": dropped_years,
        "per_page": per_page,
    }
    _write("extracted_pak_study_1000_ranges.json", payload)
    print(
        f"pak_study: {len(doc)} pages, zero_char={zero_pages}, "
        f"questions={len(all_nums)}, {payload['number_min']}..{payload['number_max']}, "
        f"gaps={gaps}, dups={dups}, markers={markers}, dropped_years={dropped_years}"
    )
    return payload


def main() -> None:
    extract_testpoint()
    extract_computer_qa()
    extract_ca40()
    monthly_files = [
        ("Current-Affairs-March-2025-in-PDF.pdf", "extracted_ca_monthly_march_2025.json"),
        (
            "Current-Affairs-April-2025-in-PDF-Free-Version.pdf",
            "extracted_ca_monthly_april_2025.json",
        ),
        ("Current-Affairs-June-2025-in-PDF__1.pdf", "extracted_ca_monthly_june_2025.json"),
        ("Current-Affairs-July-2025-in-PDF.pdf", "extracted_ca_monthly_july_2025.json"),
        (
            "Pakistan-Current-Affairs-August-2025-in-PDF.pdf",
            "extracted_ca_monthly_pakistan_august_2025.json",
        ),
    ]
    for fname, out in monthly_files:
        extract_monthly_ca(fname, out)
    extract_urdu_noa()
    extract_pak_study_ranges()
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
