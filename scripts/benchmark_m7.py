# OfficerPath AI — M7 benchmark (2026-11-22).
#
# Measures the M7 pillars end to end, on THIS VM (labelled VM
# numbers — NOT Render numbers):
# - Accuracy re-run: the M6 numbers must reproduce (TestPoint,
#   Computer Q&A, CA40, Urdu NOA, PPSC-66 live, Paper 60 live).
#   Any change is reported, even zero.
# - Latency + peak RSS per fixture, before (profile runs, same VM,
#   same day — scripts/m7_profile.py) vs after this run.
# - Union-merge mode: recovery gain + cost on PPSC-66 (fresh
#   subprocess per arm, sampled concurrent tree RSS).
# - Job pipeline: queued -> done with stage timings, forced
#   failure + retry, cancel (queued and processing).
# - Security: per-user isolation, rate-limit behaviour, oversize
#   handling, secrets-grep result.
# - Observability: sample /health and /metrics output from a real
#   run, with the required metric names checked present.
# - Profile findings (Tesseract share, render, layout, pdfplumber)
#   and the DPI verdict, recorded as measured constants with
#   provenance (scripts/m7_profile.py, m7_dpi_experiment.py).
#
# No PaddleOCR (ADR-005). No Gemini API calls. The M6 calibration
# file is deleted first (stale-fit guard, same as M6) and rewritten
# from this run's own points at the end.
#
# Usage: .venv/bin/python scripts/benchmark_m7.py
# Output: docs/benchmarks/m7-benchmark-2026-11-22.json + stdout.
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Dummy Supabase config — set BEFORE importing the app, so
# Settings reads them at import time (same as the test conftest).
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_m5 import _peak_rss_mb  # noqa: E402
from benchmark_m6 import (  # noqa: E402
    CAL_OUT,
    FLUTTER_FIX,
    PPSC66_DIR,
    _calibration_points,
    _end_to_end_digital,
    _key_region_before_after,
    _load_ca40,
    _load_computer,
    _load_testpoint,
    _load_urdu_noa,
    _paper60_live,
    _ppsc66_key_gt,
    _score_qa,
)

from app.pipeline.matching.calibration import fit_calibration  # noqa: E402
from app.pipeline.matching.service import parse_document_bytes  # noqa: E402

OUT = Path("docs/benchmarks/m7-benchmark-2026-11-22.json")
DRIVER = Path("scripts/m7_parse_once.py")

# --- Measured BEFORE numbers (same VM, same day) -------------------
# scripts/m7_profile.py, unprofiled runs: PPSC-66 single-path
# 129.6s (self-RSS 430MB), TestPoint digital 21.3s, CA40 digital
# 0.1s. The profile also established the bottleneck split
# (cProfile, PPSC-66): Tesseract image_to_data ~120s of 129.6s
# (93%), render ~8.5s, layout ~0.00s/call (42 blocks), TestPoint
# digital time is inside pdfplumber/pdfminer (no cheap fix).
BEFORE_LATENCY = {
    "ppsc66_single_path_seconds": 129.6,
    "testpoint_digital_seconds": 21.3,
    "ca40_digital_seconds": 0.1,
    "ppsc66_tree_peak_mb": 459,
    "ppsc66_tree_peak_note": "sampled concurrent tree RSS, fresh "
    "process, scripts/m7_tree_rss.py (two runs: 459MB max; a third "
    "driver run measured 398MB — range 398-459MB, worst 459MB)",
}
# scripts/m7_dpi_experiment.py: 150 DPI is 33% faster (96.5s vs
# 144.5s) but LOSES recovery (35/100 vs 40/100, 34 vs 41
# answered) with all recovered answers still correct — a recall
# loss, not a correctness loss. Verdict: 200 DPI kept.
DPI_EXPERIMENT = {
    "dpi_200": {
        "seconds": 144.5,
        "questions": 41,
        "answered": 41,
        "recovered_of_100": 40,
        "answers_correct_vs_key": 40,
    },
    "dpi_150": {
        "seconds": 96.5,
        "questions": 35,
        "answered": 34,
        "recovered_of_100": 35,
        "answers_correct_vs_key": 35,
    },
    "verdict": "REJECTED 150 DPI — 33% faster but loses 5 recovered "
    "questions; recovery is the scarce resource on PPSC-66. "
    "200 DPI stays the production default.",
}


