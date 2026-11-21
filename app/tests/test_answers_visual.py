# OfficerPath AI — Phase 1, M5
# Visual detector tests on synthetic pages with known geometry:
# one mark per option (star, tick, circle, underline) plus a
# clean control page that must produce NO detections.

import io

from PIL import Image, ImageDraw, ImageFont

from app.pipeline.answers.visual_detector import detect_marks_in_image

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SIZE = 28


def _page(marks: bool) -> tuple[bytes, list[dict]]:
    """A 600x400 synthetic page with four option lines. With
    marks=True: star after (B), tick after (C), circle around the
    (D) letter, underline under (A). Returns (png, option boxes)."""
    image = Image.new("L", (600, 400), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, SIZE)
    lines = ["(A) Alpha", "(B) Beta", "(C) Gamma", "(D) Delta"]
    boxes: list[dict] = []
    for i, text in enumerate(lines):
        x, y = 60, 60 + i * 70
        draw.text((x, y), text, font=font, fill=0)
        bbox = draw.textbbox((x, y), text, font=font)
        boxes.append(
            {
                "option_index": i,
                "bbox": {
                    "x_min": bbox[0] / 600,
                    "y_min": bbox[1] / 400,
                    "x_max": bbox[2] / 600,
                    "y_max": bbox[3] / 400,
                },
            }
        )
    if marks:
        # star right after "(B) Beta" (text ends ~x175)
        draw.text((180, 130), "★", font=font, fill=0)
        # tick right after "(C) Gamma" (text ends ~x221)
        draw.text((225, 200), "✓", font=font, fill=0)
        # circle around the "(D)" letter (centre ~ (75, 285),
        # radius 35px = 1.4x the 25px letter height)
        draw.ellipse([40, 250, 110, 320], outline=0, width=3)
        # underline under "(A) Alpha"
        draw.line([60, 98, 170, 98], fill=0, width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), boxes


def test_star_detected_on_b() -> None:
    png, boxes = _page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    stars = [d for d in detections if d.mark_kind == "star"]
    assert len(stars) == 1
    assert stars[0].option_index == 1
    assert stars[0].score >= 0.6
    assert stars[0].score <= 0.9  # capped
    assert stars[0].question_number == 1
    # The mark sits right of the option letter (letter at x 0.10).
    assert stars[0].bbox["x_min"] > 0.25


def test_tick_detected_on_c() -> None:
    png, boxes = _page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    ticks = [d for d in detections if d.mark_kind == "tick"]
    assert len(ticks) == 1
    assert ticks[0].option_index == 2
    assert ticks[0].score >= 0.6


def test_circle_detected_on_d() -> None:
    png, boxes = _page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    circles = [d for d in detections if d.mark_kind == "circle"]
    assert len(circles) == 1
    assert circles[0].option_index == 3
    assert circles[0].score <= 0.9


def test_underline_detected_on_a() -> None:
    png, boxes = _page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    underlines = [d for d in detections if d.mark_kind == "underline"]
    assert len(underlines) == 1
    assert underlines[0].option_index == 0


def test_clean_page_has_no_detections() -> None:
    png, boxes = _page(marks=False)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    assert detections == []


def test_detections_are_json_serialisable() -> None:
    png, boxes = _page(marks=True)
    detections = detect_marks_in_image(png, boxes, question_number=1)
    assert detections
    for detection in detections:
        as_dict = detection.to_dict()
        assert as_dict["mark_kind"] in ("star", "tick", "circle", "underline")
        assert 0.0 <= as_dict["bbox"]["x_min"] < as_dict["bbox"]["x_max"] <= 1.0
