# OfficerPath AI — PDF Engine (Phase 1, M1)
# Plugin interfaces (prompt §5.2) + pipeline state machine (§5.3).
#
# Every stage is a Protocol: a new OCR engine, layout analyser or
# detector is added by implementing the Protocol and registering it —
# the core never imports a concrete engine. Adapters land in M2–M5;
# this module defines the contracts only, plus the stage-transition
# table that ProcessingStage rows must obey.
#
# Evidence rule: an implementation must never invent a value. Where a
# stage cannot measure something (e.g. blur without OpenCV), it
# returns None and records why — the caller stores the gap, it does
# not fill it with a guess.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class PipelineStage(StrEnum):
    """Pipeline states (prompt §5.3). One document, one current stage;
    every transition is a row in processing_stages."""

    UPLOADED = "uploaded"
    VALIDATED = "validated"
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    OCR_DONE = "ocr_done"
    LAYOUT_DONE = "layout_done"
    EXTRACTED = "extracted"
    ANSWERS_DETECTED = "answers_detected"
    MATCHED = "matched"
    SCORED = "scored"
    COMPLETED = "completed"
    REQUIRES_REVIEW = "requires_review"
    FAILED = "failed"


# Allowed transitions. A stage may always move to FAILED (fail loudly)
# or REQUIRES_REVIEW; anything else must follow this table. The
# service layer enforces it; the database only records what happened.
ALLOWED_TRANSITIONS: dict[PipelineStage, frozenset[PipelineStage]] = {
    PipelineStage.UPLOADED: frozenset(
        {PipelineStage.VALIDATED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.VALIDATED: frozenset(
        {PipelineStage.QUEUED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.QUEUED: frozenset(
        {PipelineStage.PREPROCESSING, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.PREPROCESSING: frozenset(
        {PipelineStage.OCR_DONE, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.OCR_DONE: frozenset(
        {PipelineStage.LAYOUT_DONE, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.LAYOUT_DONE: frozenset(
        {PipelineStage.EXTRACTED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.EXTRACTED: frozenset(
        {PipelineStage.ANSWERS_DETECTED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.ANSWERS_DETECTED: frozenset(
        {PipelineStage.MATCHED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.MATCHED: frozenset(
        {PipelineStage.SCORED, PipelineStage.FAILED, PipelineStage.REQUIRES_REVIEW}
    ),
    PipelineStage.SCORED: frozenset(
        {
            PipelineStage.COMPLETED,
            PipelineStage.REQUIRES_REVIEW,
            PipelineStage.FAILED,
        }
    ),
    PipelineStage.COMPLETED: frozenset(),
    PipelineStage.REQUIRES_REVIEW: frozenset(
        {PipelineStage.PREPROCESSING, PipelineStage.COMPLETED, PipelineStage.FAILED}
    ),
    PipelineStage.FAILED: frozenset({PipelineStage.QUEUED}),
}


def can_transition(from_stage: PipelineStage, to_stage: PipelineStage) -> bool:
    """True when the state machine allows from_stage -> to_stage."""
    return to_stage in ALLOWED_TRANSITIONS.get(from_stage, frozenset())


@dataclass(frozen=True)
class BoundingBox:
    """Normalized coordinates (0.0–1.0 of page width/height)."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class OCRBlock:
    """One normalized OCR output block (prompt §8)."""

    text: str
    bbox: BoundingBox | None
    page_number: int
    reading_order: int | None = None
    confidence: float | None = None
    word_confidences: dict[str, float] | None = None
    language: str | None = None
    engine: str = ""
    engine_version: str | None = None
    style: dict[str, Any] | None = None


@dataclass
class PageContext:
    """Everything a stage needs about one page.

    M3 extension (recorded reason): OCR adapters need the actual page
    bytes, not just a storage path. `image_png` / `pdf_bytes` are
    therefore optional fields, set by the orchestrator for ONE page at
    a time and released by the caller after the stage returns — the
    M2 streaming rule (one page in memory, buffers released per page)
    is preserved; the context never holds a whole document."""

    document_id: uuid.UUID
    page_number: int
    storage_path: str
    classification: str = "unknown"
    width_px: int | None = None
    height_px: int | None = None
    correlation_id: str = ""
    image_png: bytes | None = None
    pdf_bytes: bytes | None = None
    dpi_used: float | None = None


@dataclass
class PipelineContext:
    """Shared run context: ids, rule-set version, and a bag for stage
    outputs. Stages read/write only their own keys; the orchestrator
    owns the transitions."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    user_id: uuid.UUID
    correlation_id: str = ""
    rule_set_version: str = "m1-default"
    stage_outputs: dict[str, Any] = field(default_factory=dict)


class OCREngine(Protocol):
    """recognize(page) -> OCR blocks, in reading order. M3."""

    name: str

    @property
    def version(self) -> str: ...

    def recognize(self, page: PageContext) -> list[OCRBlock]: ...


class LayoutAnalyzer(Protocol):
    """analyze(page, blocks) -> layout: columns, regions, order. M3."""

    def analyze(self, page: PageContext, blocks: list[OCRBlock]) -> dict[str, Any]: ...


class QuestionDetector(Protocol):
    """Return candidate questions with evidence. M4."""

    def detect(
        self, page: PageContext, blocks: list[OCRBlock], layout: dict[str, Any]
    ) -> list[dict[str, Any]]: ...


class OptionDetector(Protocol):
    """Return option candidates for a question region. M4."""

    def detect(
        self, page: PageContext, blocks: list[OCRBlock], question: dict[str, Any]
    ) -> list[dict[str, Any]]: ...


class AnswerSourceDetector(Protocol):
    """Detect one answer-source kind (key table, inline, visual...). M5."""

    source_type: str

    def detect(self, page: PageContext, blocks: list[OCRBlock]) -> list[dict[str, Any]]: ...


class Matcher(Protocol):
    """Deterministic answer matching, document-scoped. M6."""

    def match(
        self, questions: list[dict[str, Any]], sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


class ConfidenceScorer(Protocol):
    """Score one item; returns component scores + overall. M6."""

    def score(self, item: dict[str, Any]) -> dict[str, float]: ...


class AIAssistProvider(Protocol):
    """Optional AI assistance (prompt §15). Disabled by default;
    suggestions only — it NEVER produces a verified answer and NEVER
    overwrites original content. No provider is implemented in M1."""

    name: str
    enabled: bool

    def suggest(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]: ...


class StageRegistry:
    """Name -> implementation registry. One registry per interface kind;
    the orchestrator looks implementations up by name so a new engine
    is a registration, not a code change in the core."""

    def __init__(self) -> None:
        self._ocr: dict[str, OCREngine] = {}
        self._layout: dict[str, LayoutAnalyzer] = {}
        self._question_detectors: dict[str, QuestionDetector] = {}
        self._answer_detectors: dict[str, AnswerSourceDetector] = {}
        self._ai: dict[str, AIAssistProvider] = {}

    def register_ocr(self, engine: OCREngine) -> None:
        self._ocr[engine.name] = engine

    def register_layout(self, name: str, analyzer: LayoutAnalyzer) -> None:
        self._layout[name] = analyzer

    def register_question_detector(self, name: str, detector: QuestionDetector) -> None:
        self._question_detectors[name] = detector

    def register_answer_detector(self, detector: AnswerSourceDetector) -> None:
        self._answer_detectors[detector.source_type] = detector

    def register_ai(self, provider: AIAssistProvider) -> None:
        self._ai[provider.name] = provider

    def ocr(self, name: str) -> OCREngine:
        return self._ocr[name]

    def ocr_names(self) -> list[str]:
        return sorted(self._ocr)

    def ai(self, name: str) -> AIAssistProvider:
        return self._ai[name]
