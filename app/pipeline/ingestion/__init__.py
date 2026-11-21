# OfficerPath AI — PDF Engine (Phase 1, M1)
# Ingestion stage: file validation, per-page classification, SHA-256
# dedup, storage, stage recording. No OCR, no parsing here — that is
# M2–M5. This stage answers one question only: "is this file safe and
# well-formed enough to enter the pipeline, and what do we know about
# its pages already?"
