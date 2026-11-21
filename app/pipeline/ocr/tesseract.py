# OfficerPath AI — PDF Engine (Phase 1, M3)
# Tesseract adapter (prompt §8): offline OCR via the system
# tesseract binary + pytesseract. Languages eng+urd (configurable);
# the binary and traineddata are a SYSTEM dependency (apt:
# tesseract-ocr tesseract-ocr-urd tesseract-ocr-ara), not a Python
# wheel — Docker must install them (Dockerfile note in ADR-005).
#
# Availability is honest: if the binary or a requested language is
# missing, is_available() reports (False, reason) and recognize()
# raises EngineUnavailableError — the router skips the engine, the
# pipeline records it, nothing is faked.
#
# Output: pytesseract image_to_data (TSV) grouped into lines, then
# into Tesseract blocks. Word confidences are kept (keys "word#n"
# because the same word can appear twice in a block). Confidence -1
# (Tesseract's "no confidence") is dropped, never averaged in.
# Reading order inside a block is line order; cross-block order is
# assigned by the layout stage, not guessed here.
#
# Rotation: image_to_osd gives the OSD rotation (0/90/180/270) and
# script detection. detect_rotation() is a best-effort probe — OSD
# fails on blank or very small images and then returns None with the
# reason. The M2 limitation "90°/180° content rotation NOT detected"
# is addressed here, not hidden: see layout/analyzer.py.

from __future__ import annotations

import io
import shutil
import subprocess
from dataclasses import dataclass

from PIL import Image

from app.pipeline.interfaces import BoundingBox, OCRBlock, PageContext
from app.pipeline.ocr.normalize import detect_script

ENGINE_NAME = "tesseract"


class EngineUnavailableError(RuntimeError):
    """An engine cannot run in this environment (missing binary,
    missing language data, missing package). The router treats this
    as 'skip with reason', never as a failure of the document."""


@dataclass
class TesseractInfo:
    available: bool
    version: str | None = None
    languages: list[str] | None = None
    reason: str | None = None


def probe_tesseract(binary: str = "tesseract", languages: str = "eng+urd") -> TesseractInfo:
    """Check the binary + requested languages without running OCR."""
    path = shutil.which(binary)
    if path is None:
        return TesseractInfo(
            available=False, reason=f"tesseract binary not found on PATH ({binary!r})"
        )
    try:
        proc = subprocess.run([path, "--list-langs"], capture_output=True, text=True, timeout=30)
    except Exception as exc:  # binary present but not runnable
        return TesseractInfo(available=False, reason=f"tesseract --list-langs failed: {exc}")
    langs = [line.strip() for line in proc.stdout.splitlines()[1:] if line.strip()]
    wanted = [lang for lang in languages.split("+") if lang]
    missing = [lang for lang in wanted if lang not in langs]
    if missing:
        return TesseractInfo(
            available=False,
            languages=langs,
            reason=f"missing traineddata for: {', '.join(missing)} (have: {', '.join(langs)})",
        )
    version = None
    try:
        import pytesseract

        version = str(pytesseract.get_tesseract_version())
    except Exception:
        version = None
    return TesseractInfo(available=True, version=version, languages=langs)


class TesseractAdapter:
    """OCREngine backed by the system tesseract binary."""

    name = ENGINE_NAME

    def __init__(
        self,
        languages: str = "eng+urd",
        psm: int = 3,
        binary: str = "tesseract",
    ) -> None:
        self.languages = languages
        self.psm = psm
        self.binary = binary
        self._info: TesseractInfo | None = None

    @property
    def version(self) -> str:
        return self.probe().version or "unknown"

    def probe(self) -> TesseractInfo:
        if self._info is None:
            self._info = probe_tesseract(self.binary, self.languages)
        return self._info

    def is_available(self) -> bool:
        return self.probe().available

    def recognize(self, page: PageContext) -> list[OCRBlock]:
        info = self.probe()
        if not info.available:
            raise EngineUnavailableError(f"tesseract unavailable: {info.reason}")
        if page.image_png is None:
            raise ValueError("TesseractAdapter needs image_png on the PageContext.")
        import pytesseract

        image = Image.open(io.BytesIO(page.image_png))
        width, height = image.size
        config = f"--psm {self.psm}"
        try:
            data = pytesseract.image_to_data(
                image,
                lang=self.languages,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            raise RuntimeError(f"tesseract failed on page {page.page_number}: {exc}") from exc
        return _group_data_to_blocks(data, page, width, height, info.version)

    def detect_rotation(self, png_bytes: bytes) -> dict | None:
        """OSD probe: returns {"degrees": 0|90|180|270, "script": ...,
        "confidence": ...} or None when OSD cannot decide (blank /
        tiny / no text). Never raises for an undecidable image."""
        import pytesseract

        try:
            image = Image.open(io.BytesIO(png_bytes))
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            degrees = int(osd.get("orientation", 0))
            if degrees not in (0, 90, 180, 270):
                return None
            return {
                "degrees": degrees,
                "script": osd.get("script"),
                "confidence": float(osd.get("orientation_conf", 0.0)),
                "method": "tesseract-osd",
            }
        except Exception:
            return None


def _group_data_to_blocks(
    data: dict, page: PageContext, width: int, height: int, version: str | None
) -> list[OCRBlock]:
    """Group pytesseract image_to_data rows (words) into lines, then
    into Tesseract blocks. Empty words and conf -1 are dropped."""
    n = len(data.get("text", []))
    lines: dict[tuple[int, int, int], dict] = {}
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        conf = float(data["conf"][i])
        slot = lines.setdefault(
            key, {"words": [], "left": [], "top": [], "right": [], "bottom": []}
        )
        slot["words"].append((word, conf))
        left = int(data["left"][i])
        top = int(data["top"][i])
        slot["left"].append(left)
        slot["top"].append(top)
        slot["right"].append(left + int(data["width"][i]))
        slot["bottom"].append(top + int(data["height"][i]))
    blocks: dict[int, list[dict]] = {}
    for (block_num, _par, _line), slot in lines.items():
        blocks.setdefault(block_num, []).append(slot)
    result: list[OCRBlock] = []
    for block_num in sorted(blocks):
        block_lines = sorted(blocks[block_num], key=lambda s: min(s["top"]))
        texts: list[str] = []
        word_confidences: dict[str, float] = {}
        confidences: list[float] = []
        x_min = min(min(s["left"]) for s in block_lines)
        y_min = min(min(s["top"]) for s in block_lines)
        x_max = max(max(s["right"]) for s in block_lines)
        y_max = max(max(s["bottom"]) for s in block_lines)
        word_index = 0
        for slot in block_lines:
            line_words: list[str] = []
            for word, conf in slot["words"]:
                line_words.append(word)
                word_confidences[f"{word}#{word_index}"] = conf
                word_index += 1
                if conf >= 0:
                    confidences.append(conf)
            texts.append(" ".join(line_words))
        text = "\n".join(texts).strip()
        if not text:
            continue
        result.append(
            OCRBlock(
                text=text,
                bbox=BoundingBox(
                    x_min=max(0.0, x_min / width),
                    y_min=max(0.0, y_min / height),
                    x_max=min(1.0, x_max / width),
                    y_max=min(1.0, y_max / height),
                ),
                page_number=page.page_number,
                reading_order=None,  # assigned by the layout stage
                confidence=(sum(confidences) / len(confidences) / 100.0) if confidences else None,
                word_confidences=word_confidences or None,
                language=detect_script(text),
                engine=ENGINE_NAME,
                engine_version=version,
                style=None,
            )
        )
    return result
