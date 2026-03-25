#!/usr/bin/env python3
"""
Create SNAPSHOT_OF edges linking temporal RTL_Module snapshots to their
deep-RTL counterparts (the HEAD-version modules with full sub-component
information: ports, signals, logic chunks, parameters).

This lets users navigate from any temporal module snapshot in the visualizer
to the fully-detailed version of the same module.

Run:
    PYTHONPATH=src python3 scripts/setup/create_snapshot_of_edges.py

Idempotent: safe to re-run — existing edges are truncated and rebuilt.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from db_utils import get_db
from config_temporal import TEMPORAL_GRAPH_NAME

EDGE_COLLECTION = "SNAPSHOT_OF"
GRAPH_NAME = TEMPORAL_GRAPH_NAME

REPO_MAP = {
    "lowRISC/ibex.git": "IBEX",
    "openrisc/mor1kx.git": "MOR1KX",
    "openrisc/or1200.git": "OR1200",
    "openrisc/or1k_marocchino.git": "MAROCCHINO",
}


def ensure_collection(db) -> None:
    if not db.has_collection(EDGE_COLLECTION):
        db.create_collection(EDGE_COLLECTION, edge=True)
        print(f"[create] Edge collection: {EDGE_COLLECTION}")
    else:
        print(f"[exists] Edge collection: {EDGE_COLLECTION}")


def add_to_graph(db) -> None:
    if not db.has_graph(GRAPH_NAME):
        print(f"[skip]  Graph '{GRAPH_NAME}' not found")
        return

    graph = db.graph(GRAPH_NAME)
    edge_defs = graph.edge_definitions()
    existing_edge_cols = {ed["edge_collection"] for ed in edge_defs}

    if EDGE_COLLECTION in existing_edge_cols:
        print(f"[exists] {EDGE_COLLECTION} already in graph")
        return

    graph.create_edge_definition(
        edge_collection=EDGE_COLLECTION,
        from_vertex_collections=["RTL_Module"],
        to_vertex_collections=["RTL_Module"],
    )
    print(f"[graph]  Added {EDGE_COLLECTION}: RTL_Module → RTL_Module")


def build_edges(db) -> int:
    col = db.collection(EDGE_COLLECTION)
    col.truncate()
    print(f"[truncate] {EDGE_COLLECTION}")

    aql = """
    FOR dm IN RTL_Module
      FILTER dm.repo IN @deep_repos
      FOR tm IN RTL_Module
        FILTER tm.repo NOT IN @deep_repos
        FILTER tm.label == dm.name
        FILTER @repo_map[tm.repo] == dm.repo
        COLLECT deep_id = dm._id, temporal_id = tm._id,
                deep_name = dm.name, temporal_repo = tm.repo
        INSERT {
          _from: temporal_id,
          _to:   deep_id,
          type:  "snapshot_of",
          temporal_repo: temporal_repo,
          deep_repo: @repo_map[temporal_repo],
          module_name: deep_name
        } INTO @@edge_col
        RETURN NEW._key
    """

    cursor = db.aql.execute(
        aql,
        bind_vars={
            "deep_repos": list(REPO_MAP.values()),
            "repo_map": REPO_MAP,
            "@edge_col": EDGE_COLLECTION,
        },
        count=True,
    )
    keys = list(cursor)
    return len(keys)


def install_canvas_action(db) -> None:
    if not db.has_collection("_canvasActions"):
        print("[skip]  _canvasActions not found")
        return

    action = {
        "_key": "ic_snapshot_internals",
        "name": "[RTL_Module] Show deep-RTL internals (temporal → HEAD)",
        "description": (
            "From a temporal module snapshot, follow SNAPSHOT_OF to the "
            "deep-RTL HEAD version and show its ports, signals, logic chunks, "
            "and parameters."
        ),
        "graphName": GRAPH_NAME,
        "aql": """// Navigate from temporal snapshot → deep-RTL HEAD module → sub-components
LET snapshot_edges = (
  FOR deep IN OUTBOUND @startNode SNAPSHOT_OF
    RETURN { from: @startNode._id, to: deep._id, edge: 'SNAPSHOT_OF' }
)
LET deep_mod = FIRST(FOR d IN OUTBOUND @startNode SNAPSHOT_OF RETURN d)
LET sub_components = deep_mod != null ? (
  FOR v, e IN 1..1 OUTBOUND deep_mod HAS_PORT, HAS_SIGNAL, CONTAINS, HAS_PARAMETER
    RETURN { vertex: v, edge: e }
) : []
LET paths = (
  FOR sc IN sub_components
    LET p = {
      edges: [
        FIRST(FOR e IN SNAPSHOT_OF FILTER e._from == @startNode._id AND e._to == deep_mod._id RETURN e),
        sc.edge
      ],
      vertices: [@startNode, deep_mod, sc.vertex]
    }
    RETURN p
)
RETURN paths""",
    }

    col = db.collection("_canvasActions")
    try:
        existing = col.get("ic_snapshot_internals")
        if existing:
            col.update(action)
            print("[update] Canvas action: ic_snapshot_internals")
        else:
            col.insert(action)
            print("[insert] Canvas action: ic_snapshot_internals")
    except Exception:
        try:
            col.insert(action)
            print("[insert] Canvas action: ic_snapshot_internals")
        except Exception:
            col.update(action)
            print("[update] Canvas action: ic_snapshot_internals")

    if db.has_collection("_viewpointActions"):
        vp_col = db.collection("_viewpointActions")
        vps = list(vp_col.find({"graphName": GRAPH_NAME}))
        for vp in vps:
            actions = vp.get("actions", [])
            if "ic_snapshot_internals" not in actions:
                actions.append("ic_snapshot_internals")
                vp_col.update({"_key": vp["_key"], "actions": actions})
                print(f"[link]   Canvas action → viewpoint {vp['_key']}")


def main() -> None:
    print("=" * 60)
    print("SNAPSHOT_OF Edge Builder")
    print("=" * 60)
    db = get_db()
    print(f"Connected: {db.name}\n")

    print("── Step 1: Ensure edge collection ──")
    ensure_collection(db)

    print("\n── Step 2: Add to named graph ──")
    add_to_graph(db)

    print("\n── Step 3: Build SNAPSHOT_OF edges ──")
    count = build_edges(db)
    print(f"[done]   Created {count} SNAPSHOT_OF edges")

    print("\n── Step 4: Install canvas action ──")
    install_canvas_action(db)

    print("\n" + "=" * 60)
    print("Done. In the Graph Visualizer:")
    print("  • Temporal modules now link to their deep-RTL counterpart")
    print("  • Right-click a temporal module → '[RTL_Module] Show deep-RTL internals'")
    print("  • to see ports, signals, logic chunks, parameters")
    print("=" * 60)


if __name__ == "__main__":
    main()
