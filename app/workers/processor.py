# OfficerPath AI — PDF Engine (Phase 1A)
# Worker skeleton. Phase 1A does NOT implement OCR or parsing (Phase 1B).
# This module holds the job-claim pattern the worker will use, so the
# Phase 1B worker does not have to invent it: claim exactly one queued
# job atomically (status transition guarded by WHERE status='queued',
# the same atomic-claim pattern as the redeem-code M1 fix), then hand
# the job to the processing pipeline.

from app.database.repositories import JobRepository
from app.utils.logging import get_logger

log = get_logger(__name__)


def process_job(job: dict) -> dict:
    """Process one queued job. NOT IMPLEMENTED in Phase 1A.

    Phase 1B will: download the document's page images from Storage,
    run OCR + geometry + the parser, write the result JSON to Storage,
    and update the job row to done/failed with counts.
    """
    raise NotImplementedError(
        "Job processing (OCR + parse) is Phase 1B work and is not "
        "implemented in the Phase 1A skeleton."
    )


def claim_next_job(jobs: JobRepository) -> dict | None:
    """Claim one queued job for processing (Phase 1B hook).

    The real implementation must claim atomically in the database
    (UPDATE ... WHERE status='queued' RETURNING ...) so two workers
    can never claim the same job. This skeleton returns None until
    the Phase 1B worker is built.
    """
    log.info("Worker claim requested (Phase 1B stub)")
    return None
