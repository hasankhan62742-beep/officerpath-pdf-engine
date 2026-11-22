# OfficerPath AI — PDF Engine (Phase 1, M7)
# In-memory metrics (ADR-009): counters + per-stage durations,
# rendered as Prometheus-style plain text by GET /metrics.
#
# Deliberately dependency-free and process-local: Render free is
# one instance (ADR-001), so in-process counters are the true
# counts for the deployment shape. The /metrics handler ALSO
# queries the database for live jobs-by-status when DATABASE_URL
# is configured, so a restarted process still reports the real
# job distribution. No metric ever carries user ids, file names,
# OCR text, or any per-document content — labels are aggregates
# only (status, engine, stage, error code).

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_stage_seconds: dict[str, float] = defaultdict(float)
_stage_calls: dict[str, int] = defaultdict(int)


def _key(name: str, labels: dict[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (name, tuple(sorted((labels or {}).items())))


def inc(name: str, labels: dict[str, str] | None = None, amount: int = 1) -> None:
    """Increment a counter (e.g. inc("jobs_total", {"status": "done"}))."""
    with _lock:
        _counters[_key(name, labels)] += amount


def observe_stage(stage: str, seconds: float) -> None:
    """Record one stage execution's duration (worker stage timings)."""
    with _lock:
        _stage_seconds[stage] += seconds
        _stage_calls[stage] += 1


def reset() -> None:
    """Clear all metrics (tests only — never call in production)."""
    with _lock:
        _counters.clear()
        _stage_seconds.clear()
        _stage_calls.clear()


def snapshot() -> dict:
    """A plain-dict snapshot (tests / benchmark harness)."""
    with _lock:
        return {
            "counters": {
                f"{name}{dict(labels)}": value for (name, labels), value in _counters.items()
            },
            "stage_seconds": dict(_stage_seconds),
            "stage_calls": dict(_stage_calls),
        }


def _fmt_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels)
    return "{" + inner + "}"


def render() -> str:
    """Render all metrics as Prometheus-style plain text."""
    lines: list[str] = []
    with _lock:
        counters = dict(_counters)
        stage_seconds = dict(_stage_seconds)
        stage_calls = dict(_stage_calls)
    seen: set[str] = set()
    for (name, labels), value in sorted(counters.items()):
        if name not in seen:
            lines.append(f"# HELP {name} Total count of {name}.")
            lines.append(f"# TYPE {name} counter")
            seen.add(name)
        lines.append(f"{name}{_fmt_labels(labels)} {value}")
    if stage_seconds or stage_calls:
        lines.append(
            "# HELP officerpath_stage_seconds_total Total seconds spent in each pipeline stage."
        )
        lines.append("# TYPE officerpath_stage_seconds_total counter")
        for stage in sorted(set(stage_seconds) | set(stage_calls)):
            lines.append(
                f'officerpath_stage_seconds_total{{stage="{stage}"}} '
                f"{stage_seconds.get(stage, 0.0):.3f}"
            )
        lines.append("# HELP officerpath_stage_calls_total Pipeline stage executions.")
        lines.append("# TYPE officerpath_stage_calls_total counter")
        for stage in sorted(set(stage_seconds) | set(stage_calls)):
            lines.append(
                f'officerpath_stage_calls_total{{stage="{stage}"}} {stage_calls.get(stage, 0)}'
            )
    return "\n".join(lines) + "\n"
