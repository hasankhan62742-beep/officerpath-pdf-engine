# OfficerPath AI — PDF Engine (Phase 1, M6)
# Per-document report: counts, per-detector contribution,
# confidence distribution, pending/unknown items with reasons, and
# the evidence trail per answered question. JSON (machine) + markdown
# (human). Nothing is summarised away: the pending list carries its
# reasons, and every answered question keeps its evidence.

from __future__ import annotations

from collections import Counter

from app.pipeline.matching.calibration import BUCKETS
from app.pipeline.matching.models import MatchedDocument


def build_document_report(
    matched: MatchedDocument,
    *,
    document_label: str = "",
    calibration: dict | None = None,
    promotion: dict | None = None,
    key_region: dict | None = None,
) -> dict:
    """Build the structured per-document report from a matched
    document. All counts are computed from the matched data — the
    report never re-derives them from anywhere else."""
    by_source: Counter = Counter()
    for question in matched.questions:
        if question.status == "answered":
            by_source[question.answer_source or "unknown"] += 1
    by_status: Counter = Counter(q.status for q in matched.questions)
    confidence_buckets: Counter = Counter()
    for question in matched.questions:
        if question.status != "answered":
            continue
        for low, high, label in BUCKETS:
            if label == "1.0":
                if question.confidence == 1.0:
                    confidence_buckets[label] += 1
                continue
            if low <= question.confidence < high:
                confidence_buckets[label] += 1
                break
    pending_items = [
        {
            "number": p.get("number"),
            "text": (p.get("text") or "")[:120],
            "reason": p.get("reason", ""),
            "page": p.get("page", 0),
        }
        for p in matched.pending
    ]
    unknown_items = [
        {
            "number": q.number,
            "text": q.text[:120],
            "reason": "no detector fired",
            "page": q.page,
        }
        for q in matched.questions
        if q.status == "unknown"
    ]
    error_issues = [i for i in matched.validation_issues if i.code != "missing-answer"]
    report = {
        "document": document_label,
        "counts": {
            "questions": len(matched.questions),
            "answered": matched.answered,
            "unknown": matched.unknown,
            "pending": len(matched.pending),
            "qa_pairs": len(matched.qa_pairs),
            "duplicates": sum(1 for q in matched.questions if q.duplicate),
            "conflicts": sum(1 for q in matched.questions if q.conflicts),
            "validation_errors": len(error_issues),
            "validation_issues_total": len(matched.validation_issues),
        },
        "by_status": dict(by_status),
        "by_answer_source": dict(by_source),
        "confidence_distribution": {
            label: confidence_buckets.get(label, 0) for _, _, label in BUCKETS
        },
        "pending": pending_items,
        "unknown": unknown_items,
        "validation_issues": [i.to_dict() for i in matched.validation_issues],
        "promotion": promotion or dict(matched.promotion),
        "calibration": calibration,
        "key_region": key_region,
        "notes": list(matched.notes),
        "evidence_trail": [
            {
                "number": q.number,
                "correct_letter": q.correct_letter,
                "source": q.answer_source,
                "confidence": q.confidence,
                "verified": q.verified,
                "evidences": q.evidences,
            }
            for q in matched.questions
            if q.status == "answered"
        ],
    }
    return report


def report_to_markdown(report: dict) -> str:
    """Render the structured report as markdown."""
    counts = report["counts"]
    lines = [
        f"# Extraction report — {report.get('document') or 'document'}",
        "",
        "## Counts",
        "",
        f"- Questions: {counts['questions']} (answered {counts['answered']}, "
        f"unknown {counts['unknown']}, pending {counts['pending']})",
        f"- Q&A pairs: {counts['qa_pairs']}",
        f"- Duplicates: {counts['duplicates']}, conflicts: {counts['conflicts']}",
        f"- Validation errors: {counts['validation_errors']} "
        f"(total issues {counts['validation_issues_total']})",
        "",
        "## Answers by source",
        "",
    ]
    for source, n in sorted(report["by_answer_source"].items()):
        lines.append(f"- {source}: {n}")
    lines += ["", "## Confidence distribution (answered)", ""]
    for label, n in report["confidence_distribution"].items():
        lines.append(f"- {label}: {n}")
    if report["promotion"]:
        promo = report["promotion"]
        lines += [
            "",
            "## Promotion",
            "",
            f"- Promoted: {promo.get('promoted_count', 0)} ({promo.get('promoted', [])})",
            f"- Skipped: {promo.get('skipped_count', 0)}",
        ]
        for skipped in promo.get("skipped", [])[:20]:
            lines.append(f"  - Q{skipped.get('number')}: {skipped.get('reason')}")
    if report["pending"]:
        lines += ["", "## Still pending", ""]
        for item in report["pending"]:
            lines.append(f"- Q{item.get('number')}: {item.get('reason')} (p{item.get('page')})")
    if report["unknown"]:
        lines += ["", "## Unknown answers", ""]
        for item in report["unknown"]:
            lines.append(f"- Q{item.get('number')}: {item.get('reason')} (p{item.get('page')})")
    if report["validation_issues"]:
        lines += ["", "## Validation issues", ""]
        for issue in report["validation_issues"]:
            lines.append(
                f"- Q{issue.get('question_number')}: [{issue.get('code')}] {issue.get('message')}"
            )
    if report["notes"]:
        lines += ["", "## Notes", ""]
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
