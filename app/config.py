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

    # --- M2: PDF rendering + preprocessing (prompt §6/§7, ADR-004) ---
    # Render DPI: 200 is the OCR sweet spot for print (300 gains little
    # and doubles memory). A4 at 200 DPI = 1654x2339 px (~3.9 MP,
    # ~12 MB RGB); at 300 DPI = ~8.7 MP (~26 MB RGB). Pages are rendered
    # ONE AT A TIME and buffers are released per page (streaming), so
    # peak render memory stays far under Render free's 512 MB (ADR-001).
    # max_render_pixels is the hard guard: a page whose render at the
    # requested DPI would exceed it is rendered at a lower DPI instead.
    render_dpi: int = 200
    render_max_dpi: int = 300
    max_render_pixels: int = 12_000_000
    # Preprocessing profile selection: "auto" picks a profile from
    # measured page quality (see app/pipeline/preprocess/profiles.py).
    # An explicit profile name forces that profile on every page.
    preprocess_profile: str = "auto"
    # Low-quality pages get a second profile run for comparison
    # (recorded, never silently picked). Disable to save CPU on Render.
    preprocess_compare_second_profile: bool = True

    # --- M3: OCR engines + layout (prompt §8/§9, ADR-002, ADR-005) ---
    # Routing is "auto": digital text first, OCR for scanned regions,
    # mixed pages combine both with deduplication (see router.py).
    # An engine that is not installed/available reports unavailable
    # and is skipped — never faked.
    ocr_routing: str = "auto"
    # Tesseract languages for the adapter (eng+urd). The binary + these
    # traineddata files must exist (apt: tesseract-ocr tesseract-ocr-urd
    # tesseract-ocr-ara). PSM 3 = fully automatic page segmentation
    # (handles two-column pages); PSM 6 assumes one uniform block.
    tesseract_languages: str = "eng+urd"
    tesseract_psm: int = 3
    tesseract_binary: str = "tesseract"
    # PaddleOCR: PP-OCRv5 Arabic-script models ("ar" language). The
    # adapter is availability-gated: if the package or models cannot
    # load, it reports unavailable with the reason (M3 report).
    paddleocr_language: str = "ar"
    paddleocr_enabled: bool = True
    # --- M4: deployment-aware OCR routing (ADR-006) ---
    # Deployment profile: "render-free" (Render free, 512 MB),
    # "vps" (Hostinger KVM 1, 4 GB), "local" (dev VM, 8 GB). The
    # router never selects PaddleOCR on a profile whose memory
    # budget is below its measured peak (M3: 1,775-3,667 MB).
    # An unknown profile name fails loudly at startup of the OCR
    # stage. memory_budget_mb overrides the profile default when set.
    deployment_profile: str = "local"
    memory_budget_mb: int | None = None
    # Gemini advisory (AIAssistProvider, prompt §15 / ADR-002): DISABLED
    # by default. Enabling ALSO needs a server key in the environment
    # (GEMINI_API_KEY — never in code); with no key the provider
    # reports disabled. Suggestions only, never a verified answer.
    gemini_advisory_enabled: bool = False
    gemini_model: str = "gemini-3.5-flash-lite"  # 2.5-flash-lite 404s (19 Nov)
    gemini_api_key: str | None = None
    gemini_max_calls_per_day: int = 0  # 0 = advisory disabled entirely
    gemini_max_output_tokens: int = 2048
    # --- M7: background worker (ADR-009) ---
    # In-process background worker (no Redis/celery — Render free
    # is one 0.1-CPU instance; a separate process would need its
    # own memory). Disabled by default: the API serves without it,
    # and the worker is enabled on Render via WORKER_ENABLED=true
    # or run as its own process (python -m app.workers.runner).
    worker_enabled: bool = False
    worker_poll_seconds: float = 5.0
    # Per-stage timeout: a stage that runs longer than this is
    # failed with the stage named, never left hanging. PPSC-66
    # single-path OCR takes ~130 s on the VM; 600 s leaves ample
    # headroom while still bounding a hung job.
    worker_stage_timeout_seconds: int = 600
    # Per-page Tesseract timeout (seconds): a page whose OCR hangs
    # longer than this contributes no blocks (per-page failure
    # isolation, M2) instead of hanging the job.
    tesseract_timeout_seconds: int = 300

    # Golden dataset version used by the benchmark harness.
    benchmark_dataset_version: str = "golden-v2"

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
