# OfficerPath AI — M15
# Confidence-gated PSM-4 retry, single-path wrapper tests
# (ADR-008 addendum). The OCR itself is mocked: the fake _ocr_page
# returns blocks whose word_confidences carry the mean confidence
# the test wants, so the trigger / keep / no-op decisions are
# exercised without the Tesseract binary. Multi-pass is covered
# separately: it calls _ocr_page directly (see
# test_matching_multipass.py), never this wrapper.

from app.pipeline.interfaces import BoundingBox, OCRBlock
from app.pipeline.matching import service as matching_service


def _blocks(mean_conf: float | None, tag: str) -> list[OCRBlock]:
    confs = {} if mean_conf is None else {f"{tag}#0": mean_conf}
    return [
        OCRBlock(
            text=tag,
            bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
            page_number=1,
            word_confidences=confs,
        )
    ]


def _fake_ocr_factory(calls: list, psm3_mean: float | None, psm4_mean: float | None):
    def fake(png_bytes, page_number, settings, *, psm, use_layout, analyzer=None):
        calls.append(psm)
        if psm == 3:
            return _blocks(psm3_mean, "psm3")
        return _blocks(psm4_mean, "psm4")

    return fake


def test_retry_triggers_below_85_and_keeps_better_psm4(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(matching_service, "_ocr_page", _fake_ocr_factory(calls, 81.8, 86.4))
    blocks, info = matching_service._ocr_page_single(b"png", 1, None, psm=3, use_layout=True)
    assert calls == [3, 4]
    assert info == {
        "retried": True,
        "kept": True,
        "mean_conf_psm3": 81.8,
        "mean_conf_psm4": 86.4,
    }
    assert blocks[0].text == "psm4"


def test_no_retry_at_or_above_85(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(matching_service, "_ocr_page", _fake_ocr_factory(calls, 92.5, 95.0))
    blocks, info = matching_service._ocr_page_single(b"png", 1, None, psm=3, use_layout=True)
    assert calls == [3]
    assert info["retried"] is False
    assert info["kept"] is False
    assert blocks[0].text == "psm3"


def test_retry_discards_psm4_when_not_strictly_better(monkeypatch) -> None:
    # Equal confidence (NOA p9: 84.1 vs 84.1) and worse confidence
    # both keep the PSM-3 blocks — margin 0 means strictly better.
    for psm4_mean in (84.1, 78.0):
        calls: list = []
        monkeypatch.setattr(
            matching_service, "_ocr_page", _fake_ocr_factory(calls, 84.1, psm4_mean)
        )
        blocks, info = matching_service._ocr_page_single(b"png", 1, None, psm=3, use_layout=True)
        assert calls == [3, 4]
        assert info == {
            "retried": True,
            "kept": False,
            "mean_conf_psm3": 84.1,
            "mean_conf_psm4": psm4_mean,
        }
        assert blocks[0].text == "psm3"


def test_no_retry_when_page_has_no_scored_words(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(matching_service, "_ocr_page", _fake_ocr_factory(calls, None, 90.0))
    blocks, info = matching_service._ocr_page_single(b"png", 1, None, psm=3, use_layout=True)
    assert calls == [3]
    assert info["retried"] is False
    assert info["mean_conf_psm3"] is None
    assert blocks[0].text == "psm3"


def test_psm4_input_is_never_retried(monkeypatch) -> None:
    # The wrapper is single-path only, but if it is ever called
    # with psm=4 (e.g. a psm_override), retrying with the same PSM
    # would be pointless — it returns the first pass as-is.
    calls: list = []
    monkeypatch.setattr(matching_service, "_ocr_page", _fake_ocr_factory(calls, 50.0, 90.0))
    blocks, info = matching_service._ocr_page_single(b"png", 1, None, psm=4, use_layout=True)
    assert calls == [4]
    assert info["retried"] is False
    assert blocks[0].text == "psm4"
