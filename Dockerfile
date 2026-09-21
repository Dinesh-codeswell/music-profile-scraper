# syntax=docker/dockerfile:1

# ==============================================================================
# Stage 1: Build & Wheel Compilation
# ==============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install compilation tools for binary wheel building if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements definition first for optimal Docker layer caching
COPY requirements.txt .

# Install dependencies into an isolated prefix directory
RUN pip install --prefix=/install -r requirements.txt


# ==============================================================================
# Stage 2: Minimal Production Runtime
# ==============================================================================
FROM python:3.12-slim AS runtime

# Open Container Initiative (OCI) Metadata
LABEL org.opencontainers.image.title="Artist Import Studio" \
      org.opencontainers.image.description="FastAPI streaming profile ingestion, cross-platform fusion, and EPK generator" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/Dinesh-codeswell/music-profile-scraper"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Security: Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -M appuser

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY public/ /app/public/
COPY pyproject.toml README.md LICENSE /app/

# Enforce non-root ownership
RUN chown -R appuser:appgroup /app

# Switch to unprivileged user
USER appuser:appgroup

# Expose default HTTP port
EXPOSE 8000

# Healthcheck using Python stdlib (no external curl/wget dependency required)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request, sys, os; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", 8000)}/api/health', timeout=3).getcode() == 200 else 1)"

# Start Uvicorn ASGI server
CMD ["python3", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
