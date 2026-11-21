# OfficerPath AI — PDF Engine (Phase 1, M3)
# Gemini advisory provider (prompt §15, ADR-002): the OPTIONAL AI
# route. It is DISABLED by default and suggestions-only by design:
# it NEVER produces a verified answer and NEVER overwrites original
# content. A suggestion is stored separately, labelled SUGGESTION,
# and only a human (or M6 review) may promote it.
#
# Activation needs TWO things: gemini_advisory_enabled=True in
# settings AND a server key in the environment (GEMINI_API_KEY —
# never in code). With either missing, suggest() returns
# {"status": "disabled"} / {"status": "no_key"} and touches NO
# network. No server key is provisioned in Phase 1 (owner: deferred)
# and NO live Gemini call is made in M3 — the enabled path is
# UNVERIFIED by design and labelled as such wherever it is described.
#
# The OCR prompt below is VERBATIM the Flutter app's prompt
# (lib/services/urdu_ocr.dart GeminiVisionOcr, and
# test-fixtures/ppsc66/gemini_vision_ocr.py) — the only prompt with a
# measured 100/100 behind it (PPSC-66 VM baseline, 20 Nov 2026).
# Model: gemini-3.5-flash-lite (gemini-2.5-flash-lite returns HTTP 404,
# tested 19 Nov 2026 — must not be used).
#
# Recitation-filter risk (measured on the VM baseline: the filter
# blocked PPSC-66 pp. 3/5): build_ocr_request() + plan_crop_retry()
# design the mitigation in from the start — a blocked full-page call
# is retried on column crops, and unreadable words are marked [?],
# never guessed. The mitigation is DESIGNED here; it is unproven
# server-side until a key exists and a live call is made (M3 does
# neither).

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass

import httpx
from PIL import Image

# Verbatim Flutter-app OCR prompt (see module docstring).
OCR_PROMPT_BASELINE = (
    "Transcribe ALL text on this scanned book page EXACTLY as printed, "
    "line by line, in reading order (left column first, then right "
    "column). Keep Urdu script as Urdu script and English as English. "
    "Do not correct, translate, summarise or add anything. If a word "
    "is unreadable, write [?] for it."
)
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
# The Flutter baseline resizes to 1000 px wide, JPEG quality 88.
VISION_IMAGE_WIDTH = 1000
VISION_IMAGE_QUALITY = 88


@dataclass
class CallRecord:
    """One advisory call, for the audit log: cost + latency (prompt
    §15). Cost is None on the free tier (no billing) — recorded as
    such, never invented."""

    status: str
    latency_ms: float
    cost_usd: float | None = None
    model: str = GEMINI_MODEL
    prompt_chars: int = 0


class GeminiAdvisoryProvider:
    """AIAssistProvider backed by Gemini generateContent. Disabled by
    default; see the module docstring for the activation rules."""

    name = "gemini-advisory"

    def __init__(
        self,
        *,
        enabled: bool = False,
        api_key: str | None = None,
        model: str = GEMINI_MODEL,
        max_calls_per_day: int = 0,
        max_output_tokens: int = 2048,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.enabled = enabled
        self._api_key = api_key
        self.model = model
        self.max_calls_per_day = max_calls_per_day
        self.max_output_tokens = max_output_tokens
        self._transport = transport
        self._calls_today = 0
        self._call_log: list[CallRecord] = []

    @property
    def calls_today(self) -> int:
        return self._calls_today

    @property
    def call_log(self) -> list[CallRecord]:
        return list(self._call_log)

    def suggest(self, prompt: str, context: dict) -> dict:
        """One advisory call. Returns a status dict; 'suggestion'
        carries the model text. Never raises for a disabled / unkeyed
        / over-budget provider — those are statuses, not exceptions.
        Network + API errors are returned as status 'error' with the
        message (the caller logs it); the suggestion is never a
        verified answer."""
        if not self.enabled:
            return {"status": "disabled", "reason": "gemini_advisory_enabled is False"}
        if not self._api_key:
            return {"status": "no_key", "reason": "no server Gemini key configured"}
        if self.max_calls_per_day <= 0:
            return {"status": "disabled", "reason": "gemini_max_calls_per_day is 0"}
        if self._calls_today >= self.max_calls_per_day:
            return {
                "status": "budget_exceeded",
                "reason": f"daily call budget reached ({self.max_calls_per_day})",
            }
        started = time.monotonic()
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=120.0,
                follow_redirects=False,  # a 3xx must not carry the key elsewhere
            ) as client:
                response = client.post(
                    f"{GEMINI_ENDPOINT}/{self.model}:generateContent",
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self._api_key,
                    },
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "maxOutputTokens": self.max_output_tokens,
                            "temperature": 0.0,
                        },
                    },
                )
        except Exception as exc:  # network failure: status, not exception
            record = CallRecord(
                status="error",
                latency_ms=(time.monotonic() - started) * 1000.0,
                prompt_chars=len(prompt),
            )
            self._call_log.append(record)
            return {"status": "error", "reason": f"Gemini request failed: {exc}"}
        latency_ms = (time.monotonic() - started) * 1000.0
        self._calls_today += 1
        if response.status_code != 200:
            record = CallRecord(status="error", latency_ms=latency_ms, prompt_chars=len(prompt))
            self._call_log.append(record)
            return {
                "status": "error",
                "reason": f"Gemini HTTP {response.status_code}: {response.text[:200]}",
            }
        try:
            text = "".join(
                part.get("text", "")
                for candidate in response.json().get("candidates", [])
                for part in candidate.get("content", {}).get("parts", [])
            )
        except Exception as exc:
            return {"status": "error", "reason": f"unparseable Gemini response: {exc}"}
        self._call_log.append(
            CallRecord(status="suggestion", latency_ms=latency_ms, prompt_chars=len(prompt))
        )
        return {
            "status": "suggestion",
            "suggestion": text,
            "model": self.model,
            "latency_ms": round(latency_ms, 1),
        }


