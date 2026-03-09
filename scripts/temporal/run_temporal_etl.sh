#!/usr/bin/env bash
# scripts/temporal/run_temporal_etl.sh
#
# Orchestrates the full Phase 1 temporal ETL pipeline for IC knowledge graph:
#   1. Run commit-by-commit replay on OR1200 repo (etl_temporal_git.py)
#   2. Load temporal nodes + edges into ArangoDB (load_temporal_data.py)
#
# Usage:
#   ./scripts/temporal/run_temporal_etl.sh
#   ./scripts/temporal/run_temporal_etl.sh --limit 10    # test with first 10 commits
#   ./scripts/temporal/run_temporal_etl.sh --dry-run     # validate without writing to DB

set -euo pipefail

# ---- Paths ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
OR1200_DIR="$PROJECT_ROOT/or1200"
DATA_DIR="$PROJECT_ROOT/data/temporal"

# ---- Parse args -------------------------------------------------------------
LIMIT_ARG=""
DRY_RUN_ARG=""
REPO_NAME="openrisc/or1200"
RTL_SUBDIR="rtl/verilog"
BRANCH="master"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit)    LIMIT_ARG="--limit $2"; shift 2 ;;
    --dry-run)  DRY_RUN_ARG="--dry-run"; shift ;;
    --repo)     REPO_NAME="$2"; shift 2 ;;
    --branch)   BRANCH="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ---- Activate venv if present -----------------------------------------------
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# ---- Check OR1200 repo is present -------------------------------------------
if [ ! -d "$OR1200_DIR/.git" ]; then
    echo "[temporal_etl] ERROR: OR1200 git repo not found at $OR1200_DIR"
    echo "  Run: git submodule update --init to initialise it."
    exit 1
fi

echo "============================================================"
echo " Temporal IC Knowledge Graph — ETL Pipeline"
echo " Repo    : $REPO_NAME"
echo " OR1200  : $OR1200_DIR"
echo " Output  : $DATA_DIR"
echo " Limit   : ${LIMIT_ARG:-none}"
echo " Dry run : ${DRY_RUN_ARG:-false}"
echo "============================================================"

mkdir -p "$DATA_DIR"

# ---- Step 1: Temporal Git Replay --------------------------------------------
echo ""
echo "[Step 1/2] Replaying git history …"
python "$SRC_DIR/etl_temporal_git.py" \
    --repo        "$OR1200_DIR" \
    --repo-name   "$REPO_NAME" \
    --rtl-subdir  "$RTL_SUBDIR" \
    --branch      "$BRANCH" \
    --nodes-out   "$DATA_DIR/temporal_nodes.jsonl" \
    --edges-out   "$DATA_DIR/temporal_edges.jsonl" \
    $LIMIT_ARG

echo ""
echo "[Step 1/2] Replay complete."
echo "  Nodes: $(wc -l < "$DATA_DIR/temporal_nodes.jsonl" 2>/dev/null || echo 0)"
echo "  Edges: $(wc -l < "$DATA_DIR/temporal_edges.jsonl" 2>/dev/null || echo 0)"

# ---- Step 2: Load into ArangoDB ---------------------------------------------
echo ""
echo "[Step 2/2] Loading into ArangoDB …"
python "$SCRIPT_DIR/load_temporal_data.py" \
    --nodes-file "$DATA_DIR/temporal_nodes.jsonl" \
    --edges-file "$DATA_DIR/temporal_edges.jsonl" \
    $DRY_RUN_ARG

echo ""
echo "============================================================"
echo " Temporal ETL complete."
echo " Next: run Phase 2 (local GraphRAG) or Phase 3 (multi-repo)"
echo "============================================================"
