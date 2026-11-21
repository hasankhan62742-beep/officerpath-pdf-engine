# OfficerPath AI — PDF Engine (Phase 1, M5)
# Inline-answer detector: answers given inline with the question.
#
# Three shapes, one detector:
# 1. Table Ans column (TestPoint: ``Ans`` letter per row) — the
#    letter is the answer; resolved with the M4 token resolver.
# 2. Answer lines (CA40: bold ``Correct Answer: X) ...`` lines;
#    Urdu NOA: ``(Correct)`` markers) — the line's token is the
#    answer; the trailing value is a cross-check, never the source.
# 3. Q&A pairs (Computer Past Papers: answer text directly after
#    the question, no options) — the answer IS the text; the
#    evidence carries ``answer_text`` and no option index.
#
# And the negative case this detector exists to enforce: the
# monthly Current Affairs files have NO inline marking at all.
# ``check_monthly_ca_answers`` re-measures that span-by-span
# (bold flags + colour, M4's method) and OCRs a sample of the
# embedded images — when nothing marks an answer, the verdict is
# UNKNOWN with the reason recorded, NEVER a guess from an
# explanation (M4 measured the explanation matching exactly one
# option in only 64/125, with contradictions).

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.pipeline.answers.models import AnswerEvidence, DetectorResult
from app.pipeline.extract.keys import resolve_answer_token

#: An option span in a monthly-CA PDF starts with one of these.
_OPTION_SPAN_RE = re.compile(r"^\s*([A-D])\.\s*(.+)$")


@dataclass
class MonthlyCaAnswerCheck:
    """The monthly-CA answer-marking verdict for one PDF."""

    pdf_name: str
    questions: int = 0
    option_spans_checked: int = 0
    bold_option_spans: int = 0
    coloured_option_spans: int = 0
    correct_answer_lines: int = 0
    explanation_matches_exactly_one: int = 0
    explanation_matches_none: int = 0
    explanation_matches_multiple: int = 0
    images_ocr_sampled: int = 0
    images_with_answer_text: int = 0
    image_ocr_notes: list[str] = field(default_factory=list)
    verdict: str = "unknown"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "pdf_name": self.pdf_name,
            "questions": self.questions,
            "option_spans_checked": self.option_spans_checked,
            "bold_option_spans": self.bold_option_spans,
            "coloured_option_spans": self.coloured_option_spans,
            "correct_answer_lines": self.correct_answer_lines,
            "explanation_matches_exactly_one": self.explanation_matches_exactly_one,
            "explanation_matches_none": self.explanation_matches_none,
            "explanation_matches_multiple": self.explanation_matches_multiple,
            "images_ocr_sampled": self.images_ocr_sampled,
            "images_with_answer_text": self.images_with_answer_text,
            "image_ocr_notes": list(self.image_ocr_notes),
            "verdict": self.verdict,
            "reason": self.reason,
        }


def detect_inline_answer(
    question_number: int | None,
    options: list[str],
    inline_token: str | None,
) -> AnswerEvidence | None:
    """Resolve one inline answer token (Ans-column letter, answer
    line, ``(Correct)`` marker value) against the question's
    options. Returns None when there is no token or it resolves
    to no option — the caller keeps the answer UNKNOWN."""
    if inline_token is None:
        return None
    token = inline_token.strip()
    if not token:
        return None
    resolved = resolve_answer_token(token, options)
    if resolved is None:
        return AnswerEvidence(
            detector="inline",
            question_number=question_number,
            correct_index=-1,
            confidence=0.0,
            evidence=f"inline token {token!r} resolves to no option — ignored",
            detail={"inline_token": token, "rejected": True},
        )
    return AnswerEvidence(
        detector="inline",
        question_number=question_number,
        correct_index=resolved,
        confidence=1.0,
        evidence=f"inline answer {token!r} -> ({chr(65 + resolved)})",
        detail={"inline_token": token},
    )


def detect_qa_answer(
    question_number: int | None, question: str, answer: str
) -> AnswerEvidence | None:
    """Q&A pair (no options): the text after the question IS the
    answer. Returns None when the answer text is empty — an empty
    answer is UNKNOWN, never invented."""
    if not (answer or "").strip():
        return None
    return AnswerEvidence(
        detector="inline",
        question_number=question_number,
        correct_index=-1,
        confidence=1.0,
        evidence=f"inline Q&A answer text: {answer.strip()[:60]!r}",
        answer_text=answer.strip(),
        detail={"question": question.strip()[:80]},
    )


def _option_in_explanation(option: str, explanation: str) -> bool:
    """Whole-word containment of the option text in the explanation
    (M4's statistic — noisy, never ground truth)."""
    if not option.strip():
        return False
    pattern = r"\b" + re.escape(" ".join(option.lower().split())) + r"\b"
    return re.search(pattern, " ".join(explanation.lower().split())) is not None


