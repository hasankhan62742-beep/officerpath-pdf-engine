# OfficerPath AI — Phase 1, M3
# Gemini advisory provider: disabled by default, budget-capped, and
# the request builders (pure functions — no network, no key).
# NO test here touches the network or a real key.

import base64
import io

import httpx
from PIL import Image

from app.pipeline.ocr.gemini import (
    OCR_PROMPT_BASELINE,
    GeminiAdvisoryProvider,
    MockGeminiProvider,
    build_ocr_request,
    plan_crop_retry,
)


def _png_bytes(width=100, height=50, color=(255, 255, 255)):
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_disabled_by_default_returns_status():
    provider = GeminiAdvisoryProvider()
    assert provider.enabled is False
    result = provider.suggest("anything", {})
    assert result["status"] == "disabled"


def test_enabled_without_key_returns_no_key():
    provider = GeminiAdvisoryProvider(enabled=True, max_calls_per_day=10)
    assert provider.suggest("anything", {})["status"] == "no_key"


def test_zero_budget_is_disabled_even_with_key():
    provider = GeminiAdvisoryProvider(enabled=True, api_key="fake-key", max_calls_per_day=0)
    assert provider.suggest("anything", {})["status"] == "disabled"


def test_budget_enforced_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "suggestion text"}]}}]},
        )

    transport = httpx.MockTransport(handler)
    provider = GeminiAdvisoryProvider(
        enabled=True,
        api_key="fake-key",
        max_calls_per_day=1,
        transport=transport,
    )
    first = provider.suggest("prompt", {})
    assert first["status"] == "suggestion"
    assert first["suggestion"] == "suggestion text"
    assert provider.calls_today == 1
    second = provider.suggest("prompt", {})
    assert second["status"] == "budget_exceeded"


def test_http_error_is_status_not_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="quota exceeded")

    provider = GeminiAdvisoryProvider(
        enabled=True,
        api_key="fake-key",
        max_calls_per_day=5,
        transport=httpx.MockTransport(handler),
    )
    result = provider.suggest("prompt", {})
    assert result["status"] == "error"
    assert "429" in result["reason"]


def test_no_redirects_followed():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    provider = GeminiAdvisoryProvider(
        enabled=True,
        api_key="fake-key",
        max_calls_per_day=5,
        transport=httpx.MockTransport(handler),
    )
    result = provider.suggest("prompt", {})
    assert result["status"] == "error"
    assert seen == [
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
    ]


def test_build_ocr_request_uses_baseline_prompt_and_resizes():
    png = _png_bytes(width=2000, height=1000)
    request = build_ocr_request(png)
    assert request["prompt"] == OCR_PROMPT_BASELINE
    assert request["prompt_is_baseline"] is True
    assert request["model"] == "gemini-3.5-flash-lite"
    assert request["image"]["mime_type"] == "image/jpeg"
    assert request["image"]["width_px"] == 1000
    raw = base64.b64decode(request["image"]["data_base64"])
    assert raw[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_build_ocr_request_extra_instruction_is_flagged():
    request = build_ocr_request(_png_bytes(), extra_instruction="Use crops.")
    assert request["prompt_is_baseline"] is False
    assert "Use crops." in request["prompt"]


def test_plan_crop_retry_splits_page():
    requests = plan_crop_retry(_png_bytes(width=1000, height=500))
    assert len(requests) == 2
    assert requests[0]["crop_index"] == 0
    assert requests[1]["crop_index"] == 1
    for item in requests:
        assert item["request"]["prompt"] == OCR_PROMPT_BASELINE


def test_mock_provider_enforces_budget():
    mock = MockGeminiProvider(max_calls_per_day=1)
    assert mock.suggest("p", {})["status"] == "suggestion"
    assert mock.suggest("p", {})["status"] == "budget_exceeded"
    assert mock.calls_made == 1
