#!/usr/bin/env bash
# Local ER MCP launcher for the ic-knowledge-graph project.
# Connects to the local Docker ArangoDB (localhost:8530) without going through
# run_mcp_server.sh, which sources dnb_er/.env and would overwrite the endpoint.
#
# Referenced by ~/.cursor/mcp.json as:
#   ic-knowledge-graph-arango-entity-resolution-local-mcp

set -euo pipefail

source /Users/arthurkeen/code/dnb_er/.venv/bin/activate

export ARANGO_HOST=localhost
export ARANGO_PORT=8530
export ARANGO_TLS=false
export ARANGO_DATABASE=ic-knowledge-graph-temporal
export ARANGO_USERNAME=root
export ARANGO_PASSWORD=

exec arango-er-mcp