def check_monthly_ca_answers(
    pdf_bytes: bytes, pdf_name: str, *, ocr_images: bool = True
) -> MonthlyCaAnswerCheck:
    """Re-measure the monthly-CA answer marking for one PDF:
    span-by-span bold/colour check of every option span, a search
    for ``Correct Answer`` lines, the explanation-vs-option match
    histogram, and (unless ``ocr_images`` is False) a Tesseract
    OCR sample of the embedded images. Verdict is ``unknown``
    unless a marking mechanism is found — the explanation is a
    noisy statistic, never an answer source."""
    import fitz

    check = MonthlyCaAnswerCheck(pdf_name=pdf_name)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        questions: list[dict] = []
        current: dict | None = None
        for pno, page in enumerate(doc):
            text = page.get_text()
            check.correct_answer_lines += text.count("Correct Answer")
            d = page.get_text("dict")
            for block in d.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span["text"].strip()
                        if not span_text:
                            continue
                        is_bold = bool(span["flags"] & 16)
                        opt_m = _OPTION_SPAN_RE.match(span_text)
                        if opt_m:
                            check.option_spans_checked += 1
                            if is_bold:
                                check.bold_option_spans += 1
                            if span["color"] != 0:
                                check.coloured_option_spans += 1
                            if current is not None:
                                current["options"][opt_m.group(1)] = opt_m.group(2)
                            continue
                        if is_bold and not opt_m:
                            current = {
                                "page": pno + 1,
                                "question": span_text,
                                "options": {},
                                "explanation": "",
                            }
                            questions.append(current)
                            continue
                        if current is not None:
                            current["explanation"] = (
                                current["explanation"] + " " + span_text
                            ).strip()
        check.questions = len(questions)
        for q in questions:
            matched = [
                k
                for k in "ABCD"
                if k in q["options"] and _option_in_explanation(q["options"][k], q["explanation"])
            ]
            if len(matched) == 1:
                check.explanation_matches_exactly_one += 1
            elif len(matched) == 0:
                check.explanation_matches_none += 1
            else:
                check.explanation_matches_multiple += 1
        # Embedded-image OCR sample: first 2 images of the first 2
        # pages that carry images (news photos, not diagrams).
        # Skipped when ocr_images=False (unit tests: the span check
        # is the verdict; the image sample is benchmark work).
        sampled = 0
        for pno, page in enumerate(doc):
            if not ocr_images:
                break
            if sampled >= 4:
                break
            for img in page.get_images(full=True)[:2]:
                if sampled >= 4:
                    break
                try:
                    pix = fitz.Pixmap(doc, img[0])
                    png = pix.tobytes("png")
                except Exception:
                    continue
                sampled += 1
                check.images_ocr_sampled += 1
                text = _ocr_image_text(png)
                if re.search(r"(answer|correct|\(\s*[A-D]\s*\)\s*\*)", text, re.IGNORECASE):
                    check.images_with_answer_text += 1
                    check.image_ocr_notes.append(
                        f"page {pno + 1} image xref {img[0]}: answer-like text found: "
                        f"{text[:120]!r}"
                    )
                else:
                    check.image_ocr_notes.append(
                        f"page {pno + 1} image xref {img[0]}: no answer text "
                        f"(OCR {len(text)} chars)"
                    )
        if (
            check.bold_option_spans == 0
            and check.coloured_option_spans == 0
            and check.correct_answer_lines == 0
            and check.images_with_answer_text == 0
        ):
            check.verdict = "unknown"
            sample_note = (
                f"{check.images_with_answer_text}/{check.images_ocr_sampled} sampled "
                "images carry answer text"
                if ocr_images
                else "image OCR sample skipped (ocr_images=False)"
            )
            check.reason = (
                f"no marking mechanism: {check.option_spans_checked} option spans, "
                "0 bold, 0 coloured, 0 'Correct Answer' lines, "
                f"{sample_note}; explanation matches exactly one option in "
                f"{check.explanation_matches_exactly_one}/{check.questions} — too noisy "
                "to be an answer source."
            )
        else:
            check.verdict = "marked"
            check.reason = (
                f"marking found: {check.bold_option_spans} bold option spans, "
                f"{check.coloured_option_spans} coloured, "
                f"{check.correct_answer_lines} 'Correct Answer' lines, "
                f"{check.images_with_answer_text} sampled images with answer text."
            )
        return check
    finally:
        doc.close()


def _ocr_image_text(png_bytes: bytes) -> str:
    """Best-effort Tesseract OCR of one small embedded image. Any
    failure returns "" — a failed OCR is no evidence, never a
    fabricated empty answer."""
    try:
        import uuid

        from app.pipeline.interfaces import PageContext
        from app.pipeline.ocr.tesseract import TesseractAdapter

        adapter = TesseractAdapter(languages="eng+urd", psm=3)
        if not adapter.is_available():
            return ""
        context = PageContext(
            document_id=uuid.uuid4(),
            page_number=1,
            storage_path="",
            classification="scanned",
            image_png=png_bytes,
        )
        blocks = adapter.recognize(context)
        return "\n".join(b.text for b in blocks)
    except Exception:
        return ""


def inline_detection_to_result(
    evidences: list[AnswerEvidence | None],
) -> DetectorResult:
    """Wrap inline evidences as a DetectorResult (None entries are
    questions with no inline token — recorded as rejections only
    when the evidence says it was rejected)."""
    kept = [e for e in evidences if e is not None]
    rejected = [
        {"question_number": e.question_number, "reason": e.evidence}
        for e in kept
        if e.correct_index == -1 and not e.answer_text
    ]
    return DetectorResult(
        detector="inline",
        evidences=[e for e in kept if e.correct_index >= 0 or e.answer_text],
        rejected=rejected,
        notes=[],
    )
