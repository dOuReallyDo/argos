# ── Argos Production Dockerfile ─────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Argos RAG"
LABEL org.opencontainers.image.description="Multimodal RAG system"
LABEL org.opencontainers.image.source="https://github.com/doureallydo/argos"

# System dependencies for OCR, video, crypto
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy source
COPY . .

# Create data directory
RUN mkdir -p /app/data/files /app/data/logs

EXPOSE 8000

# Default: run API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
