# ─────────────────────────────────────────────────────────────
# Stage 1 – base runtime image
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# System libs required by OpenCV (headless) and YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─────────────────────────────────────────────────────────────
# Stage 2 – install Python deps (cached layer)
# ─────────────────────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────
# Stage 3 – final image
# ─────────────────────────────────────────────────────────────
FROM deps AS final

# Copy application source
COPY . /app

# Copy trained weights from host (mounted or baked in)
# The weights directory is mapped as a volume in docker-compose
# so we create an empty placeholder here.
RUN mkdir -p /app/runs/detect/industrial_safety_yolo

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# Use gunicorn in production; fall back to flask dev server if needed
CMD ["gunicorn", "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "32", \
     "--timeout", "120", \
     "--worker-class", "gthread", \
     "app:app"]