def build_ocr_request(png_bytes: bytes, *, extra_instruction: str = "") -> dict:
    """Build (do NOT send) the Gemini vision-OCR request for one page:
    the verbatim baseline prompt + the page image resized to 1000 px
    wide as inline JPEG. `extra_instruction` is appended only when
    the verbatim prompt is blocked by the recitation filter — and the
    fact it was used is recorded by the caller. Pure function: no
    network, no key, fully testable."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    width, height = image.size
    if width > VISION_IMAGE_WIDTH:
        image = image.resize(
            (VISION_IMAGE_WIDTH, int(height * VISION_IMAGE_WIDTH / width)),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=VISION_IMAGE_QUALITY)
    prompt = OCR_PROMPT_BASELINE + (f" {extra_instruction}" if extra_instruction else "")
    return {
        "model": GEMINI_MODEL,
        "prompt": prompt,
        "prompt_is_baseline": not extra_instruction,
        "image": {
            "mime_type": "image/jpeg",
            "data_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "width_px": image.width,
            "height_px": image.height,
        },
    }


def plan_crop_retry(
    png_bytes: bytes, *, columns: list[tuple[float, float]] | None = None
) -> list[dict]:
    """Recitation-filter mitigation, designed (not yet proven
    server-side): split one page into column crops and build one OCR
    request per crop. `columns` are (x_min, x_max) fractions from the
    layout analyser; without them the page is split 50/50. Each crop
    is a separate request dict (same prompt, cropped image). The
    caller sends them only when the full-page call was blocked."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    width, height = image.size
    splits = columns or [(0.0, 0.5), (0.5, 1.0)]
    requests: list[dict] = []
    for index, (x_min, x_max) in enumerate(splits):
        left = max(0, int(width * x_min))
        right = min(width, int(width * x_max))
        if right - left < 50:  # a sliver is not a readable crop
            continue
        crop = image.crop((left, 0, right, height))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        requests.append(
            {
                "crop_index": index,
                "crop_bbox_fraction": (x_min, 0.0, x_max, 1.0),
                "request": build_ocr_request(buffer.getvalue()),
            }
        )
    return requests


class MockGeminiProvider:
    """Test double for the advisory provider: returns a canned
    suggestion, enforces the same budget rules, counts calls. Used
    by tests so no test ever touches the network or a key."""

    name = "gemini-advisory-mock"

    def __init__(self, *, canned: str = "mock suggestion", max_calls_per_day: int = 10) -> None:
        self.enabled = True
        self._canned = canned
        self.max_calls_per_day = max_calls_per_day
        self.calls_made = 0
        self._log: list[dict] = []

    def suggest(self, prompt: str, context: dict) -> dict:
        if self.calls_made >= self.max_calls_per_day:
            return {"status": "budget_exceeded", "reason": "daily call budget reached"}
        self.calls_made += 1
        self._log.append({"prompt": prompt, "context": context})
        return {"status": "suggestion", "suggestion": self._canned, "model": "mock"}