def _driver(args: list[str]) -> dict:
    """Run one parse in a fresh subprocess (m7_parse_once.py) and
    return its JSON. Raises on failure — a driver crash is a
    benchmark failure, never a silent zero."""
    proc = subprocess.run(
        [sys.executable, str(DRIVER), *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"m7_parse_once {args} failed:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _key_letter(entry_text: str) -> str | None:
    match = re.search(r"\(([A-D])\)", entry_text)
    return match.group(1) if match else None


def _job_pipeline_proof() -> dict:
    """Full queued -> done run with stage timings, a forced failure
    + retry, and a cancel — through the real HTTP + worker path
    (temp SQLite, fake auth, local disk storage)."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.api.v1.async_jobs as async_jobs_api
    import app.api.v1.review as review_api
    from app.config import settings
    from app.db import models as db
    from app.db.models import Base
    from app.main import app
    from app.security.rate_limit import rate_limiter
    from app.storage.local import LocalDiskStorage
    from app.tests.conftest import (
        FakeSupabaseClient,
        auth_headers,
    )
    from app.workers.processor import claim_next_job, process_job
    from app.workers.runner import run_once

    tmp = Path(tempfile.mkdtemp(prefix="m7-bench-jobs-"))
    engine = create_engine(f"sqlite:///{tmp}/jobs.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    async_jobs_api.get_session = lambda: factory()  # type: ignore[method-assign]
    review_api.get_session = lambda: factory()  # type: ignore[method-assign]
    settings.storage_root = str(tmp / "storage")
    rate_limiter.reset()
    ca40 = (PPSC66_DIR / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()
    proof: dict = {}
    with TestClient(app) as client:
        app.state.supabase_client = FakeSupabaseClient()
        app.state.service_client = app.state.supabase_client

        def submit(data: bytes, filename: str = "ca40.pdf") -> dict:
            res = client.post(
                "/api/v1/async-jobs/parse",
                files={"file": (filename, data, "application/pdf")},
                headers=auth_headers("token-user-a"),
            )
            assert res.status_code == 202, res.text
            return res.json()

        def status(job_id: str) -> dict:
            res = client.get(
                f"/api/v1/async-jobs/{job_id}",
                headers=auth_headers("token-user-a"),
            )
            assert res.status_code == 200, res.text
            return res.json()

        # Happy path: queued -> done, with stage timings.
        body = submit(ca40)
        job_id = body["job_id"]
        assert status(job_id)["status"] == "queued"
        t0 = time.monotonic()
        summary = run_once(factory)
        happy_seconds = round(time.monotonic() - t0, 2)
        assert summary is not None and summary["status"] == "completed"
        done = status(job_id)
        proof["happy_path"] = {
            "seconds": happy_seconds,
            "status": done["status"],
            "questions": done["result_summary"]["questions"],
            "answered": done["result_summary"]["answered"],
            "stages": [
                {
                    "stage": s["stage"],
                    # Per-stage seconds live inside the stage row's
                    # detail dict (the worker records them there).
                    "seconds": (s.get("detail") or {}).get("seconds"),
                }
                for s in done["stages"]
            ],
            "stage_names": [s["stage"] for s in done["stages"]],
        }
        assert run_once(factory) is None  # queue empty

        # Forced failure + retry: corrupt bytes fail with a reason,
        # retry re-queues, good bytes complete the same job.
        bad = submit(b"%PDF-1.4\n%garbage-not-a-pdf", "bad.pdf")
        bad_id = bad["job_id"]
        summary = run_once(factory)
        assert summary is not None and summary["status"] == "failed"
        failed = status(bad_id)
        assert failed["status"] == "failed" and failed["error"]
        res = client.post(
            f"/api/v1/async-jobs/{bad_id}/retry",
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 200 and res.json()["status"] == "queued"
        session = factory()
        job = session.get(db.Job, uuid.UUID(bad_id))
        document = session.get(db.Document, job.document_id)
        store = LocalDiskStorage(settings.storage_root)
        store.delete(document.storage_path)
        store.put(document.storage_path, ca40)
        session.close()
        summary = run_once(factory)
        assert summary is not None and summary["status"] == "completed"
        assert summary["questions"] == 40
        proof["failure_then_retry"] = {
            "failed_error": failed["error"],
            "retry_count": 1,
            "after_retry": "completed",
            "questions_after_retry": 40,
        }

        # Cancel a queued job: cancelled, not failed; the worker
        # leaves it alone; a second cancel is a 409.
        cancel_body = submit(ca40)
        cancel_id = cancel_body["job_id"]
        res = client.post(
            f"/api/v1/async-jobs/{cancel_id}/cancel",
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 200 and res.json()["status"] == "cancelled"
        assert run_once(factory) is None
        res = client.post(
            f"/api/v1/async-jobs/{cancel_id}/cancel",
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 409
        proof["cancel_queued"] = {
            "status": "cancelled",
            "second_cancel_status": 409,
            "worker_claimed_nothing": True,
        }

        # Cancel a processing job: claimed, flag set, the worker
        # records cancelled at the first stage boundary.
        proc_body = submit(ca40)
        proc_id = proc_body["job_id"]
        session = factory()
        job = claim_next_job(session)
        assert job is not None and str(job.id) == proc_id
        job.result_summary = {"cancel_requested": True}
        session.commit()
        session.close()
        session = factory()
        job = session.get(db.Job, uuid.UUID(proc_id))
        summary = process_job(
            session,
            job,
            storage=LocalDiskStorage(settings.storage_root),
            settings=settings,
        )
        assert summary["status"] == "cancelled"
        session.close()
        proof["cancel_processing"] = {"status": "cancelled"}
    engine.dispose()
    return proof


def _security_proof() -> dict:
    """Per-user isolation, oversize handling, bad input, rate
    limit, and the secrets grep — through the real HTTP path."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.api.v1.async_jobs as async_jobs_api
    import app.api.v1.review as review_api
    from app.config import settings
    from app.db.models import Base
    from app.main import app
    from app.security.rate_limit import rate_limiter
    from app.tests.conftest import FakeSupabaseClient, auth_headers

    tmp = Path(tempfile.mkdtemp(prefix="m7-bench-sec-"))
    engine = create_engine(f"sqlite:///{tmp}/jobs.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    async_jobs_api.get_session = lambda: factory()  # type: ignore[method-assign]
    review_api.get_session = lambda: factory()  # type: ignore[method-assign]
    settings.storage_root = str(tmp / "storage")
    rate_limiter.reset()
    proof: dict = {}
    with TestClient(app) as client:
        app.state.supabase_client = FakeSupabaseClient()
        app.state.service_client = app.state.supabase_client
        ca40 = (PPSC66_DIR / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()

        # Per-user isolation: user A's job is a 404 for user B
        # (GET and cancel), for both async-jobs and review parse.
        res = client.post(
            "/api/v1/async-jobs/parse",
            files={"file": ("ca40.pdf", ca40, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 202, res.text
        job_id = res.json()["job_id"]
        res_b = client.get(f"/api/v1/async-jobs/{job_id}", headers=auth_headers("token-user-b"))
        res_b_cancel = client.post(
            f"/api/v1/async-jobs/{job_id}/cancel",
            headers=auth_headers("token-user-b"),
        )
        proof["per_user_isolation"] = {
            "other_user_get_status": res_b.status_code,
            "other_user_cancel_status": res_b_cancel.status_code,
        }
        assert res_b.status_code == 404
        assert res_b_cancel.status_code == 404

        # Oversize body: 422 file_too_large (the M1 contract),
        # rejected by the middleware before the route reads it.
        old_limit = settings.max_file_size_bytes
        settings.max_file_size_bytes = 1024
        try:
            res = client.post(
                "/api/v1/documents/parse",
                files={"file": ("big.pdf", b"%PDF" + b"0" * 2048, "application/pdf")},
                headers=auth_headers("token-user-a"),
            )
            proof["oversize"] = {
                "status": res.status_code,
                "code": res.json()["error"]["code"],
            }
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "file_too_large"
        finally:
            settings.max_file_size_bytes = old_limit

        # Bad input: a non-PDF to the PDF parse endpoint is a 422,
        # never a 500; unauthenticated access is a 401.
        res = client.post(
            "/api/v1/documents/parse",
            files={"file": ("x.txt", b"not a pdf", "text/plain")},
            headers=auth_headers("token-user-a"),
        )
        proof["bad_input_non_pdf"] = {"status": res.status_code}
        assert res.status_code == 422
        res = client.post(
            "/api/v1/documents/parse",
            files={"file": ("x.pdf", ca40, "application/pdf")},
        )
        proof["unauthenticated"] = {"status": res.status_code}
        assert res.status_code == 401

        # Rate limit: 10 parse attempts per user per minute by
        # default; the 11th is a 429 (code rate_limited).
        rate_limiter.reset()
        statuses = []
        for _ in range(11):
            res = client.post(
                "/api/v1/documents/parse",
                files={"file": ("x.txt", b"not a pdf", "text/plain")},
                headers=auth_headers("token-user-a"),
            )
            statuses.append(res.status_code)
        proof["rate_limit"] = {
            "attempts": 11,
            "statuses": statuses,
            "limit_per_minute": settings.rate_limit_register_per_minute,
        }
        assert statuses[:10] == [422] * 10
        assert statuses[10] == 429
    engine.dispose()

    # Secrets grep: same method as test_security_m7 — scan every
    # shipped .py file (app/, excluding tests) for an assignment
    # of a string literal to a secret-looking name.
    repo = Path(__file__).resolve().parent.parent
    pattern = re.compile(
        r"""(?i)(api[_-]?key|secret|password|bearer|supabase[_-]?service[_-]?role[_-]?key)\s*[:=]\s*["'][A-Za-z0-9_\-./]{8,}["']"""
    )
    offenders = []
    for path in sorted((repo / "app").rglob("*.py")):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(repo)}:{lineno}")
    proof["secrets_grep"] = {
        "files_scanned": len([p for p in (repo / "app").rglob("*.py") if "tests" not in p.parts]),
        "offenders": offenders,
    }
    assert offenders == []
    return proof


def _observability_samples() -> dict:
    """Sample /health and /metrics from a real run (TestClient,
    fake auth for the parse that generates the metrics).

    Metric-name contract (the real names — see the M7 tests):
    counters appear on FIRST EVENT (standard Prometheus
    behaviour), so this section generates one of each: a sync
    parse (documents_parsed_total, ocr_calls_total), an async
    job through the worker (officerpath_jobs_current gauge from
    the live DB, officerpath_stage_seconds_total, jobs_total),
    and one bad parse (errors_total). http_requests_total comes
    from the requests themselves."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.api.metrics as metrics_api
    import app.api.v1.async_jobs as async_jobs_api
    import app.api.v1.review as review_api
    from app.config import settings
    from app.db.models import Base
    from app.main import app
    from app.security.rate_limit import rate_limiter
    from app.tests.conftest import FakeSupabaseClient, auth_headers
    from app.utils.metrics import reset as metrics_reset
    from app.workers.runner import run_once

    tmp = Path(tempfile.mkdtemp(prefix="m7-bench-obs-"))
    engine = create_engine(f"sqlite:///{tmp}/jobs.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    async_jobs_api.get_session = lambda: factory()  # type: ignore[method-assign]
    review_api.get_session = lambda: factory()  # type: ignore[method-assign]
    metrics_api.get_session = lambda: factory()  # type: ignore[method-assign]
    settings.storage_root = str(tmp / "storage")
    rate_limiter.reset()
    metrics_reset()
    samples: dict = {}
    with TestClient(app) as client:
        app.state.supabase_client = FakeSupabaseClient()
        app.state.service_client = app.state.supabase_client
        health = client.get("/health")
        samples["health"] = {"status_code": health.status_code, "body": health.json()}
        # One real parse so /metrics has nonzero counters.
        ca40 = (PPSC66_DIR / "ppsc-current-affairs-40-mcqs.pdf").read_bytes()
        res = client.post(
            "/api/v1/documents/parse",
            files={"file": ("ca40.pdf", ca40, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 200, res.text
        # One async job through the worker: the jobs gauge (live
        # DB) + stage durations + jobs_total.
        res = client.post(
            "/api/v1/async-jobs/parse",
            files={"file": ("ca40.pdf", ca40, "application/pdf")},
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 202, res.text
        summary = run_once(factory)
        assert summary is not None and summary["status"] == "completed"
        # One error so errors_total exists.
        res = client.post(
            "/api/v1/documents/parse",
            files={"file": ("x.txt", b"not a pdf", "text/plain")},
            headers=auth_headers("token-user-a"),
        )
        assert res.status_code == 422, res.text
        metrics = client.get("/metrics")
        text = metrics.text
        required = [
            "officerpath_jobs_current",
            "documents_parsed_total",
            "ocr_calls_total",
            "http_requests_total",
            "errors_total",
            "officerpath_stage_seconds_total",
            "jobs_total",
        ]
        samples["metrics"] = {
            "status_code": metrics.status_code,
            "content_type": metrics.headers.get("content-type"),
            "required_present": {name: (name in text) for name in required},
            "documents_parsed_line": next(
                (ln for ln in text.splitlines() if ln.startswith("documents_parsed_total")),
                None,
            ),
            "jobs_current_line": next(
                (ln for ln in text.splitlines() if ln.startswith("officerpath_jobs_current")),
                None,
            ),
            "sample_lines": [ln for ln in text.splitlines() if not ln.startswith("#")][:12],
        }
        assert all(name in text for name in required), "missing from /metrics: " + ", ".join(
            n for n in required if n not in text
        )
    engine.dispose()
    return samples


def main() -> None:
    if CAL_OUT.exists():
        CAL_OUT.unlink()
        print("== removed stale docs/benchmarks/m6-calibration.json ==")
    report: dict = {
        "milestone": "M7",
        "date": "2026-11-22",
        "vm": "VM numbers — NOT Render numbers",
        "peak_rss_mb": _peak_rss_mb(),
        "before_latency": BEFORE_LATENCY,
        "dpi_experiment": DPI_EXPERIMENT,
    }
    all_points: list[tuple[float, bool]] = []

    print("== M7: end-to-end digital fixtures (accuracy re-run) ==")
    report["end_to_end"] = {}
    gt_testpoint, _ = _load_testpoint()
    r, pts = _end_to_end_digital(
        "English_1000_Most_Repeated_MCQs_by_TestPoint.pk.pdf",
        gt_testpoint,
        score_answers=True,
        source_id="m7-testpoint",
    )
    report["end_to_end"]["testpoint"] = r
    all_points.extend(pts)
    print(f"  testpoint: {r['counts']} score={r['score']['question_detection']}")
    gt_computer, _ = _load_computer()
    pdf = (PPSC66_DIR / "Computer_Past_Papers_2019-2025.pdf").read_bytes()
    start = time.monotonic()
    matched, _, _ = parse_document_bytes(pdf, "m7-computer")
    qa_detected = [
        {"number": q.number, "text": q.text, "options": [], "answer": q.answer_text}
        for q in matched.qa_pairs
    ]
    report["end_to_end"]["computer_qa"] = {
        "seconds": round(time.monotonic() - start, 1),
        "qa_pairs": len(matched.qa_pairs),
        "score": _score_qa(qa_detected, gt_computer),
    }
    print(f"  computer qa: {report['end_to_end']['computer_qa']['score']}")
    gt_ca40, _ = _load_ca40()
    r, pts = _end_to_end_digital(
        "ppsc-current-affairs-40-mcqs.pdf",
        gt_ca40,
        score_answers=True,
        source_id="m7-ca40",
    )
    report["end_to_end"]["ca40"] = r
    all_points.extend(pts)
    print(f"  ca40: {r['counts']} score={r['score']['question_detection']}")
    gt_urdu, _ = _load_urdu_noa()
    r, pts = _end_to_end_digital(
        "PDF_Urdu_MCQs_NOA.pdf",
        gt_urdu,
        score_answers=True,
        source_id="m7-urdu-noa",
    )
    report["end_to_end"]["urdu_noa"] = r
    all_points.extend(pts)
    print(f"  urdu_noa: {r['counts']} score={r['score']['question_detection']}")

    print("== M7: PPSC-66 live, single vs multi-pass (fresh processes) ==")
    p66_path = str(FLUTTER_FIX / "ppsc_paper_66.pdf")
    dump_path = Path("/tmp/m7-p66-single-dump.json")
    single = _driver(["--pdf", p66_path, "--dump", str(dump_path)])
    multi = _driver(["--pdf", p66_path, "--multi-pass"])
    report["ppsc66_live"] = {"single_path": single, "multi_pass": multi}
    print(f"  single: {single}")
    print(f"  multi:  {multi}")
    # Promotion before/after derived from the single parse's own
    # promotion report (no second OCR pass): promotion only moves
    # pending questions to answered.
    dump = json.loads(dump_path.read_text())
    promoted_count = dump["promotion"].get("promoted_count", 0)
    after = dump["counts"]
    report["ppsc66_live"]["promotion_before_after_derived"] = {
        "before": {
            "answered": after["answered"] - promoted_count,
            "unknown": after["unknown"] + promoted_count,
            "pending": after["pending"] + promoted_count,
            "questions": after["questions"],
        },
        "after": {
            "answered": after["answered"],
            "unknown": after["unknown"],
            "pending": after["pending"],
            "questions": after["questions"],
        },
        "promoted_count": promoted_count,
        "note": "derived from the single parse's promotion report — "
        "promotion moves pending questions to answered, nothing else",
    }
    print(f"  promotion: {report['ppsc66_live']['promotion_before_after_derived']}")
    # Live calibration points (key GT letters, by number).
    key_gt = _ppsc66_key_gt()
    key_gt_list = [
        {"number": n, "text": "", "options": ["", "", "", ""], "answer": _key_letter(v)}
        for n, v in sorted(key_gt.items())
    ]
    live_points = _calibration_points(dump["questions"], key_gt_list, by_number=True)
    all_points.extend(live_points)
    print(f"  live calibration points: {len(live_points)}")

    print("== M7: key-region before/after (live key) ==")
    report["key_region_before_after"] = _key_region_before_after()
    print(f"  whole-blob: {report['key_region_before_after']['before_whole_blob']}")
    print(f"  region: {report['key_region_before_after']['after_region_located']}")

    print("== M7: Paper 60 live ==")
    report["paper60_live"] = _paper60_live()
    print(f"  paper60: {report['paper60_live']['score']}")

    print("== M7: acceptance photos via the image endpoint driver ==")
    table_photo = FLUTTER_FIX / "table-computer-q67-81-resent-20261121.jpg"
    paper60_photo = PPSC66_DIR / "paper60-photo.jpg"
    report["photo_parses"] = {
        "computer_table_photo": _driver(["--image", str(table_photo)]),
        "paper60_photo": _driver(["--image", str(paper60_photo)]),
    }
    print(f"  table photo: {report['photo_parses']['computer_table_photo']}")
    print(f"  paper60 photo: {report['photo_parses']['paper60_photo']}")

    print("== M7: job pipeline proof ==")
    report["job_pipeline"] = _job_pipeline_proof()
    print(
        f"  happy path: {report['job_pipeline']['happy_path']['status']} "
        f"in {report['job_pipeline']['happy_path']['seconds']}s, "
        f"stages={report['job_pipeline']['happy_path']['stage_names']}"
    )
    print(f"  failure+retry: {report['job_pipeline']['failure_then_retry']}")
    print(
        f"  cancel: {report['job_pipeline']['cancel_queued']} / "
        f"{report['job_pipeline']['cancel_processing']}"
    )

    print("== M7: security proof ==")
    report["security"] = _security_proof()
    print(f"  isolation: {report['security']['per_user_isolation']}")
    print(f"  rate limit: {report['security']['rate_limit']['statuses']}")
    print(f"  secrets grep offenders: {report['security']['secrets_grep']['offenders']}")

    print("== M7: observability samples ==")
    report["observability"] = _observability_samples()
    print(f"  health: {report['observability']['health']['body']}")
    print(f"  metrics: {report['observability']['metrics']['documents_parsed_line']}")

    print("== M7: calibration (this run's points only) ==")
    fit = fit_calibration(all_points)
    CAL_OUT.write_text(json.dumps(fit.to_dict(), indent=1, ensure_ascii=False))
    report["calibration"] = fit.to_dict()
    report["calibration"]["total_pairs"] = len(all_points)
    print(f"  pairs={len(all_points)} ece_before={fit.ece_before} ece_after={fit.ece_after}")

    tp = report["end_to_end"]["testpoint"]["score"]["question_detection"]
    report["testpoint_residual"] = {
        "question_fp": tp["fp"],
        "question_prf": tp,
        "note": "M5 residual was 28 FPs; M6 measured 28; M7 did not "
        "change extraction (see report for the cheap-fix assessment).",
    }
    print(f"  testpoint FP: {tp['fp']} (M5/M6: 28)")

    report["peak_rss_mb"] = _peak_rss_mb()
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nwrote {OUT}")
    print(f"wrote {CAL_OUT}")
    print(f"peak RSS (this process): {report['peak_rss_mb']} MB (VM)")


if __name__ == "__main__":
    main()
