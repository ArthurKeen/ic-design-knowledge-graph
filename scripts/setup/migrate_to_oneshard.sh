#!/usr/bin/env bash
#
# Migrate an existing ArangoDB database to OneShard layout.
#
# OneShard must be set when the *database* is created; you cannot convert in place.
# Typical flow: dump → drop → create OneShard empty DB → restore.
#
# Prerequisites:
#   - Either `arangodump` / `arangosh` / `arangorestore` on PATH (match server major version),
#     OR Docker (uses image ARANGO_CLI_IMAGE, default arangodb:3.12)
#   - Enterprise cluster if you rely on OneShard (see docs)
#   - Configure project .env (ARANGO_MODE, endpoints, and optional replication match Python tools)
#
# Usage:
#   chmod +x scripts/setup/migrate_to_oneshard.sh
#   ./scripts/setup/migrate_to_oneshard.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Load project .env so ARANGO_MODE, endpoints, and optional replication match Python tools.
# Temporarily allow unset vars: passwords often contain "$" sequences that must not trigger
# `set -u` / accidental expansion (e.g. "$GTEaYL" seen as a variable name).
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set +u
  set -a
  # shellcheck disable=SC1090
  source "${REPO_ROOT}/.env"
  set +a
  set -u
fi

# --- Endpoint for CLI tools (arangodump does not read ARANGO_MODE) ---
if [[ "${ARANGO_MODE:-LOCAL}" == "LOCAL" ]]; then
  ARANGO_ENDPOINT="${ARANGO_ENDPOINT:-${LOCAL_ARANGO_ENDPOINT:-http://localhost:8530}}"
  ARANGO_USERNAME="${ARANGO_USERNAME:-${LOCAL_ARANGO_USERNAME:-root}}"
  ARANGO_PASSWORD="${ARANGO_PASSWORD:-${LOCAL_ARANGO_PASSWORD:-}}"
fi

# --- Connection (required for arangodump/arangosh; override .env if needed) ---
: "${ARANGO_ENDPOINT:?Set ARANGO_ENDPOINT (or LOCAL_ARANGO_ENDPOINT when ARANGO_MODE=LOCAL)}"
: "${ARANGO_USERNAME:?Set ARANGO_USERNAME}"
: "${ARANGO_PASSWORD:?Set ARANGO_PASSWORD}"
: "${ARANGO_DATABASE:?Set ARANGO_DATABASE (database name)}"

# --- Optional: replication for HA on cluster (Enterprise) ---
# export ARANGO_REPLICATION_FACTOR=2
# export ARANGO_WRITE_CONCERN=2

DUMP_DIR="${DUMP_DIR:-./arangodump_${ARANGO_DATABASE}_oneshard_backup}"
ARANGO_CLI_IMAGE="${ARANGO_CLI_IMAGE:-arangodb:3.12}"

# Resolve dump dir to absolute path for Docker volume mounts
mkdir -p "${DUMP_DIR}"
DUMP_ABS="$(cd "$(dirname "${DUMP_DIR}")" && pwd)/$(basename "${DUMP_DIR}")"

use_cli_docker() {
  if command -v arangodump >/dev/null 2>&1 && command -v arangosh >/dev/null 2>&1 && command -v arangorestore >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

if use_cli_docker; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: arangodump/arangosh/arangorestore not on PATH and Docker is not available." >&2
    echo "Install ArangoDB client tools, or install Docker and set ARANGO_CLI_IMAGE if needed." >&2
    exit 127
  fi
  echo "[INFO] Using Docker image ${ARANGO_CLI_IMAGE} for arangodump/arangosh/arangorestore (tools not on PATH)."
fi

echo "[1/4] arangodump -> ${DUMP_ABS}"
if use_cli_docker; then
  docker run --rm \
    -v "${DUMP_ABS}:/dump" \
    "${ARANGO_CLI_IMAGE}" \
    arangodump \
      --server.endpoint "${ARANGO_ENDPOINT}" \
      --server.username "${ARANGO_USERNAME}" \
      --server.password "${ARANGO_PASSWORD}" \
      --server.database "${ARANGO_DATABASE}" \
      --output-directory /dump
else
  arangodump \
    --server.endpoint "${ARANGO_ENDPOINT}" \
    --server.username "${ARANGO_USERNAME}" \
    --server.password "${ARANGO_PASSWORD}" \
    --server.database "${ARANGO_DATABASE}" \
    --output-directory "${DUMP_ABS}"
fi

echo "[2/4] Drop database ${ARANGO_DATABASE} (via arangosh --javascript.execute-string)"
if use_cli_docker; then
  docker run --rm \
    "${ARANGO_CLI_IMAGE}" \
    arangosh \
      --server.endpoint "${ARANGO_ENDPOINT}" \
      --server.username "${ARANGO_USERNAME}" \
      --server.password "${ARANGO_PASSWORD}" \
      --server.database "_system" \
      --javascript.execute-string "db._dropDatabase('${ARANGO_DATABASE}');"
else
  arangosh \
    --server.endpoint "${ARANGO_ENDPOINT}" \
    --server.username "${ARANGO_USERNAME}" \
    --server.password "${ARANGO_PASSWORD}" \
    --server.database "_system" \
    --javascript.execute-string "db._dropDatabase('${ARANGO_DATABASE}');"
fi

echo "[3/4] Recreate empty OneShard database (Python API)"
export ARANGO_DATABASE
PYTHONPATH="${REPO_ROOT}/src" python3 "${REPO_ROOT}/scripts/setup/create_oneshard_database.py" --name "${ARANGO_DATABASE}"

echo "[4/4] arangorestore"
if use_cli_docker; then
  docker run --rm \
    -v "${DUMP_ABS}:/dump" \
    "${ARANGO_CLI_IMAGE}" \
    arangorestore \
      --server.endpoint "${ARANGO_ENDPOINT}" \
      --server.username "${ARANGO_USERNAME}" \
      --server.password "${ARANGO_PASSWORD}" \
      --server.database "${ARANGO_DATABASE}" \
      --input-directory /dump \
      --create-database false
else
  arangorestore \
    --server.endpoint "${ARANGO_ENDPOINT}" \
    --server.username "${ARANGO_USERNAME}" \
    --server.password "${ARANGO_PASSWORD}" \
    --server.database "${ARANGO_DATABASE}" \
    --input-directory "${DUMP_ABS}" \
    --create-database false
fi

echo
echo "Done. Verify in the Web UI → Shards: leaders for this DB should be on one DB-Server."
echo "Dump kept at: ${DUMP_ABS}"
echo ""
echo "Open Shards: log into the cluster Web UI → top-level \"Shards\" (or Cluster → Shards,"
echo "  depending on version) → find collections under database \"${ARANGO_DATABASE}\"."
echo ""
echo "[5/4] Running post-restore rebuild (graph definition, situations, bridges, visualizer)..."
"${REPO_ROOT}/scripts/rebuild_database.sh" --skip-ingestion
