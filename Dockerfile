# The Muser — Multi-stage Docker build
# CPU target: for users without NVIDIA GPU (LLM orchestration only)
# GPU target: full pipeline with CUDA support

# ============================================================
# Stage 1: Base image with system dependencies
# ============================================================
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    libfluidsynth-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml LICENSE NOTICE ./
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/

# ============================================================
# Stage 2: CPU target
# ============================================================
FROM base AS cpu

RUN pip install --no-cache-dir -e "."

VOLUME ["/app/models", "/app/voices", "/app/soundfonts", "/app/compositions"]
EXPOSE 7860

ENTRYPOINT ["muser"]

# ============================================================
# Stage 3: GPU target (NVIDIA CUDA)
# ============================================================
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS gpu

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    fluidsynth \
    libfluidsynth-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /app
COPY pyproject.toml LICENSE NOTICE ./
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/

RUN pip install --no-cache-dir -e ".[gpu,voice,web]"

VOLUME ["/app/models", "/app/voices", "/app/soundfonts", "/app/compositions"]
EXPOSE 7860

ENTRYPOINT ["muser"]
