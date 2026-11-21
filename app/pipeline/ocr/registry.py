# OfficerPath AI — PDF Engine (Phase 1, M3)
# OCR engine registry (prompt §5.2): name -> engine, with an
# availability probe per engine. The core never imports a concrete
# engine module: adapters register themselves, the router asks the
# registry what is available, and an unavailable engine is skipped
# with its reason recorded — never faked, never silently dropped.
#
# Availability is probed LAZILY and cached per registry instance:
# probing PaddleOCR imports a ~900 MB venv's worth of heavy modules,
# so it happens once, on first use, not at import time.

from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.interfaces import OCREngine
from app.pipeline.ocr.digital import DigitalExtractor


@dataclass
class EngineStatus:
    available: bool
    version: str | None = None
    reason: str | None = None


class OCRRegistry:
    """Name -> OCREngine, plus lazy availability probing."""

    def __init__(self) -> None:
        self._engines: dict[str, OCREngine] = {}
        self._status: dict[str, EngineStatus] = {}
        self._probers: dict[str, object] = {}

    def register(self, engine: OCREngine, prober: object = None) -> None:
        """Register an engine. `prober` is an optional object with an
        is_available()/probe() style check; when absent the engine is
        assumed available (the digital extractor: no external dep)."""
        self._engines[engine.name] = engine
        if prober is not None:
            self._probers[engine.name] = prober

    def names(self) -> list[str]:
        return sorted(self._engines)

    def engine(self, name: str) -> OCREngine:
        return self._engines[name]

    def status(self, name: str) -> EngineStatus:
        """Availability, probed once and cached. A prober that raises
        is reported unavailable with the exception text — probing must
        never crash the pipeline."""
        if name in self._status:
            return self._status[name]
        prober = self._probers.get(name)
        if prober is None:
            status = EngineStatus(
                available=True,
                version=getattr(self._engines[name], "version", None),
            )
            self._status[name] = status
            return status
        try:
            if hasattr(prober, "probe"):
                info = prober.probe()  # TesseractInfo-like: available/version/reason
                status = EngineStatus(
                    available=bool(info.available),
                    version=getattr(info, "version", None),
                    reason=getattr(info, "reason", None),
                )
            elif hasattr(prober, "is_available"):
                ok = bool(prober.is_available())
                status = EngineStatus(
                    available=ok,
                    version=getattr(self._engines[name], "version", None),
                    reason=None if ok else "prober reported unavailable",
                )
            else:
                status = EngineStatus(available=True)
        except Exception as exc:  # noqa: BLE001 - probing must not crash
            status = EngineStatus(available=False, reason=f"probe failed: {exc}")
        self._status[name] = status
        return status

    def available_names(self) -> list[str]:
        return [name for name in self.names() if self.status(name).available]

    def unavailable_report(self) -> dict[str, str]:
        """name -> reason for every registered engine that cannot run.
        The benchmark report and the OCR stage record this verbatim."""
        report: dict[str, str] = {}
        for name in self.names():
            status = self.status(name)
            if not status.available:
                report[name] = status.reason or "unavailable (no reason given)"
        return report


def default_registry(
    *,
    tesseract_languages: str = "eng+urd",
    tesseract_psm: int = 3,
    paddleocr_language: str = "ar",
    paddleocr_enabled: bool = True,
) -> OCRRegistry:
    """The production registry: digital extractor (always) +
    Tesseract + PaddleOCR (each availability-gated). Importing this
    module does NOT import paddleocr/tesseract — adapters are imported
    here, but their heavy dependencies load lazily inside the
    adapters themselves."""
    from app.pipeline.ocr.paddle import PaddleOCRAdapter
    from app.pipeline.ocr.tesseract import TesseractAdapter

    registry = OCRRegistry()
    registry.register(DigitalExtractor())
    tess = TesseractAdapter(languages=tesseract_languages, psm=tesseract_psm)
    registry.register(tess, prober=tess)
    if paddleocr_enabled:
        paddle = PaddleOCRAdapter(language=paddleocr_language)
        registry.register(paddle, prober=paddle)
    return registry
