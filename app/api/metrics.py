# OfficerPath AI — PDF Engine (Phase 1, M7)
# GET /metrics: Prometheus-style plain text, no new dependency.
#
# Unauthenticated BY DESIGN for Stage 1: every value is an
# aggregate (jobs by status, documents parsed, stage durations,
# OCR calls by engine, error counts by type). No metric carries
# user ids, file names, OCR text, or any per-document content, so
# there is nothing here an unauthenticated caller can use to
# learn about a user. If a future metric ever needs a label with
# user content, this endpoint must gain auth first (recorded in
# ADR-009). Jobs-by-status comes from a live database query when
# DATABASE_URL is configured (true even after a restart); the
# in-process counters cover the rest.

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import func

from app.db import models as db
from app.db.session import get_session
from app.utils import metrics

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    lines = [metrics.render().rstrip("\n")]
    session = get_session()
    if session is not None:
        try:
            rows = session.query(db.Job.status, func.count(db.Job.id)).group_by(db.Job.status).all()
            lines.append(
                "# HELP officerpath_jobs_current Jobs currently in each status (live database)."
            )
            lines.append("# TYPE officerpath_jobs_current gauge")
            for status, count in sorted(rows):
                lines.append(f'officerpath_jobs_current{{status="{status}"}} {count}')
        finally:
            session.close()
    return PlainTextResponse("\n".join(lines) + "\n")
