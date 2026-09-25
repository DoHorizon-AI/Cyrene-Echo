# syntax=docker/dockerfile:1.4
# ==============================================================================
# Cyrene Echo Production Container Image
# Provides:
#   1. cyrene-echo (Evaluation run and gate contract service & CLI)
# ==============================================================================

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH" \
    ECHO_DATABASE_DIR="/data/echo" \
    ECHO_ARTIFACT_ROOT="/data/artifacts" \
    ECHO_HOST="0.0.0.0" \
    ECHO_PORT="8094"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install third-party runtime dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "httpx>=0.27.0" \
    "pydantic>=2.0.0" \
    "uvicorn>=0.30.0" \
    "grpcio>=1.60.0" \
    "protobuf>=4.25.0"

# Copy dependency SDKs
COPY Cyrene-Platform/sdk/python/cyrene_artifacts /app/deps/cyrene_artifacts
COPY Cyrene-Plugins-Official/sdk/python/cyrene_plugin_runtime /app/deps/cyrene_plugin_runtime

# Install local monorepo SDKs with --no-deps
RUN pip install --no-cache-dir --no-deps \
    /app/deps/cyrene_artifacts \
    /app/deps/cyrene_plugin_runtime

# Copy Echo source
COPY Cyrene-Services/Cyrene-Echo/pyproject.toml Cyrene-Services/Cyrene-Echo/README.md /app/echo/
COPY Cyrene-Services/Cyrene-Echo/src /app/echo/src

# Install Echo package with --no-deps
RUN pip install --no-cache-dir --no-deps /app/echo

# Create data directories and non-root user
RUN mkdir -p /data/echo /data/artifacts && \
    useradd -u 10001 -m -s /bin/bash cyrene && \
    chown -R cyrene:cyrene /data /app

# Copy entrypoint script
COPY Cyrene-Services/Cyrene-Echo/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER cyrene

EXPOSE 8094

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:8094/ || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
