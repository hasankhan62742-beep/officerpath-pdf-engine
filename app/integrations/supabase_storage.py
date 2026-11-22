# OfficerPath AI — PDF Engine (Phase 1A)
# Storage helpers (Phase 1A: defined, not yet used by the register flow).
# The app uploads page images directly to the private `pdf-documents`
# bucket; the backend fetches them with short-lived signed URLs.
# Signed URLs are minted with the SERVICE-ROLE client only, server-side.

from app.core.errors import ApiError
from app.database.supabase_client import get_service_client
from app.utils.logging import get_logger

log = get_logger(__name__)


def download_bucket_bytes(
    bucket: str,
    storage_path: str,
    *,
    service_client=None,
) -> bytes:
    """Download one object from a private Supabase Storage bucket
    with the SERVICE-ROLE client (server-side only — the key never
    leaves the backend). Used by the worker (M4) to fetch a
    register-source job's bytes: the client uploaded them to the
    bucket, so they are not on local disk.

    Errors are ApiErrors with stable codes and no internals:
    - 503 `storage_unavailable` — no service-role client configured.
    - 500 `storage_bucket_missing` — the bucket does not exist
      (live: apply migration 016 via the Dashboard).
    - 500 `storage_object_missing` — the bucket exists but the
      object is not there (wrong path, or deleted upstream).
    - 500 `storage_error` — anything else (network, auth, …).
    The bucket/object distinction is best-effort substring matching
    on the storage client's message; the fallback is `storage_error`.
    """
    client = service_client if service_client is not None else get_service_client()
    if client is None:
        raise ApiError(
            status_code=503,
            code="storage_unavailable",
            message="Storage is not configured on this server.",
        )
    try:
        data = client.storage.from_(bucket).download(storage_path)
    except Exception as exc:  # noqa: BLE001 — classify, then raise an ApiError
        message = str(exc)
        lowered = message.lower()
        if "bucket not found" in lowered:
            raise ApiError(
                status_code=500,
                code="storage_bucket_missing",
                message=(
                    f"Storage bucket {bucket!r} does not exist. "
                    "Apply migration 016 (Supabase Dashboard) to create it."
                ),
            ) from exc
        if "not found" in lowered or "object not found" in lowered:
            raise ApiError(
                status_code=500,
                code="storage_object_missing",
                message="The registered file is not in storage (wrong path or deleted).",
            ) from exc
        log.info(
            "bucket download failed",
            extra={"fields": {"bucket": bucket, "error": message[:200]}},
        )
        raise ApiError(
            status_code=500,
            code="storage_error",
            message="Could not download the document from storage.",
        ) from exc
    if not isinstance(data, (bytes, bytearray)):
        raise ApiError(
            status_code=500,
            code="storage_error",
            message="Could not download the document from storage.",
        )
    return bytes(data)


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
