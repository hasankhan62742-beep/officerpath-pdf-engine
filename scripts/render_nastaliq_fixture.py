# OfficerPath AI — Phase 1, M4
# Render a synthetic Urdu Nastaliq fixture (ground truth known
# exactly) so Tesseract's Nastaliq performance can be measured
# honestly instead of claimed. Font: Noto Nastaliq Urdu (installed
# on the VM, /usr/share/fonts/truetype/noto/). PIL renders with
# raqm/harfbuzz (verified present), so the Nastaliq shaping is real.
#
# Ground truth is the LINES list below, written verbatim to the
# .txt next to the PNG. The fixture mirrors the synthetic English
# MCQs (same 4 questions, translated) so Nastaliq CER is comparable
# to the Latin-script synthetic CER.
#
# Usage: .venv/bin/python scripts/render_nastaliq_fixture.py

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"
# Noto Nastaliq Urdu has NO Latin A-Z glyphs: "(A)" renders as .notdef
# boxes. Option markers are therefore drawn separately with a Latin
# font (DejaVu Sans), at the right end of the option line where the
# RTL marker belongs. Digits render in the Nastaliq font, so question
# numbers stay in the Urdu line.
LATIN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TITLE = "ماڈل پیپر — عمومی معلومات"
LINES = [
    "1. پاکستان کا دارالحکومت کون سا ہے؟",
    "(A) کراچی",
    "(B) لاہور",
    "(C) اسلام آباد",
    "(D) کوئٹہ",
    "2. لاہور سے کون سا دریا گزرتا ہے؟",
    "(A) سندھ",
    "(B) راوی",
    "(C) چناب",
    "(D) جہلم",
    "3. پاکستان کا سب سے بڑا صحرا کون سا ہے؟",
    "(A) تھر",
    "(B) چولستان",
    "(C) خاران",
    "(D) ناران",
    "4. قومی ترانہ کس نے لکھا؟",
    "(A) اقبال",
    "(B) حفیظ جالندھری",
    "(C) فیض",
    "(D) غالب",
]

OUT_DIR = Path("app/tests/fixtures/golden/synthetic-nastaliq")
WIDTH, HEIGHT = 1654, 2339  # A4 at 200 DPI


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(FONT, 44)
    body_font = ImageFont.truetype(FONT, 34)
    # Title, centred. Nastaliq is tall: generous line spacing.
    draw.text(
        (WIDTH // 2, 90),
        TITLE,
        font=title_font,
        fill="black",
        anchor="ma",
        direction="rtl",
        language="ur",
    )
    latin_font = ImageFont.truetype(LATIN_FONT, 34)
    y = 260
    for line in LINES:
        is_question = line[0].isdigit()
        if is_question:
            draw.text(
                (WIDTH - 150, y),
                line,
                font=body_font,
                fill="black",
                anchor="ra",
                direction="rtl",
                language="ur",
            )
        else:
            # Option line "(A) <urdu>": marker in Latin font at the
            # far right, Urdu word to its left.
            marker, _, urdu = line.partition(" ")
            draw.text(
                (WIDTH - 220, y + 8),
                marker,
                font=latin_font,
                fill="black",
                anchor="ra",
            )
            draw.text(
                (WIDTH - 220 - 60, y),
                urdu,
                font=body_font,
                fill="black",
                anchor="ra",
                direction="rtl",
                language="ur",
            )
        y += 100
    png_path = OUT_DIR / "nastaliq-p1.png"
    image.save(png_path)
    txt_path = OUT_DIR / "nastaliq-p1.txt"
    txt_path.write_text(TITLE + "\n" + "\n".join(LINES) + "\n", encoding="utf-8")
    print(f"wrote {png_path} ({WIDTH}x{HEIGHT})")
    print(f"wrote {txt_path} ({len(LINES) + 1} lines)")


if __name__ == "__main__":
    main()
