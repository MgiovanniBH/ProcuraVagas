# ==========================================
# Stage 1: Build the Next.js frontend console
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ==========================================
# Stage 2: Python runtime with uv
# ==========================================
FROM python:3.12-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Configure environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    JOBVIS_WEB_DIR=/app/web/out \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    JOBVIS_HOST=0.0.0.0

# Install dependencies using uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Copy source code and data
COPY src/ ./src/
COPY data/ ./data/

# Copy built frontend static export from Stage 1
COPY --from=frontend-builder /app/web/out /app/web/out

# Install the project package into environment
RUN uv sync --frozen --no-dev

# Expose Gradio Wizard (:7860) and FastAPI / Jobvis console (:8000)
EXPOSE 7860 8000

CMD ["python", "-m", "job_scout.app"]
