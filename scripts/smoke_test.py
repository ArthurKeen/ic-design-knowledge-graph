#!/usr/bin/env python3
"""
Core smoke test for the IC Knowledge Graph project.

This script is intentionally lightweight:
- No GraphRAG service calls
- No data import
- Verifies configuration can connect to ArangoDB
- Optionally verifies expected graph/collections exist
"""

import argparse
import os
import sys
from typing import Iterable

# Allow running from repo root without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def _fail(msg: str, code: int = 2) -> None:
    print(f"[SMOKE][FAIL] {msg}", file=sys.stderr)
    raise SystemExit(code)


def _ok(msg: str) -> None:
    print(f"[SMOKE][OK] {msg}")


def _info(msg: str) -> None:
    print(f"[SMOKE][INFO] {msg}")


def _check_collections(db, names: Iterable[str], require_nonempty: bool) -> None:
    missing = []
    empty = []
    for name in names:
        if not db.has_collection(name):
            missing.append(name)
            continue
        if require_nonempty:
            try:
                if db.collection(name).count() == 0:
                    empty.append(name)
            except Exception:
                # Some system collections may not support count; ignore here.
                pass

    if missing:
        _fail(f"Missing collections: {', '.join(missing)}")
    if empty:
        _fail(f"Collections exist but are empty: {', '.join(empty)}")


def _check_graph_exists() -> None:
    # Use HTTP API to avoid depending on specific python-arango graph helpers.
    import requests

    from config import GRAPH_NAME
    from db_utils import get_api_url, get_requests_auth

    url = get_api_url("gharial")
    r = requests.get(url, auth=get_requests_auth(), timeout=15)
    r.raise_for_status()
    graphs = {g.get("name") for g in r.json().get("graphs", [])}
    if GRAPH_NAME not in graphs:
        _fail(f"Graph '{GRAPH_NAME}' not found in database")
    _ok(f"Graph '{GRAPH_NAME}' exists")


def main() -> int:
    p = argparse.ArgumentParser(description="IC Knowledge Graph smoke test")
    p.add_argument("--require-graph", action="store_true", help="Fail if the named graph is missing")
    p.add_argument(
        "--require-nonempty",
        action="store_true",
        help="When checking collections, also require count() > 0",
    )
    p.add_argument(
        "--check-graphrag",
        action="store_true",
        help="Also check GraphRAG collections exist (does not run services)",
    )
    args = p.parse_args()

    # Import inside main so failures show as actionable messages.
    try:
        from config import (
            ARANGO_ENDPOINT,
            ARANGO_DATABASE,
            ARANGO_MODE,
            GRAPH_NAME,
            COL_MODULE,
            COL_PORT,
            COL_SIGNAL,
            COL_LOGIC,
            COL_COMMIT,
            COL_AUTHOR,
            GRAPHRAG_PREFIX,
        )
        from db_utils import get_db
    except Exception as e:
        _fail(f"Failed to import project modules (check PYTHONPATH / install): {e}", code=3)

    _info(f"Mode: {ARANGO_MODE}")
    _info(f"Endpoint: {ARANGO_ENDPOINT}")
    _info(f"Database: {ARANGO_DATABASE}")
    _info(f"Graph: {GRAPH_NAME}")

    try:
        db = get_db()
        # Force a trivial roundtrip
        version = db.version()
    except Exception as e:
        _fail(f"Unable to connect to ArangoDB: {e}")

    _ok(f"Connected to ArangoDB {version} (db='{db.name}')")

    # Core collections that should exist after running the main ETL + create_graph.
    core_collections = [COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC, COL_COMMIT, COL_AUTHOR]
    _check_collections(db, core_collections, require_nonempty=args.require_nonempty)
    _ok("Core collections are present")

    if args.check_graphrag:
        graphrag_cols = [
            f"{GRAPHRAG_PREFIX}Documents",
            f"{GRAPHRAG_PREFIX}Chunks",
            f"{GRAPHRAG_PREFIX}Entities",
            f"{GRAPHRAG_PREFIX}Golden_Entities",
            f"{GRAPHRAG_PREFIX}Relations",
            f"{GRAPHRAG_PREFIX}Golden_Relations",
            f"{GRAPHRAG_PREFIX}Communities",
        ]
        _check_collections(db, graphrag_cols, require_nonempty=args.require_nonempty)
        _ok("GraphRAG collections are present")

    if args.require_graph:
        _check_graph_exists()

    _ok("Smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

