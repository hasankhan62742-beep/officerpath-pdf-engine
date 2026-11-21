# OfficerPath AI — PDF Engine (Phase 1, M5)
# Visual detector: pen/print marks visible in the IMAGE but not
# (or not reliably) in the text layer — ticks, circles, stars and
# underlines near option letters.
#
# Method (OpenCV, deterministic, no guessing):
# - star / tick: template matching. The glyphs are rendered with
#   DejaVu Sans at the option letter's own height and matched at
#   three scales inside a search region around the option letter.
#   A match counts only at score >= 0.6, and the score IS the
#   reported confidence (capped at 0.9 — a visual mark is never
#   1.0).
# - circle: Hough circles on the search region; a circle whose
#   centre is near the option letter and whose radius is
#   0.7–1.5x the letter height counts.
# - underline: a horizontal ink run below the option text, found
#   by a horizontal morphological opening.
#
# Every detection carries its evidence: mark kind, score, and the
# normalised bounding box of the mark. The detector never fires
# without a location. Option boxes are the FULL option-line boxes
# (``option_boxes_from_tesseract`` groups Tesseract words into
# lines and returns the line containing each option marker) or
# synthetic fixtures with known geometry — the detector itself
# does not guess where the options are. Marks sit next to the
# option VALUE (e.g. Paper 60's "(C) F5*"), not next to the
# letter, so a letter-only box would miss them.

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

#: A template match below this score is not a detection.
#: 0.7 (raised from 0.6 in M5): the synthetic stars match at
#: 0.83+, while a 0.61 false match on the Paper 60 photo (dense
#: text) was the only sub-0.7 hit.
MATCH_THRESHOLD = 0.7
#: Visual confidence is capped — a mark is never certain.
CONFIDENCE_CAP = 0.9

_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


@dataclass
class VisualDetection:
    """One mark found in image space."""

    question_number: int | None
    option_index: int
    mark_kind: str  # star | tick | circle | underline
    score: float
    bbox: dict  # normalised x_min/y_min/x_max/y_max
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "question_number": self.question_number,
            "option_index": self.option_index,
            "mark_kind": self.mark_kind,
            "score": round(self.score, 3),
            "bbox": {k: round(v, 4) for k, v in self.bbox.items()},
            "evidence": self.evidence,
        }


