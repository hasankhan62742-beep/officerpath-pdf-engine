# OfficerPath AI — PDF Engine (Phase 1A)
# Storage helpers (Phase 1A: defined, not yet used by the register flow).
# The app uploads page images directly to the private `pdf-documents`
# bucket; the backend fetches them with short-lived signed URLs.
# Signed URLs are minted with the SERVICE-ROLE client only, server-side.

from app.core.errors import ApiError
from app.utils.logging import get_logger

log = get_logger(__name__)


def create_signed_download_url(
    service_client, bucket: str, storage_path: str, expires_in_seconds: int = 900
) -> str:
    """Short-lived (default 15 min) signed URL for one object."""
    if service_client is None:
        raise ApiError(
            status_code=503,
            code="storage_unavailable",
            message="Storage is not configured on this server.",
        )
    res = service_client.storage.from_(bucket).create_signed_url(storage_path, expires_in_seconds)
    url = res.get("signedURL") if isinstance(res, dict) else None
    if not url:
        raise ApiError(
            status_code=500,
            code="storage_error",
            message="Could not create a download link for the document.",
        )
    return url
