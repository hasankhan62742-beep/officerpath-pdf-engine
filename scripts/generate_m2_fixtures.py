"""Generate M2 test fixtures programmatically (deterministic).

Run from the repo root:  .venv/bin/python scripts/generate_m2_fixtures.py

Outputs (all under app/tests/fixtures/m2/):
- clean.pdf: 2 pages of digital text (page 2 is two-column) + drawn marks
- scanned.pdf: page 1 of clean.pdf rendered to an image and embedded (no text layer)
- mixed.pdf: page 1 digital, page 2 image-only
- skewed.pdf: clean page 1 rotated 5 degrees, embedded as an image
- low_contrast.pdf: light-grey digital text on white
- noisy.pdf: clean page 1 render + Gaussian noise, embedded as an image
- blank.pdf: one empty page
- manifest.json: per-file kind + mark bboxes (PDF points AND render
  pixels at 200 DPI) so tests can check mark preservation exactly.

Marks are drawn with vector graphics so their bboxes are known:
highlight (yellow rect), tick (polyline), star (polygon), circle,
underline. The PPSC-66 real pages are NOT generated here — they are
copied (read-only) from the Flutter repo into app/tests/fixtures/ppsc66/
with a PROVENANCE.md; see scripts/copy_ppsc66_fixtures.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "tests" / "fixtures" / "m2"
DPI = 200
SCALE = DPI / 72.0  # PDF points -> render pixels at 200 DPI

QUESTIONS = [
    ("1. What is the capital of Pakistan?", ["Karachi", "Lahore", "Islamabad", "Quetta"]),
    ("2. Which river flows through Lahore?", ["Indus", "Ravi", "Chenab", "Jhelum"]),
    ("3. The largest desert of Pakistan is?", ["Thar", "Cholistan", "Kharan", "Naran"]),
    ("4. Who wrote the national anthem?", ["Iqbal", "Hafeez Jalandhari", "Faiz", "Ghalib"]),
]


def _mcq_page(page: fitz.Page, two_column: bool = False) -> dict:
    """Draw MCQs + marks on one page. Returns mark bboxes in points."""
    marks: dict[str, list[float]] = {}
    title = "Model Paper — General Knowledge (fixture)"
    page.insert_text((72, 72), title, fontsize=16, fontname="helv")
    page.draw_line((72, 84), (523, 84), color=(0, 0, 0), width=1)
    y = 120.0
    x_columns = [72, 310] if two_column else [72]
    per_column = 2 if two_column else 4
    for col, x0 in enumerate(x_columns):
        yy = y
        for qi in range(col * per_column, min((col + 1) * per_column, 4)):
            stem, options = QUESTIONS[qi]
            page.insert_text((x0, yy), stem, fontsize=11, fontname="helv")
            if qi == 0:
                # Underline under the first stem.
                marks["underline"] = [x0, yy - 11, x0 + 210, yy + 2]
                page.draw_line((x0, yy + 2), (x0 + 210, yy + 2), color=(0, 0, 0), width=1)
            yy += 18
            for oi, option in enumerate(options):
                label = chr(ord("A") + oi)
                oy = yy
                if qi == 0 and oi == 1:
                    # Yellow highlight behind option B of Q1. The rect
                    # is drawn BEFORE the text, so the text is drawn
                    # once, on top. (M3 fix: the old code drew the
                    # rect over the text and re-inserted the text,
                    # which duplicated "(B) Lahore" in the text layer
                    # and broke digital ground truth.)
                    rect = fitz.Rect(x0 + 8, oy - 12, x0 + 130, oy + 4)
                    page.draw_rect(rect, color=(1, 1, 0), fill=(1, 1, 0))
                    marks["highlight"] = [rect.x0, rect.y0, rect.x1, rect.y1]
                page.insert_text((x0 + 12, oy), f"({label}) {option}", fontsize=11, fontname="helv")
                if qi == 1 and oi == 2:
                    # Tick mark left of option C of Q2.
                    tick = [(x0 - 2, oy - 6), (x0 + 3, oy - 1), (x0 + 10, oy - 10)]
                    page.draw_polyline(tick, color=(0, 0, 0), width=2)
                    marks["tick"] = [x0 - 4, oy - 12, x0 + 12, oy + 1]
                if qi == 2 and oi == 0:
                    # Star next to option A of Q3.
                    cx, cy, r = x0 + 4, oy - 6, 7
                    points = []
                    for k in range(10):
                        ang = -math.pi / 2 + k * math.pi / 5
                        rr = r if k % 2 == 0 else r * 0.45
                        points.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
                    page.draw_polyline(points + [points[0]], color=(0, 0, 0), width=1)
                    marks["star"] = [cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1]
                if qi == 3 and oi == 0:
                    # Circle around option A of Q4.
                    rect = fitz.Rect(x0 + 8, oy - 12, x0 + 150, oy + 4)
                    page.draw_oval(rect, color=(0, 0, 0), width=1.5)
                    marks["circle"] = [rect.x0, rect.y0, rect.x1, rect.y1]
                yy += 16
            yy += 14
    return marks


def _to_px(bbox: list[float]) -> list[int]:
    return [int(round(v * SCALE)) for v in bbox]


def _render_page_to_png(doc: fitz.Document, page_no: int, dpi: int = DPI) -> bytes:
    page = doc[page_no]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
    return pix.tobytes("png")


def _image_pdf(
    png_bytes: bytes, out_path: Path, rotate_deg: float = 0.0, noise_sigma: float = 0.0
) -> None:
    """Embed a PNG as a full-page image PDF (no text layer). Optional
    rotation / noise is applied to the pixels first."""
    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if noise_sigma > 0:
        rng = np.random.default_rng(42)  # deterministic
        noise = rng.normal(0, noise_sigma, image.shape).astype(np.float32)
        image = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if rotate_deg:
        height, width = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), rotate_deg, 1.0)
        image = cv2.warpAffine(
            image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255)
        )
    # JPEG (quality 92) keeps the fixture repo small: the same render
    # as PNG is ~11 MB, as JPEG ~0.3 MB, with no visible difference
    # for classification/quality measurements.
    _, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=bytes(buffer))
    doc.save(out_path)
    doc.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"dpi": DPI, "files": {}}

    # --- clean.pdf: digital text, 2 pages, marks on page 1 ---
    doc = fitz.open()
    marks_p1 = _mcq_page(doc.new_page(width=595, height=842), two_column=False)
    _mcq_page(doc.new_page(width=595, height=842), two_column=True)
    clean_path = OUT / "clean.pdf"
    doc.save(clean_path)
    manifest["files"]["clean.pdf"] = {
        "kind": "digital",
        "pages": 2,
        "marks_page_1": {
            kind: {"points": bbox, "pixels_at_200dpi": _to_px(bbox)}
            for kind, bbox in marks_p1.items()
        },
    }
    clean_png = _render_page_to_png(doc, 0)
    doc.close()

    # --- scanned.pdf: image-only version of clean page 1 ---
    _image_pdf(clean_png, OUT / "scanned.pdf")
    manifest["files"]["scanned.pdf"] = {
        "kind": "scanned",
        "pages": 1,
        "marks_page_1": "same as clean.pdf",
    }

    # --- mixed.pdf: digital page 1 + image-only page 2 ---
    _array = np.frombuffer(clean_png, dtype=np.uint8)
    _img = cv2.imdecode(_array, cv2.IMREAD_COLOR)
    _, _jpg = cv2.imencode(".jpg", _img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    doc = fitz.open()
    _mcq_page(doc.new_page(width=595, height=842), two_column=False)
    page2 = doc.new_page(width=595, height=842)
    page2.insert_image(page2.rect, stream=bytes(_jpg))
    doc.save(OUT / "mixed.pdf")
    doc.close()
    manifest["files"]["mixed.pdf"] = {"kind": "mixed", "pages": 2}

    # --- skewed.pdf: clean page 1 rotated +5 degrees ---
    _image_pdf(clean_png, OUT / "skewed.pdf", rotate_deg=5.0)
    manifest["files"]["skewed.pdf"] = {"kind": "scanned", "pages": 1, "skew_degrees": 5.0}

    # --- low_contrast.pdf: light-grey digital text ---
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (72, 72),
        "Model Paper — General Knowledge (fixture)",
        fontsize=16,
        fontname="helv",
        color=(0.78, 0.78, 0.78),
    )
    y = 120.0
    for stem, options in QUESTIONS:
        page.insert_text((72, y), stem, fontsize=11, fontname="helv", color=(0.78, 0.78, 0.78))
        y += 18
        for oi, option in enumerate(options):
            page.insert_text(
                (84, y),
                f"({chr(ord('A') + oi)}) {option}",
                fontsize=11,
                fontname="helv",
                color=(0.78, 0.78, 0.78),
            )
            y += 16
        y += 14
    doc.save(OUT / "low_contrast.pdf")
    doc.close()
    manifest["files"]["low_contrast.pdf"] = {
        "kind": "digital",
        "pages": 1,
        "note": "light-grey text (0.78)",
    }

    # --- noisy.pdf: clean page 1 + Gaussian noise (sigma 18) ---
    _image_pdf(clean_png, OUT / "noisy.pdf", noise_sigma=18.0)
    manifest["files"]["noisy.pdf"] = {"kind": "scanned", "pages": 1, "noise_sigma": 18.0}

    # --- blank.pdf: one empty page ---
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(OUT / "blank.pdf")
    doc.close()
    manifest["files"]["blank.pdf"] = {"kind": "blank", "pages": 1}

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for name in sorted(manifest["files"]):
        print(f"wrote {name}")
    print(f"manifest: {OUT / 'manifest.json'}")


if __name__ == "__main__":
    main()
