# OfficerPath AI — Phase 1, M7
# Image parse: one photo (JPEG/PNG) through the same OCR ->
# layout -> extract -> answers -> matching pipeline as a scanned
# PDF page, returning the same resolved-MCQ shape. Server side of
# the Flutter importImage path.

import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.pipeline.matching.service import parse_image_bytes
from app.tests.conftest import auth_headers

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _mcq_image_png(with_key: bool = True) -> bytes:
    font = ImageFont.truetype(FONT, 28)
    img = Image.new("RGB", (1200, 1100 if with_key else 900), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        "1. What is the capital of France?",
        "(A) London",
        "(B) Paris",
        "(C) Rome",
        "(D) Berlin",
        "",
        "2. What is 2 + 2?",
        "(A) 3",
        "(B) 4",
        "(C) 5",
        "(D) 6",
    ]
    if with_key:
        lines += ["", "ANSWER KEY", "1. (B)", "2. (B)"]
    y = 20
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 56
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_parse_image_with_key_answers_both_questions() -> None:
    matched, report, debug = parse_image_bytes(_mcq_image_png(), "probe-image")
    assert debug["is_digital"] is False
    assert debug["page_count"] == 1
    assert debug["psm_by_page"] == {"1": 3}
    assert matched.counts["questions"] == 2
    assert matched.answered == 2
    assert all(q.correct_index == 1 for q in matched.questions)
    assert all(q.answer_source == "trailing-key" for q in matched.questions)
    assert report["counts"]["answered"] == 2


def test_parse_image_without_key_leaves_questions_pending() -> None:
    # No key, no marks: the questions are found with all 4 options
    # but stay pending — never guessed.
    matched, _, _ = parse_image_bytes(_mcq_image_png(with_key=False), "probe-image")
    assert matched.counts["questions"] == 0
    assert len(matched.pending) == 2
    assert [p["number"] for p in matched.pending] == [1, 2]
    assert all(len(p["options"]) == 4 for p in matched.pending)


def test_parse_image_rejects_non_image_bytes() -> None:
    with pytest.raises(ValueError, match="JPEG or PNG"):
        parse_image_bytes(b"hello, not an image", "probe-image")


def test_parse_image_rejects_corrupt_png() -> None:
    with pytest.raises(ValueError, match="could not be decoded"):
        parse_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "probe-image")


def test_parse_image_jpeg_accepted() -> None:
    png = _mcq_image_png(with_key=False)
    image = Image.open(io.BytesIO(png))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=92)
    matched, _, debug = parse_image_bytes(buffer.getvalue(), "probe-image-jpg")
    assert debug["page_count"] == 1
    assert len(matched.pending) == 2


# --- API -----------------------------------------------------------------


def test_parse_image_endpoint_returns_resolved_mcqs(client) -> None:
    resp = client.post(
        "/api/v1/documents/parse-image",
        files={"file": ("page.png", _mcq_image_png(), "image/png")},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_digital"] is False
    assert body["page_count"] == 1
    assert body["matched"]["counts"]["questions"] == 2
    assert body["matched"]["answered"] == 2
    # Without a database the parse still returns, unpersisted.
    assert body["persisted"] is False


def test_parse_image_endpoint_rejects_text_file(client) -> None:
    resp = client.post(
        "/api/v1/documents/parse-image",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers=auth_headers("token-user-a"),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_file"


def test_parse_image_endpoint_requires_auth(client) -> None:
    resp = client.post(
        "/api/v1/documents/parse-image",
        files={"file": ("page.png", _mcq_image_png(), "image/png")},
    )
    assert resp.status_code == 401
