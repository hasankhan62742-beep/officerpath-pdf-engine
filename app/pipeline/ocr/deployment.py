# OfficerPath AI — PDF Engine (Phase 1, M4)
# Deployment-aware OCR routing (ADR-006).
#
# M3 measured PaddleOCR at 1,775-3,667 MB peak RSS per page with OOM
# kills (exit 137) on full-resolution phone photos — 7x the Render
# free 512 MB budget. The M3 router was deployment-blind: it preferred
# PaddleOCR whenever the package was available, which would OOM the
# Stage-1 service. This module is the gate: a deployment profile
# carries a memory budget, and PaddleOCR is allowed only when the
# budget fits its measured worst-case peak. The gate is checked in
# the router (defence in depth: even a registered + available
# PaddleOCR is never selected on a profile that cannot run it), and
# every exclusion carries a human-readable reason that the service
# logs and records on the page result.

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings

# PaddleOCR's measured worst-case peak RSS (M3 benchmark, VM):
# 3,667 MB on synthetic clean pages, 1,775-1,782 MB on real PPSC-66
# pages. The gate requires a >= 4 GB budget so the worst measured
# peak fits with headroom. A 2 GB budget would pass the real-page
# peaks but not the synthetic worst case, so it does not pass.
PADDLEOCR_MIN_MEMORY_MB = 4096

# Memory budgets per deployment profile (MB). Render free is 512 MB
# (ADR-001, verified). Hostinger KVM 1 (Stage 2) is 4 GB. "local" is
# this dev VM (8 GB).
PROFILE_MEMORY_BUDGET_MB: dict[str, int] = {
    "render-free": 512,
    "vps": 4096,
    "local": 8192,
}


@dataclass(frozen=True)
class DeploymentProfile:
    """One deployment's resource budget for OCR routing."""

    name: str
    memory_budget_mb: int
    paddleocr_enabled: bool = True

    @property
    def paddleocr_allowed(self) -> bool:
        """True only when the flag is on AND the budget fits the
        measured PaddleOCR peak. Either condition failing excludes it."""
        return self.paddleocr_enabled and self.memory_budget_mb >= PADDLEOCR_MIN_MEMORY_MB

    def paddleocr_exclusion_reason(self) -> str | None:
        """Human-readable reason PaddleOCR is excluded, or None when
        it is allowed. The service logs this verbatim."""
        if not self.paddleocr_enabled:
            return "PaddleOCR disabled by PADDLEOCR_ENABLED=false"
        if self.memory_budget_mb < PADDLEOCR_MIN_MEMORY_MB:
            return (
                f"memory budget {self.memory_budget_mb} MB < PaddleOCR "
                f"minimum {PADDLEOCR_MIN_MEMORY_MB} MB "
                f"(M3 measured peak RSS 1,775-3,667 MB)"
            )
        return None


def deployment_profile(
    name: str,
    *,
    paddleocr_enabled: bool = True,
    memory_budget_mb: int | None = None,
) -> DeploymentProfile:
    """Build a profile by name. An unknown name raises ValueError
    (fail loudly — a typo must not silently route to a wrong budget).
    `memory_budget_mb` overrides the profile default when given."""
    if name not in PROFILE_MEMORY_BUDGET_MB:
        raise ValueError(
            f"unknown deployment profile {name!r}; "
            f"known profiles: {sorted(PROFILE_MEMORY_BUDGET_MB)}"
        )
    budget = memory_budget_mb if memory_budget_mb is not None else PROFILE_MEMORY_BUDGET_MB[name]
    return DeploymentProfile(
        name=name,
        memory_budget_mb=budget,
        paddleocr_enabled=paddleocr_enabled,
    )


def deployment_profile_from_settings(settings: Settings) -> DeploymentProfile:
    """The profile for the current process, from Settings."""
    return deployment_profile(
        settings.deployment_profile,
        paddleocr_enabled=settings.paddleocr_enabled,
        memory_budget_mb=settings.memory_budget_mb,
    )


def deployment_exclusions(
    available_engines: list[str],
    deployment: DeploymentProfile | None,
) -> dict[str, str]:
    """Engines that must NOT be selected under this deployment, with
    reasons. Empty when there is no deployment (M3 behaviour) or
    nothing is excluded. Currently only PaddleOCR has a gate; the
    digital extractor and Tesseract fit every profile (Tesseract
    peak 228.7 MB < 512 MB, M3)."""
    if deployment is None:
        return {}
    excluded: dict[str, str] = {}
    if "paddleocr" in available_engines and not deployment.paddleocr_allowed:
        reason = deployment.paddleocr_exclusion_reason()
        excluded["paddleocr"] = reason or "excluded by deployment profile"
    return excluded
