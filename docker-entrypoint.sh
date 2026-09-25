#!/bin/bash
set -euo pipefail

DATABASE_DIR="${ECHO_DATABASE_DIR:-/data/echo}"
ARTIFACT_ROOT="${ECHO_ARTIFACT_ROOT:-/data/artifacts}"

mkdir -p "${DATABASE_DIR}" "${ARTIFACT_ROOT}"

if [ $# -gt 0 ]; then
    if [[ "$1" == -* ]]; then
        exec cyrene-echo serve "$@"
    else
        exec "$@"
    fi
fi

HOST="${ECHO_HOST:-0.0.0.0}"
PORT="${ECHO_PORT:-8094}"
DB_PATH="${DATABASE_DIR}/echo.sqlite3"

echo "[entrypoint] Starting Cyrene Echo evaluation service on ${HOST}:${PORT}..."
exec cyrene-echo serve \
    --database "${DB_PATH}" \
    --artifact-root "${ARTIFACT_ROOT}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --allow-remote
