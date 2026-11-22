# OfficerPath AI — Phase 1, M8
# Acceptance-surface tests: the three acceptance files end to end
# through the PUBLIC API (sync parse / parse-image endpoints), with
# the values the M6/M7 benchmarks measured on this VM. These are
# the files the owner will test on his own phone (STOP CONDITION),
# so the suite must cover them — until M8 they were only exercised
# by the benchmark scripts, never by pytest.
#
# Expected values are the measured ones, not aspirations:
# - PPSC-66 PDF: 7 pages, 41 questions, 41 answered (M6/M7).
# - Computer table photo (Q67-81): 0 questions, 2 pending — live
#   Tesseract does not recover this ruled table (M7 §2/§3). The
#   test pins the honest outcome; a future OCR improvement must
#   update it with a new measurement, not a guess.
# - Paper 60 photo: 4 questions, 4 answered, 9 pending (M7 §2/§3).
#
# These tests are slow (~3 min total: PPSC-66 single-path OCR is
# ~130 s on this VM). They run the real Tesseract binary, so they
# fail without it — same as the existing OCR tests (CI installs
# tesseract-ocr + eng/urd, see .github/workflows/ci.yml).

import warnings
from pathlib import Path

from starlette.testclient import StarletteDeprecationWarning

from app.tests.conftest import auth_headers

FIX = Path(__file__).resolve().parent / "fixtures/golden/ppsc66"
FLUTTER_FIX = Path("~/workspace/officerpath-ai/test-fixtures/ppsc66").expanduser()
PPSC66_PDF = FLUTTER_FIX / "ppsc_paper_66.pdf"
TABLE_PHOTO = FLUTTER_FIX / "table-computer-q67-81-resent-20261121.jpg"
PAPER60_PHOTO = FIX / "paper60-photo.jpg"

# The sync parse of a 7-page scan takes ~130 s; the TestClient's
# default httpx timeout (5 s) would kill it. Passing an explicit
# timeout is deprecated by starlette (it warns), so the warning is
# silenced locally — the timeout itself is required, not optional.
LONG_TIMEOUT = 900


def _post_long(client, url: str, files: dict, headers: dict):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", StarletteDeprecationWarning)
        return client.post(url, files=files, headers=headers, timeout=LONG_TIMEOUT)


def test_acceptance_ppsc66_pdf_via_parse_endpoint(client) -> None:
    with PPSC66_PDF.open("rb") as fh:
        resp = _post_long(
            client,
            "/api/v1/documents/parse",
            files={"file": ("ppsc_paper_66.pdf", fh, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_digital"] is False
    assert body["page_count"] == 7
    assert body["persisted"] is False  # no DATABASE_URL in tests
    matched = body["matched"]
    assert matched["counts"]["questions"] == 41
    assert matched["answered"] == 41
    assert matched["counts"]["pending"] == 27
    # Every answered question carries its evidence trail.
    answered = [q for q in matched["questions"] if q["status"] == "answered"]
    assert len(answered) == 41
    assert all(q["answer_source"] for q in answered)


def test_acceptance_computer_table_photo_via_parse_image(client) -> None:
    with TABLE_PHOTO.open("rb") as fh:
        resp = _post_long(
            client,
            "/api/v1/documents/parse-image",
            files={"file": ("table.jpg", fh, "image/jpeg")},
            headers=auth_headers("token-user-a"),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_digital"] is False
    assert body["page_count"] == 1
    matched = body["matched"]
    assert matched["counts"]["questions"] == 0
    assert len(matched["pending"]) == 2


def test_acceptance_paper60_photo_via_parse_image(client) -> None:
    with PAPER60_PHOTO.open("rb") as fh:
        resp = _post_long(
            client,
            "/api/v1/documents/parse-image",
            files={"file": ("paper60.jpg", fh, "image/jpeg")},
            headers=auth_headers("token-user-a"),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_digital"] is False
    assert body["page_count"] == 1
    matched = body["matched"]
    assert matched["counts"]["questions"] == 4
    assert matched["answered"] == 4
    assert len(matched["pending"]) == 9
