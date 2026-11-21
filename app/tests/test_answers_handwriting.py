# OfficerPath AI — Phase 1, M5
# Handwriting detector tests on synthetic pages: a wide multi-word
# scribble in the margin is marginalia; a small mark next to an
# option letter is an answer mark; printed text (covered by word
# boxes) is never reported as ink.

import io

from PIL import Image, ImageDraw, ImageFont

from app.pipeline.answers.handwriting import (
    classify_ink_region,
    find_unmatched_ink,
)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _png_with_note() -> tuple[bytes, list[dict]]:
    """600x400 page: printed option lines (with word boxes) plus a
    handwritten-style note scribbled at the bottom."""
    image = Image.new("L", (600, 400), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 28)
    word_boxes: list[dict] = []
    for i, text in enumerate(["(A) Alpha", "(B) Beta", "(C) Gamma", "(D) Delta"]):
        x, y = 60, 40 + i * 60
        draw.text((x, y), text, font=font, fill=0)
        bbox = draw.textbbox((x, y), text, font=font)
        word_boxes.append(
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
    # Handwritten note: a wavy multi-stroke scribble at the bottom.
    for k in range(6):
        x0 = 80 + k * 60
        draw.line(
            [(x0, 360), (x0 + 25, 348), (x0 + 50, 362), (x0 + 55, 350)],
            fill=0,
            width=2,
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), word_boxes


def test_printed_text_is_not_reported_as_ink() -> None:
    png, word_boxes = _png_with_note()
    # Word boxes cover the printed lines; only the bottom scribble
    # should survive as unmatched ink.
    regions = find_unmatched_ink(png, word_boxes)
    assert regions, "the bottom scribble should be found"
    for region in regions:
        assert region.bbox["y_min"] > 0.8, "only bottom-margin ink survives"


def test_wide_bottom_scribble_is_marginalia() -> None:
    png, word_boxes = _png_with_note()
    regions = find_unmatched_ink(png, word_boxes)
    assert regions
    classified = [classify_ink_region(r, option_boxes=word_boxes) for r in regions]
    assert any(r.classification == "marginalia" for r in classified)
    assert not any(r.classification == "answer-mark" for r in classified)


def test_small_mark_next_to_option_is_answer_mark() -> None:
    # A single small blob right next to the (B) option line.
    image = Image.new("L", (600, 400), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 28)
    draw.text((60, 100), "(B) Beta", font=font, fill=0)
    bbox = draw.textbbox((60, 100), "(B) Beta", font=font)
    word_box = {
        "option_index": 1,
        "bbox": {
            "x_min": bbox[0] / 600,
            "y_min": bbox[1] / 400,
            "x_max": bbox[2] / 600,
            "y_max": bbox[3] / 400,
        },
    }
    # Small tick-like blob just after the option text.
    draw.ellipse([185, 105, 195, 115], fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    regions = find_unmatched_ink(buffer.getvalue(), [word_box])
    assert len(regions) == 1
    classified = classify_ink_region(regions[0], option_boxes=[word_box])
    assert classified.classification == "answer-mark"
    assert "adjacent to an option letter" in classified.reason


def test_unclassifiable_ink_stays_unknown() -> None:
    # A lone mid-page blob, far from every option and too small to
    # be a note: neither rule fires.
    image = Image.new("L", (600, 400), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse([400, 200, 415, 215], fill=0)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    regions = find_unmatched_ink(buffer.getvalue(), [])
    assert len(regions) == 1
    classified = classify_ink_region(regions[0], option_boxes=[])
    assert classified.classification == "unknown"
    assert "left unclassified" in classified.reason
