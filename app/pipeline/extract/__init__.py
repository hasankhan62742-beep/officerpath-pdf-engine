# OfficerPath AI — PDF Engine (Phase 1, M4)
# MCQ extraction package: port of the Flutter app's MCQ parser rules
# (docs/milestones/M4_DART_PARSER_PORT_SPEC.md) plus the M4 additions
# recorded in the task brief (D8 delimiter-aware Sr# tables, D10
# seeded distractor shuffle, D13 structured paper identity, D14
# unknown subjects flagged, not mapped to GK).

from app.pipeline.extract.blocks import (
    compute_number_duplicates,
    compute_number_gaps,
    demote_decoded_numbers,
    interpolate_numbers,
    parse_one_liner,
    parse_standard_block,
    split_into_blocks,
)
from app.pipeline.extract.keys import (
    decide_key_match,
    parse_key_entries,
    resolve_answer_token,
)
from app.pipeline.extract.markers import (
    clean_stored,
    decode_ocr_option_letter,
    split_option_line,
)
from app.pipeline.extract.models import (
    ExtractedQuestion,
    ParseResult,
    PendingQuestion,
    QAPair,
)
from app.pipeline.extract.numbers import (
    decode_ocr_number,
    normalize_urdu_digits,
    question_number_detailed,
)
from app.pipeline.extract.qa import build_q_only_options, scan_flashcards
from app.pipeline.extract.scoring import score_candidate
from app.pipeline.extract.service import (
    PageLines,
    extract_document,
    extract_from_digital_pdf,
    extract_from_ocr_blocks,
)
from app.pipeline.extract.signals import confidence_for_source
from app.pipeline.extract.tables import (
    parse_pipe_delimiter_lines,
    parse_sr_delimiter_lines,
    parse_sr_pdfplumber_tables,
    parse_table_columns,
    parse_table_rows_grid,
)
from app.pipeline.extract.validate import (
    looks_fabricated,
    validate_parse_result,
)

__all__ = [
    "PageLines",
    "ExtractedQuestion",
    "ParseResult",
    "PendingQuestion",
    "QAPair",
    "build_q_only_options",
    "clean_stored",
    "compute_number_duplicates",
    "compute_number_gaps",
    "confidence_for_source",
    "decode_ocr_number",
    "decode_ocr_option_letter",
    "decide_key_match",
    "demote_decoded_numbers",
    "extract_document",
    "extract_from_digital_pdf",
    "extract_from_ocr_blocks",
    "interpolate_numbers",
    "looks_fabricated",
    "normalize_urdu_digits",
    "parse_key_entries",
    "parse_one_liner",
    "parse_pipe_delimiter_lines",
    "parse_sr_delimiter_lines",
    "parse_sr_pdfplumber_tables",
    "parse_standard_block",
    "parse_table_columns",
    "parse_table_rows_grid",
    "question_number_detailed",
    "resolve_answer_token",
    "scan_flashcards",
    "score_candidate",
    "split_into_blocks",
    "split_option_line",
    "validate_parse_result",
]
