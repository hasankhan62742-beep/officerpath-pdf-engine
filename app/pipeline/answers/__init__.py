# OfficerPath AI — PDF Engine (Phase 1, M5)
# Answer detection package: one detector per answer mechanism
# (trailing key, inline, digital style, visual, handwriting), plus
# the standing precedence resolver and the document-level service.
#
# Design (M5): the M4 extractor already resolves answers inline
# while parsing (answer-line / key / tick / bold / asterisk via
# ``extract.signals.resolve_signals``). This package does NOT redo
# that work — it makes each mechanism an EXPLICIT, measurable
# detector with evidence, filters the noise each mechanism actually
# produces on the golden set, and resolves conflicts under the
# standing precedence:
#   manual verification > explicit key > inline answer >
#   digital style > visual > inferred.
# An UNKNOWN answer is a correct outcome; a guessed answer
# presented as correct is the worst failure. Detectors never
# fabricate: when no detector fires, the answer is UNKNOWN.

from app.pipeline.answers.handwriting import (
    InkRegion,
    classify_ink_region,
    find_unmatched_ink,
)
from app.pipeline.answers.inline_detector import (
    MonthlyCaAnswerCheck,
    check_monthly_ca_answers,
    detect_inline_answer,
    detect_qa_answer,
    inline_detection_to_result,
)
from app.pipeline.answers.key_detector import (
    KeyDetection,
    detect_trailing_key,
    key_detection_to_result,
)
from app.pipeline.answers.models import (
    AnswerEvidence,
    DetectorResult,
    ResolvedAnswer,
)
from app.pipeline.answers.precedence import (
    DETECTOR_RANK,
    INFERRED_CONFIDENCE_CAP,
    PRECEDENCE,
    resolve_answer,
)
from app.pipeline.answers.service import (
    AnswerResolution,
    apply_resolution,
    resolve_document_answers,
)
from app.pipeline.answers.style_detector import (
    detect_bold_option,
    detect_star_option,
    detect_style_marks,
)
from app.pipeline.answers.visual_detector import (
    VisualDetection,
    detect_marks_in_image,
    option_boxes_from_tesseract,
)

__all__ = [
    "AnswerEvidence",
    "AnswerResolution",
    "DetectorResult",
    "InkRegion",
    "KeyDetection",
    "MonthlyCaAnswerCheck",
    "ResolvedAnswer",
    "VisualDetection",
    "apply_resolution",
    "check_monthly_ca_answers",
    "classify_ink_region",
    "detect_bold_option",
    "detect_inline_answer",
    "detect_marks_in_image",
    "detect_qa_answer",
    "detect_star_option",
    "detect_style_marks",
    "detect_trailing_key",
    "find_unmatched_ink",
    "inline_detection_to_result",
    "key_detection_to_result",
    "option_boxes_from_tesseract",
    "resolve_answer",
    "resolve_document_answers",
    "DETECTOR_RANK",
    "INFERRED_CONFIDENCE_CAP",
    "PRECEDENCE",
]