def _render_glyph_template(glyph: str, size_px: int) -> np.ndarray:
    """Render one glyph (star/tick) in DejaVu Sans as a grayscale
    template (ink = dark)."""
    font = ImageFont.truetype(_DEJAVU, size_px)
    image = Image.new("L", (size_px * 2, size_px * 2), 255)
    draw = ImageDraw.Draw(image)
    draw.text((size_px // 2, size_px // 2), glyph, font=font, fill=0)
    return np.array(image)


def _template_match_scores(gray: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Best normalised cross-correlation of template in gray (both
    ink-dark). Returns (score, top-left)."""
    if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
        return 0.0, (0, 0)
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, best, _, loc = cv2.minMaxLoc(result)
    return float(best), (int(loc[0]), int(loc[1]))


def _search_region(shape: tuple[int, int], bbox: dict, pad: float) -> tuple[int, int, int, int]:
    """Pixel search window around a normalised option-letter box,
    expanded by ``pad`` x the letter height on every side."""
    height, width = shape[:2]
    x0 = int(bbox["x_min"] * width)
    y0 = int(bbox["y_min"] * height)
    x1 = int(bbox["x_max"] * width)
    y1 = int(bbox["y_max"] * height)
    letter_h = max(1, y1 - y0)
    pad_px = int(letter_h * pad)
    return (
        max(0, x0 - pad_px),
        max(0, y0 - pad_px),
        min(width, x1 + pad_px),
        min(height, y1 + pad_px),
    )


def _ring_is_drawn(binary: np.ndarray, cx: float, cy: float, radius: float) -> bool:
    """Is this Hough circle a real drawn ring? A hand-drawn circle
    is ONE connected ink stroke spanning (nearly) the full
    circumference. Dense text fails this even when it puts ink at
    most sampled circumference points: the "ring" ink comes from
    many separate letters, each spanning a few degrees. So: take
    the annulus band (radius ± 4 px), find its connected
    components, and require ONE component to span >= 300° around
    the centre. The interior must also be mostly white (< 40%
    ink) so filled blobs fail. Measured: the point-sampling
    version of this check passed 3 false circles on the Paper 60
    photo (parentheses + letter curves around "(A) XML"); the
    single-stroke version is what separates a drawn ring from
    text."""
    import math

    height, width = binary.shape[:2]
    x0 = max(0, int(cx - radius - 6))
    x1 = min(width, int(cx + radius + 6))
    y0 = max(0, int(cy - radius - 6))
    y1 = min(height, int(cy + radius + 6))
    if x1 <= x0 or y1 <= y0:
        return False
    crop = binary[y0:y1, x0:x1]
    yy, xx = np.mgrid[0 : crop.shape[0], 0 : crop.shape[1]]
    dist = np.sqrt((xx + x0 - cx) ** 2 + (yy + y0 - cy) ** 2)
    band = ((np.abs(dist - radius) <= 4) & (crop > 0)).astype(np.uint8)
    if int(np.count_nonzero(band)) < 20:
        return False
    num, labels, _stats, _cent = cv2.connectedComponentsWithStats(band, connectivity=8)
    best_span = 0.0
    for label in range(1, num):
        ys, xs = np.where(labels == label)
        if len(xs) < 10:
            continue
        angles = np.sort(np.arctan2(ys + y0 - cy, xs + x0 - cx) % (2 * math.pi))
        gaps = np.diff(np.concatenate([angles, angles[:1] + 2 * math.pi]))
        span = 2 * math.pi - float(np.max(gaps))
        best_span = max(best_span, span)
    if best_span < math.radians(300):
        return False
    interior = binary[y0:y1, x0:x1]
    ys, xs = np.where(interior > 0)
    if len(xs) == 0:
        return True
    inside = ((xs + x0 - cx) ** 2 + (ys + y0 - cy) ** 2) < (radius * 0.9) ** 2
    area = max(1.0, float(np.pi) * (radius * 0.9) ** 2)
    return float(np.count_nonzero(inside)) / area < 0.4


def detect_marks_in_image(
    image_png: bytes,
    option_boxes: list[dict],
    *,
    question_number: int | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> list[VisualDetection]:
    """Detect star / tick / circle / underline marks near the given
    option-LINE boxes. ``option_boxes`` is a list of
    ``{"option_index": int, "bbox": {x_min, y_min, x_max, y_max}}``
    in normalised coordinates, one per option line. Returns
    detections sorted by (option_index, mark_kind); at most one
    detection per (option, kind) — the best-scoring one."""
    arr = np.frombuffer(image_png, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("could not decode image_png")
    height, width = image.shape[:2]
    detections: list[VisualDetection] = []
    for box in option_boxes:
        option_index = int(box["option_index"])
        bbox = box["bbox"]
        letter_h = max(1, int((bbox["y_max"] - bbox["y_min"]) * height))
        # Pad 3x the letter height: a star/tick sits AFTER the
        # option value (up to ~1 letter height past the box edge)
        # and the glyph template is itself ~2 letter heights wide,
        # so the search window must hold the whole template.
        x0, y0, x1, y1 = _search_region(image.shape, bbox, pad=3.0)
        region = image[y0:y1, x0:x1]
        if region.size == 0:
            continue
        # --- star / tick by template matching -------------------
        for glyph, kind in [("★", "star"), ("✓", "tick")]:
            best_score = 0.0
            best_loc: tuple[int, int] = (0, 0)
            best_size = letter_h
            for scale in (0.8, 1.0, 1.25):
                size = max(8, int(letter_h * scale))
                template = _render_glyph_template(glyph, size)
                score, loc = _template_match_scores(region, template)
                if score > best_score:
                    best_score, best_loc, best_size = score, loc, size
            if best_score >= threshold:
                mx, my = best_loc
                detections.append(
                    VisualDetection(
                        question_number=question_number,
                        option_index=option_index,
                        mark_kind=kind,
                        score=min(best_score, CONFIDENCE_CAP),
                        bbox={
                            "x_min": (x0 + mx) / width,
                            "y_min": (y0 + my) / height,
                            "x_max": (x0 + mx + best_size) / width,
                            "y_max": (y0 + my + best_size) / height,
                        },
                        evidence=(
                            f"{kind} template match score {best_score:.2f} "
                            f"near option ({chr(65 + option_index)})"
                        ),
                    )
                )
        # --- circle by Hough ------------------------------------
        # A circled option is a circle AROUND the letter: radius
        # >= 1.1x the letter height, centred on the letter, and
        # extending past it on both sides. Letter loops ("a", "B")
        # are smaller than the letter and centred inside the word,
        # so they fail the radius and centre checks — without them
        # Hough fires on every round letter (measured: 3 false
        # circles on a clean synthetic page). A second, stronger
        # check: the ring must actually be drawn — >= 60% of 36
        # sampled circumference points must be ink, and the
        # interior must be mostly white (< 40% ink, the letter
        # itself accounts for ~10–20%). Hough alone fires on the
        # arcs letter curves make (measured: 7 false circles on
        # the Paper 60 photo, a page with no pen marks at all).
        blurred = cv2.medianBlur(region, 5)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=max(10, letter_h),
            param1=100,
            param2=25,
            minRadius=int(letter_h * 1.1),
            maxRadius=int(letter_h * 2.2),
        )
        if circles is not None:
            _, binary_full = cv2.threshold(image, 200, 255, cv2.THRESH_BINARY_INV)
            letter_cx = int(bbox["x_min"] * width) + letter_h // 2
            letter_cy = int((bbox["y_min"] + bbox["y_max"]) * height / 2)
            for cx, cy, radius in circles[0]:
                cx_abs, cy_abs = x0 + cx, y0 + cy
                centre_ok = (
                    abs(cx_abs - letter_cx) <= 0.8 * letter_h
                    and abs(cy_abs - letter_cy) <= 0.8 * letter_h
                )
                encloses_letter = (
                    cx_abs - radius < int(bbox["x_min"] * width)
                    and cx_abs + radius > int(bbox["x_min"] * width) + letter_h
                )
                ring_ok = _ring_is_drawn(binary_full, cx_abs, cy_abs, radius)
                if centre_ok and encloses_letter and ring_ok:
                    detections.append(
                        VisualDetection(
                            question_number=question_number,
                            option_index=option_index,
                            mark_kind="circle",
                            score=0.7,
                            bbox={
                                "x_min": (cx_abs - radius) / width,
                                "y_min": (cy_abs - radius) / height,
                                "x_max": (cx_abs + radius) / width,
                                "y_max": (cy_abs + radius) / height,
                            },
                            evidence=(
                                f"circle radius {radius:.0f}px around option "
                                f"({chr(65 + option_index)})"
                            ),
                        )
                    )
                    break
        # --- underline: THIN horizontal ink run below the letter -
        # A real underline is 1–3 px tall. The strip below an
        # option line also catches the NEXT line's ascenders on
        # tightly-set pages (measured: the first version fired on
        # every option of the Paper 60 photo — 50 false positives
        # on a page with no pen marks at all). So the run must be
        # thin: its bounding height <= max(3, letter_h // 6) px.
        below_y0 = int(bbox["y_max"] * height)
        below_y1 = min(height, below_y0 + max(2, letter_h // 2))
        below_x0 = int(bbox["x_min"] * width)
        below_x1 = int(bbox["x_max"] * width) + letter_h * 4
        below_x1 = min(width, below_x1)
        if below_y1 > below_y0 and below_x1 > below_x0:
            strip = image[below_y0:below_y1, below_x0:below_x1]
            _, binary = cv2.threshold(strip, 200, 255, cv2.THRESH_BINARY_INV)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, letter_h), 1))
            opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
            if int(np.count_nonzero(opened)) >= max(5, letter_h):
                rows = np.where(np.any(opened > 0, axis=1))[0]
                run_height = int(rows[-1] - rows[0] + 1) if len(rows) else 0
                if 0 < run_height <= max(3, letter_h // 6):
                    detections.append(
                        VisualDetection(
                            question_number=question_number,
                            option_index=option_index,
                            mark_kind="underline",
                            score=0.7,
                            bbox={
                                "x_min": below_x0 / width,
                                "y_min": below_y0 / height,
                                "x_max": below_x1 / width,
                                "y_max": below_y1 / height,
                            },
                            evidence=(
                                f"thin ({run_height}px) horizontal ink run below "
                                f"option ({chr(65 + option_index)})"
                            ),
                        )
                    )
    detections.sort(key=lambda d: (d.option_index, d.mark_kind))
    return _deduplicate(detections, option_boxes)


def _bbox_iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two normalised bboxes."""
    x0 = max(a["x_min"], b["x_min"])
    y0 = max(a["y_min"], b["y_min"])
    x1 = min(a["x_max"], b["x_max"])
    y1 = min(a["y_max"], b["y_max"])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    area_a = (a["x_max"] - a["x_min"]) * (a["y_max"] - a["y_min"])
    area_b = (b["x_max"] - b["x_min"]) * (b["y_max"] - b["y_min"])
    # float(): bbox values can be numpy scalars (from the Hough /
    # template paths) — the declared return is a plain float.
    return float(inter / (area_a + area_b - inter))


def _deduplicate(
    detections: list[VisualDetection], option_boxes: list[dict]
) -> list[VisualDetection]:
    """One physical mark can fall inside several options' search
    windows (a star after option B is also inside option A's
    window). Two detections of the same kind with nearly the same
    bbox are the same mark: keep the one whose option box is
    closest to the mark (centre-to-centre)."""
    by_box = {int(b["option_index"]): b["bbox"] for b in option_boxes}

    def _distance(d: VisualDetection) -> float:
        box = by_box.get(d.option_index)
        if box is None:
            return 1.0
        mcx = (d.bbox["x_min"] + d.bbox["x_max"]) / 2
        mcy = (d.bbox["y_min"] + d.bbox["y_max"]) / 2
        bcx = (box["x_min"] + box["x_max"]) / 2
        bcy = (box["y_min"] + box["y_max"]) / 2
        return float(((mcx - bcx) ** 2 + (mcy - bcy) ** 2) ** 0.5)

    kept: list[VisualDetection] = []
    for detection in detections:
        duplicate_of = None
        for other in kept:
            if (
                other.mark_kind == detection.mark_kind
                and _bbox_iou(other.bbox, detection.bbox) > 0.3
            ):
                duplicate_of = other
                break
        if duplicate_of is None:
            kept.append(detection)
        elif _distance(detection) < _distance(duplicate_of):
            kept[kept.index(duplicate_of)] = detection
    kept.sort(key=lambda d: (d.option_index, d.mark_kind))
    return kept


def option_boxes_from_tesseract(image_png: bytes) -> list[dict]:
    """Find option lines in the image with Tesseract word boxes:
    words are grouped into lines (block/par/line); a line whose
    first word is an option marker (``(A)`` / ``B.`` / ...) yields
    one box = the union of that line's word boxes, in normalised
    coordinates. The full line box matters: marks sit next to the
    option value, not the letter."""
    import re

    import pytesseract

    image = Image.open(io.BytesIO(image_png))
    width, height = image.size
    try:
        data = pytesseract.image_to_data(
            image, lang="eng", config="--psm 3", output_type=pytesseract.Output.DICT
        )
    except Exception:
        return []
    marker_re = re.compile(r"^\(?\s*([A-Da-d])\s*[\)\.\:]$")
    n = len(data.get("text", []))
    lines: dict[tuple[int, int, int], list[int]] = {}
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        lines.setdefault(key, []).append(i)
    boxes: list[dict] = []
    for key in sorted(lines):
        idxs = lines[key]
        first_word = (data["text"][idxs[0]] or "").strip()
        match = marker_re.match(first_word)
        if not match:
            continue
        x0 = min(int(data["left"][i]) for i in idxs)
        y0 = min(int(data["top"][i]) for i in idxs)
        x1 = max(int(data["left"][i]) + int(data["width"][i]) for i in idxs)
        y1 = max(int(data["top"][i]) + int(data["height"][i]) for i in idxs)
        if x1 <= x0 or y1 <= y0:
            continue
        boxes.append(
            {
                "option_index": ord(match.group(1).upper()) - ord("A"),
                "bbox": {
                    "x_min": x0 / width,
                    "y_min": y0 / height,
                    "x_max": x1 / width,
                    "y_max": y1 / height,
                },
            }
        )
    return boxes
