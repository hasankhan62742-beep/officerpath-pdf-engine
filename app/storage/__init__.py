# OfficerPath AI — PDF Engine (Phase 1, M1)
# Storage abstraction: originals are immutable and live behind the
# StorageBackend interface. Local disk first; an S3-compatible backend
# is added later behind the same interface (ADR-003 note).
