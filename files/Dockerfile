# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Non-root user for security
RUN useradd -m -u 1000 anomaly

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# Cloud Run uses PORT env var
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER anomaly

# Uvicorn: 2 workers, 1 thread each (Cloud Run is single-core by default)
# --no-access-log keeps logs clean; Cloud Run captures stdout separately
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "2", \
     "--no-access-log", \
     "--timeout-keep-alive", "30"]
