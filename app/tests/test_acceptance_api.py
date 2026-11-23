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
# Fixtures are repo-relative (fixtures/golden/ppsc66, next to this
# file) so the suite is self-contained on GitHub Actions — the
# earlier absolute ~/workspace/officerpath-ai path exists only on
# the dev VM and broke CI with FileNotFoundError (2026-11-23).
# The Paper 60 pending count is OCR-segmentation sensitive (VM
# measures 9, the GitHub runner 11 on the same file), so that one
# count is a range, not an exact number — the exact invariants are
# the answered questions and the shape of the pending items.
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
PPSC66_PDF = FIX / "ppsc_paper_66.pdf"
TABLE_PHOTO = FIX / "table-computer-q67-81-resent-20261121.jpg"
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
    # The 4 star-marked questions resolve on every Tesseract build
    # measured (VM 5.3.4 and the GitHub runner): 4 found, 4 answered.
    assert matched["counts"]["questions"] == 4
    assert matched["answered"] == 4

    # The three clean-English star-marked answers must resolve to
    # the exact option text — this is the ground truth the star
    # marks carry, not an OCR-count artefact.
    def _answered(fragment: str) -> dict:
        hits = [q for q in matched["questions"] if fragment in (q["text"] or "")]
        assert len(hits) == 1, fragment
        return hits[0]

    q = _answered("A computer on network is identified by its")
    assert q["correct_index"] == 2 and q["options"][2] == "IP Address"
    q = _answered("generally used in architectural design")
    assert q["correct_index"] == 2 and q["options"][2] == "Auto CAD"
    q = _answered("Another name for free software")
    assert q["correct_index"] == 3 and q["options"][3] == "Public Domain Software"
    assert all(q["answer_source"] == "style-star" for q in matched["questions"])
    # Pending (unresolved question-like fragments) is
    # OCR-segmentation sensitive — VM measures 9, the GitHub runner
    # measures 11 on the same file — so it is pinned as a range
    # that brackets both measured environments, with its shape
    # pinned exactly: every pending item is an unanswered
    # 4-option fragment.
    pending = matched["pending"]
    assert 8 <= len(pending) <= 12
    assert matched["counts"]["pending"] == len(pending)
    assert all(p["reason"] == "no-key-entry" for p in pending)
    assert all(len(p["options"]) == 4 for p in pending)
