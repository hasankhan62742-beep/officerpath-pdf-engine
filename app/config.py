# OfficerPath AI — PDF Engine (Phase 1, M1)
# Settings. Secrets come ONLY from environment variables, never from code
# or from files committed to the repo. `.env.example` shows placeholders only.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "officerpath-pdf-engine"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production

    host: str = "0.0.0.0"
    port: int = 8000

    # Supabase — URL + ANON key are publishable config; the SERVICE-ROLE key
    # is a server-side secret. It must NEVER be shipped to a client, logged,
    # or returned in any API response. All three are read from env only.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # Upload / job limits (mirror the Flutter app's limits where they exist).
    max_file_size_bytes: int = 100 * 1024 * 1024  # 100 MB, app import cap
    max_pages_per_job: int = 100  # mirrors maxOcrPagesPerImport in the app
    max_page_file_size_bytes: int = 5 * 1024 * 1024  # 5 MB per page image

    # Rate limits — Phase 1: simple in-memory per-user sliding windows.
    # NOT shared across instances; replace with a distributed limiter
    # (e.g. Redis) before running more than one replica.
    rate_limit_register_per_minute: int = 10
    rate_limit_retry_per_minute: int = 5
    rate_limit_window_seconds: int = 60

    # Storage bucket for uploaded documents (created by migration 015).
    documents_bucket: str = "pdf-documents"

    # --- M1: engine-owned database (SQLAlchemy + Alembic, ADR-003) ---
    # DATABASE_URL is the SQLAlchemy URL for the SAME Postgres database
    # that Supabase hosts (e.g. postgresql+psycopg://...). It is None by
    # default: the engine runs without it (PostgREST register/jobs flow
    # still works), and stage history is then recorded in-memory only
    # (NullStageRecorder). Alembic migrations need it set. NEVER put the
    # Supabase Postgres password in code; set it as an env var / secret.
    database_url: str | None = None

    # --- M1: storage backend (abstraction; local disk first) ---
    # "local" only for now. S3-compatible backends are added in later
    # milestones behind the same StorageBackend interface (ADR-003 note).
    storage_backend: str = "local"
    # Root for local storage. Relative paths resolve against the repo
    # root (the process working directory). Render's filesystem is
    # ephemeral — local storage is a Stage-1 development default, not a
    # production persistence story (see docs/deploy-render.md).
    storage_root: str = "var/storage"

    # --- M1: ingestion limits (prompt §6) ---
    # Image dimension / pixel caps guard against decompression bombs:
    # an image whose decoded pixels far exceed its file size is rejected.
    max_image_dimension_px: int = 12000
    # 25 MP: a 300 DPI A4 page is ~8.75 MP; 25 MP caps decoded RGB at
    # ~75 MB, safe inside Render free's 512 MB (ADR-001). Absolute
    # pixel cap is the real decompression-bomb bound — see validator.
    max_image_pixels: int = 25_000_000
    # Ratio above which a WARNING (not a rejection) is recorded.
    # Highly compressible real images (blank pages) legitimately reach
    # ratios in the hundreds; rejecting on ratio alone would refuse
    # blank scans. Absolute pixel/file caps do the rejecting.
    max_decompression_ratio: int = 100  # decoded bytes / file bytes
    # Max bytes read when sniffing a file's structure (headers, EXIF,
    # PDF trailer). Files are validated streaming-style where possible;
    # this cap bounds the sniffing pass, not the file itself.
    sniff_max_bytes: int = 8 * 1024 * 1024

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def service_role_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)


settings = Settings()
