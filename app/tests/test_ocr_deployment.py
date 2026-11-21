# OfficerPath AI — Phase 1, M4
# Deployment-aware OCR routing (ADR-006): PaddleOCR must never be
# selected on a profile whose memory budget is below its measured
# peak (M3: 1,775-3,667 MB; gate minimum 4,096 MB).

import pytest

from app.config import Settings
from app.pipeline.ocr.deployment import (
    PADDLEOCR_MIN_MEMORY_MB,
    deployment_exclusions,
    deployment_profile,
    deployment_profile_from_settings,
)
from app.pipeline.ocr.router import route_page

ALL_ENGINES = ["digital-pymupdf", "paddleocr", "tesseract"]


def test_render_free_profile_budget_is_512():
    profile = deployment_profile("render-free")
    assert profile.memory_budget_mb == 512
    assert profile.name == "render-free"


def test_vps_profile_budget_is_4096():
    assert deployment_profile("vps").memory_budget_mb == 4096


def test_local_profile_budget_is_8192():
    assert deployment_profile("local").memory_budget_mb == 8192


def test_unknown_profile_fails_loudly():
    with pytest.raises(ValueError, match="unknown deployment profile"):
        deployment_profile("render-pro")


def test_memory_budget_override_is_respected():
    profile = deployment_profile("render-free", memory_budget_mb=8192)
    assert profile.memory_budget_mb == 8192
    assert profile.paddleocr_allowed


def test_paddleocr_gate_minimum_is_above_measured_peak():
    # M3 worst measured peak: 3,667 MB. The gate must exceed it.
    assert PADDLEOCR_MIN_MEMORY_MB == 4096
    assert PADDLEOCR_MIN_MEMORY_MB > 3667


def test_render_free_excludes_paddleocr_with_reason():
    profile = deployment_profile("render-free")
    assert not profile.paddleocr_allowed
    reason = profile.paddleocr_exclusion_reason()
    assert reason is not None
    assert "512 MB" in reason and "4096 MB" in reason
    assert deployment_exclusions(ALL_ENGINES, profile) == {"paddleocr": reason}


def test_vps_allows_paddleocr():
    profile = deployment_profile("vps")
    assert profile.paddleocr_allowed
    assert profile.paddleocr_exclusion_reason() is None
    assert deployment_exclusions(ALL_ENGINES, profile) == {}


def test_local_allows_paddleocr():
    assert deployment_profile("local").paddleocr_allowed


def test_flag_off_excludes_paddleocr_everywhere():
    for name in ("render-free", "vps", "local"):
        profile = deployment_profile(name, paddleocr_enabled=False)
        assert not profile.paddleocr_allowed
        assert "PADDLEOCR_ENABLED=false" in (profile.paddleocr_exclusion_reason() or "")


def test_route_scanned_render_free_falls_back_to_tesseract():
    profile = deployment_profile("render-free")
    assert route_page("scanned", ALL_ENGINES, deployment=profile) == ["tesseract"]


def test_route_scanned_vps_prefers_paddleocr():
    profile = deployment_profile("vps")
    assert route_page("scanned", ALL_ENGINES, deployment=profile) == ["paddleocr"]


def test_route_mixed_render_free_runs_digital_plus_tesseract():
    profile = deployment_profile("render-free")
    assert route_page("mixed", ALL_ENGINES, deployment=profile) == [
        "digital-pymupdf",
        "tesseract",
    ]


def test_route_without_deployment_keeps_m3_behaviour():
    # No deployment given: PaddleOCR still preferred (offline tooling
    # and the pre-M4 callers). The gate only applies when a profile
    # is supplied.
    assert route_page("scanned", ALL_ENGINES) == ["paddleocr"]


def test_no_exclusions_without_deployment():
    assert deployment_exclusions(ALL_ENGINES, None) == {}


def test_profile_from_settings_render_free():
    settings = Settings(deployment_profile="render-free", paddleocr_enabled=True)
    profile = deployment_profile_from_settings(settings)
    assert profile.name == "render-free"
    assert not profile.paddleocr_allowed


def test_profile_from_settings_unknown_name_raises():
    settings = Settings(deployment_profile="no-such-profile")
    with pytest.raises(ValueError, match="unknown deployment profile"):
        deployment_profile_from_settings(settings)
