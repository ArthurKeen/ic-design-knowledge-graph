#!/usr/bin/env bash
# =============================================================================
# scripts/multi_repo/run_all_repos.sh
#
# Orchestrates the full multi-repo ingestion pipeline:
#   1. Clones / updates all repos in repo_registry.yaml
#   2. Runs temporal ETL (commit replay + epoch detection)
#   3. Runs local GraphRAG pipeline (doc chunking + entity extraction + embed)
#   4. Prints a summary of results
#
# Usage:
#   ./scripts/multi_repo/run_all_repos.sh              # all repos, all steps
#   ./scripts/multi_repo/run_all_repos.sh --repo mor1kx
#   ./scripts/multi_repo/run_all_repos.sh --no-graphrag
#   ./scripts/multi_repo/run_all_repos.sh --dry-run
#   ./scripts/multi_repo/run_all_repos.sh --embedding-backend openai
#
# Options forwarded to ingest_repo.py:
#   --repo NAME            Ingest only this repo (default: all in registry)
#   --no-clone             Skip git clone/pull
#   --no-temporal          Skip temporal ETL
#   --no-graphrag          Skip local GraphRAG
#   --dry-run              Run all steps but write nothing to ArangoDB
#   --commit-limit N       Process at most N commits per repo (useful for testing)
#   --embedding-backend B  sentence_transformers (default) or openai
#
# Environment:
#   Reads from .env at project root. Make sure these are set:
#     ARANGO_HOST, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE
#     OPENAI_API_KEY (optional — only needed for --embedding-backend openai)
#
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # Safe loader: export each KEY=VALUE line without shell-interpreting the value.
    # Using 'export KEY=VALUE' with the literal string prevents $SPECIAL chars in
    # passwords (e.g. $GTEaYL) from being expanded as shell variables.
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip blank lines and comments
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        # Only process lines that look like KEY=VALUE
        if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            # Strip surrounding double-quotes if present
            val="${val#\"}"
            val="${val%\"}"
            export "$key=$val"
        fi
    done < "${ENV_FILE}"
    echo "[run_all_repos] Loaded .env from ${ENV_FILE}"
else
    echo "[run_all_repos] WARNING: .env not found at ${ENV_FILE}"
fi

# ---------------------------------------------------------------------------
# Python environment — prefer project .venv if present
# ---------------------------------------------------------------------------
VENV="${PROJECT_ROOT}/.venv"
if [[ -d "${VENV}" && -x "${VENV}/bin/python" ]]; then
    CANDIDATE="${VENV}/bin/python"
    # Validate venv has required packages; fall back if not
    if "${CANDIDATE}" -c "import yaml, arango" 2>/dev/null; then
        PYTHON="${CANDIDATE}"
    else
        echo "[run_all_repos] .venv missing deps — falling back to system python3"
        PYTHON="$(command -v python3 || command -v python)"
    fi
else
    PYTHON="$(command -v python3 || command -v python)"
fi

echo "[run_all_repos] Python: ${PYTHON}"
echo "[run_all_repos] Project: ${PROJECT_ROOT}"
echo "[run_all_repos] DB: ${ARANGO_DATABASE:-<not set>} @ ${ARANGO_HOST:-<not set>}"
echo ""

# ---------------------------------------------------------------------------
# Time-stamp for log scoping
# ---------------------------------------------------------------------------
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${PROJECT_ROOT}/data/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/ingest_${RUN_TS}.log"

echo "[run_all_repos] Log: ${LOG_FILE}"
echo ""

# ---------------------------------------------------------------------------
# Run the Python ingestor, forwarding all arguments
# ---------------------------------------------------------------------------
INGESTOR="${SCRIPT_DIR}/ingest_repo.py"

echo "[run_all_repos] Starting ingestion at $(date)"
echo "================================================================"

# tee to both stdout and log file
"${PYTHON}" "${INGESTOR}" "$@" 2>&1 | tee "${LOG_FILE}"

EXIT_CODE="${PIPESTATUS[0]}"

echo ""
echo "================================================================"
echo "[run_all_repos] Ingestion finished at $(date)"

if [[ "${EXIT_CODE}" -eq 0 ]]; then
    echo "[run_all_repos] ✅ All repos ingested successfully."
    echo "[run_all_repos] Log written to: ${LOG_FILE}"
else
    echo "[run_all_repos] ❌ Ingestion exited with code ${EXIT_CODE}. See log: ${LOG_FILE}"
fi

exit "${EXIT_CODE}"
