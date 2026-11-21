# OfficerPath AI — PDF Engine (Phase 1, M6)
# Matching: join M4 extraction + M5 answer resolution into resolved
# MCQs, promote answerable pending questions (ADR-007), validate,
# calibrate confidences, and report. Pure functions over ParseResult
# + AnswerResolution — no I/O except the optional fitted calibration
# file (see service.load_calibration).

from app.pipeline.matching.calibration import (
    Calibration,
    CalibrationBucket,
    expected_calibration_error,
    fit_calibration,
)
from app.pipeline.matching.key_region import (
    KeyRegion,
    locate_key_region,
    parse_key_entries_in_region,
)
from app.pipeline.matching.models import (
    MatchedDocument,
    ResolvedMCQ,
    ValidationIssue,
)
from app.pipeline.matching.promotion import (
    MIN_PROMOTION_CONFIDENCE,
    PROMOTABLE_RANKS,
    PromotionReport,
    promote_pending,
)
from app.pipeline.matching.report import build_document_report, report_to_markdown
from app.pipeline.matching.service import (
    load_calibration,
    match_document,
    parse_document_bytes,
    resolve_with_key_detection,
)
from app.pipeline.matching.validate import ERROR_CODES, validate_matched_document, validate_question

__all__ = [
    "Calibration",
    "CalibrationBucket",
    "ERROR_CODES",
    "KeyRegion",
    "MIN_PROMOTION_CONFIDENCE",
    "MatchedDocument",
    "PROMOTABLE_RANKS",
    "PromotionReport",
    "ResolvedMCQ",
    "ValidationIssue",
    "build_document_report",
    "expected_calibration_error",
    "fit_calibration",
    "load_calibration",
    "locate_key_region",
    "match_document",
    "parse_document_bytes",
    "parse_key_entries_in_region",
    "promote_pending",
    "report_to_markdown",
    "resolve_with_key_detection",
    "validate_matched_document",
    "validate_question",
]
