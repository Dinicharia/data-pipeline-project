# Dockerfile
# Packages our entire ETL pipeline into a portable container.
# Build:  docker build -t data-pipeline:latest .
# Run:    docker run --env-file .env data-pipeline:latest

# ── Base image ────────────────────────────────────────────────────────────────
# Every Dockerfile starts with FROM — the image we build on top of.
# python:3.11-slim is the official Python image, "slim" variant:
#   - python:3.11       → 900MB (includes build tools, many extras)
#   - python:3.11-slim  → 130MB (just Python, nothing extra)
#   - python:3.11-alpine→  50MB (even smaller, but causes compatibility issues
#                                with psycopg2 and pandas — avoid for data work)
# Rule: use -slim for data pipelines. -alpine sounds attractive but
# its missing C libraries break numpy, pandas, and psycopg2.
FROM python:3.11-slim

# ── Metadata ──────────────────────────────────────────────────────────────────
# LABEL stores metadata in the image — useful for auditing
LABEL maintainer="data-engineering"
LABEL project="data-pipeline"
LABEL version="1.0"

# ── System dependencies ───────────────────────────────────────────────────────
# RUN executes shell commands during the BUILD step
# psycopg2 needs libpq-dev to compile its C extensions
# We chain commands with && to create ONE layer instead of three
# Each RUN creates a new image layer — fewer layers = smaller image
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*    # delete apt cache to shrink image size

# ── Working directory ─────────────────────────────────────────────────────────
# WORKDIR sets the directory for all subsequent commands
# Creates it if it doesn't exist
# All paths in COPY, RUN, CMD are relative to this
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# COPY source destination
# We copy requirements.txt FIRST (before the rest of the code)
# WHY? Docker layer caching.
# If requirements.txt hasn't changed, Docker reuses the cached pip install layer
# even when your source code changes — much faster rebuilds
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
# Copy everything else after installing dependencies
# (so code changes don't invalidate the pip cache layer)
COPY src/        ./src/
COPY sql/        ./sql/
COPY config/     ./config/
COPY prefect/    ./prefect/

# ── Create runtime directories ────────────────────────────────────────────────
RUN mkdir -p data logs

# ── Environment ───────────────────────────────────────────────────────────────
# ENV sets environment variables baked into the image
# These are defaults — can be overridden at runtime with --env or --env-file
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# PYTHONUNBUFFERED=1: print() output appears immediately (not buffered)
#                     critical for seeing logs in real time
# PYTHONDONTWRITEBYTECODE=1: don't create .pyc cache files in the container

# ── Non-root user ─────────────────────────────────────────────────────────────
# Running as root inside a container is a security risk —
# if someone escapes the container, they have root on the host.
# Create a dedicated user for our application.
RUN useradd --create-home --shell /bin/bash pipeline
USER pipeline

# ── Default command ───────────────────────────────────────────────────────────
# CMD is what runs when you do: docker run data-pipeline:latest
# Can be overridden: docker run data-pipeline:latest python src/other.py
CMD ["python", "src/pipeline.py"]