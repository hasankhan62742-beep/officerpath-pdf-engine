# OfficerPath AI — PDF Engine (Phase 1, M1)
# Multi-stage build: slim runtime image, non-root user, no secrets.
# Build in CI (GitHub Actions); Docker is NOT available on the dev VM.
# Deploys to Render free tier (ADR-001); Cloud Run is parked (GCP
# billing paused) — no Cloud Run assumptions remain in this file.
# HEALTHCHECK hits /health. Uvicorn handles SIGTERM gracefully:
# on SIGTERM it stops accepting new connections and finishes in-flight
# requests before exiting (Render gives a grace period; keep request
# work short or use the async job model).

# ---- Build stage: install dependencies into a venv ----
# M2 note (ADR-004): PyMuPDF, opencv-python-headless, Pillow and NumPy
# all install as manylinux wheels — no compiler is needed for them.
# The "headless OpenCV needs no libGL" claim that used to stand here
# was WRONG for opencv-python-headless==4.11.0.86: ldd on the dev
# venv's cv2 .so shows it still links libGL.so.1 and
# libglib-2.0.so.0 / libgthread-2.0.so.0, and the first Render deploy
# (2026-11-23) crashed at startup with `ImportError: libGL.so.1`
# for exactly that reason. The runtime stage below installs libgl1
# + libglib2.0-0 for it (see its note). build-essential stays only
# for any future source build. (UNVERIFIED in Docker itself — no
# Docker on the dev VM; the first CI Docker build after the push
# verifies it.)
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage: minimal, non-root ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000
WORKDIR /app
# M3 note (ADR-005): Tesseract needs its binary + language data at
# runtime (eng+urd+ara for Urdu/Arabic-script pages, osd for the
# orientation data PSM 3 uses). The language list matches the set
# the M7 suite passes against on the VM (tesseract-ocr-eng/urd/osd
# installed explicitly — the base tesseract-ocr package alone is
# not relied on to pull eng). The builder stage does not need it
# (pytesseract is a thin wrapper). PaddleOCR models are NOT baked into the image — they download on first use
# into ~/.paddlex (network, ~50-100 MB); a slim build omits paddleocr
# from requirements.txt instead. (UNVERIFIED in Docker itself — no
# Docker on the dev VM; the first CI Docker build after the push
# verifies it, as with M2.)
# 2026-11-23 Render failure: the first live deploy crashed at
# startup with `ImportError: libGL.so.1` at `import cv2`
# (app/pipeline/answers/handwriting.py, via app.main). The headless
# wheel opencv-python-headless==4.11.0.86 still links libGL.so.1 and
# libglib-2.0.so.0 / libgthread-2.0.so.0 — proven by ldd on the dev
# venv's cv2 .so — so the runtime stage installs libgl1 (the
# Debian 12 bookworm name; libgl1-mesa-glx is the pre-bookworm name
# — do not use it) and libglib2.0-0 (provides both glib libs).
# Runtime stage only: the builder never imports cv2.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-urd tesseract-ocr-ara tesseract-ocr-osd \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
# Alembic migrations ship in the image so `alembic upgrade head` can
# run at deploy time (DATABASE_URL from env). No secrets in either.
COPY alembic ./alembic
COPY alembic.ini ./
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
