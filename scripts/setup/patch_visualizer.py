#!/usr/bin/env python3
"""
One-shot patch script for the IC Temporal Knowledge Graph visualizer setup.

Fixes applied:
1. Adds missing RTL_* collections to the Default theme (RTL_Signal, RTL_Port,
   RTL_LogicChunk, RTL_Parameter) so nodes show icons regardless of which theme
   is selected.
2. Adds missing vertex collections to the IC_Temporal_Knowledge_Graph named graph
   (Communities, Documents, DesignSituation) so they are reachable in traversals.
3. Re-installs the hardware-design theme from docs/hardware_design_theme.json
   (which now has the correct graphId and full multi-repo node/edge coverage).

Run:
    python scripts/setup/patch_visualizer.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from db_utils import get_db
from config_temporal import TEMPORAL_GRAPH_NAME


GRAPH_NAME = TEMPORAL_GRAPH_NAME
THEME_FILE = Path(__file__).parent.parent.parent / "docs" / "hardware_design_theme.json"

# Collections that exist in the DB but are not yet in the named graph
MISSING_VERTEX_COLLECTIONS = [
    "OR1200_Communities",
    "IBEX_Communities",
    "MAROCCHINO_Communities",
    "MOR1KX_Communities",
    "OR1200_Documents",
    "IBEX_Documents",
    "MAROCCHINO_Documents",
    "MOR1KX_Documents",
    "DesignSituation",
]

# RTL collections missing from the Default theme (all exist in DB)
MISSING_RTL_NODE_CONFIGS = {
    "RTL_Signal": {
        "background": {"color": "#48bb78", "iconName": "mdi:signal-variant"},
        "labelAttribute": "name",
        "hoverInfoAttributes": ["name", "datatype", "expanded_name", "parent_module"],
        "rules": [],
    },
    "RTL_Port": {
        "background": {"color": "#ed64a6", "iconName": "mdi:usb-c-port"},
        "labelAttribute": "name",
        "hoverInfoAttributes": ["name", "direction", "datatype", "expanded_name", "parent_module"],
        "rules": [],
    },
    "RTL_LogicChunk": {
        "background": {"color": "#667eea", "iconName": "mdi:code-braces"},
        "labelAttribute": "name",
        "hoverInfoAttributes": ["name", "parent_module"],
        "rules": [],
    },
    "RTL_Parameter": {
        "background": {"color": "#f6ad55", "iconName": "mdi:cog"},
        "labelAttribute": "name",
        "hoverInfoAttributes": ["name", "value", "evaluated_value", "parent_module"],
        "rules": [],
    },
}

# Edge collections missing from the Default theme
MISSING_DEFAULT_EDGE_CONFIGS = {
    "RESOLVED_TO": {
        "lineStyle": {"color": "#d69e2e", "thickness": 1.2},
        "labelStyle": {"color": "#1d2531"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "_id",
        "hoverInfoAttributes": ["score", "method"],
        "rules": [],
    },
    "HAS_PORT": {
        "lineStyle": {"color": "#4299e1", "thickness": 0.7},
        "labelStyle": {"color": "#1d2531"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "type",
        "hoverInfoAttributes": ["type"],
        "rules": [],
    },
    "HAS_SIGNAL": {
        "lineStyle": {"color": "#9f7aea", "thickness": 0.7},
        "labelStyle": {"color": "#1d2531"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "type",
        "hoverInfoAttributes": ["type"],
        "rules": [],
    },
    "CROSS_REPO_SIMILAR_TO": {
        "lineStyle": {"color": "#F97316", "thickness": 2.5},
        "labelStyle": {"color": "#F97316"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "similarity_score",
        "hoverInfoAttributes": ["similarity_score", "similarity_type", "method"],
        "rules": [],
    },
    "CROSS_REPO_EVOLVED_FROM": {
        "lineStyle": {"color": "#EF4444", "thickness": 2.0, "lineType": "dashed"},
        "labelStyle": {"color": "#EF4444"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "type",
        "hoverInfoAttributes": ["type", "similarity_score"],
        "rules": [],
    },
    "BELONGS_TO_EPOCH": {
        "lineStyle": {"color": "#6366F1", "thickness": 0.5, "lineType": "dashed"},
        "labelStyle": {"color": "#1d2531"},
        "arrowStyle": {"sourceArrowShape": "none", "targetArrowShape": "triangle"},
        "labelAttribute": "doc_version",
        "hoverInfoAttributes": ["doc_version", "type"],
        "rules": [],
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ──────────────────────────────────────────────────────────────────────────────
# Fix 1: Default theme — add missing RTL_* node configs and key edge configs
# ──────────────────────────────────────────────────────────────────────────────

def patch_default_theme(db) -> None:
    if not db.has_collection("_graphThemeStore"):
        print("  [SKIP] _graphThemeStore not found — open the graph in the UI once first")
        return

    col = db.collection("_graphThemeStore")
    defaults = list(col.find({"name": "Default"}))
    if not defaults:
        print("  [SKIP] Default theme not found in _graphThemeStore")
        return

    doc = defaults[0]
    key = doc["_key"]
    changed = False

    node_map = doc.get("nodeConfigMap") or {}
    for coll_name, config in MISSING_RTL_NODE_CONFIGS.items():
        if coll_name not in node_map:
            node_map[coll_name] = config
            print(f"  [ADD node] Default theme ← {coll_name}")
            changed = True
        else:
            print(f"  [SKIP node] Default theme already has {coll_name}")

    edge_map = doc.get("edgeConfigMap") or {}
    for edge_name, config in MISSING_DEFAULT_EDGE_CONFIGS.items():
        if edge_name not in edge_map:
            edge_map[edge_name] = config
            print(f"  [ADD edge] Default theme ← {edge_name}")
            changed = True
        else:
            print(f"  [SKIP edge] Default theme already has {edge_name}")

    if changed:
        col.update({
            "_key": key,
            "nodeConfigMap": node_map,
            "edgeConfigMap": edge_map,
            "updatedAt": now_iso(),
        })
        print("  [OK] Default theme updated")
    else:
        print("  [OK] Default theme already up to date — no changes needed")


# ──────────────────────────────────────────────────────────────────────────────
# Fix 2: Named graph — add missing vertex collections as orphan collections
# ──────────────────────────────────────────────────────────────────────────────

def patch_named_graph(db) -> None:
    if not db.has_graph(GRAPH_NAME):
        print(f"  [SKIP] Graph '{GRAPH_NAME}' not found")
        return

    graph = db.graph(GRAPH_NAME)

    # Build set of all vertex collections currently in the graph
    existing_vertex_colls: set[str] = set()
    for ed in graph.edge_definitions():
        existing_vertex_colls.update(ed.get("from_vertex_collections", []))
        existing_vertex_colls.update(ed.get("to_vertex_collections", []))
    existing_vertex_colls.update(graph.vertex_collections())

    for coll_name in MISSING_VERTEX_COLLECTIONS:
        if coll_name in existing_vertex_colls:
            print(f"  [SKIP] {coll_name} already in graph")
            continue
        if not db.has_collection(coll_name):
            print(f"  [SKIP] {coll_name} does not exist in DB")
            continue
        graph.add_vertex_collection(coll_name)
        print(f"  [ADD] {coll_name} → {GRAPH_NAME}")


# ──────────────────────────────────────────────────────────────────────────────
# Fix 3: Install / update hardware-design theme from JSON file
# ──────────────────────────────────────────────────────────────────────────────

def install_hardware_design_theme(db) -> None:
    if not db.has_collection("_graphThemeStore"):
        print("  [SKIP] _graphThemeStore not found — open the graph in the UI once first")
        return

    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    ts = now_iso()
    theme["updatedAt"] = ts
    theme.setdefault("createdAt", ts)

    col = db.collection("_graphThemeStore")
    existing = list(col.find({"graphId": theme["graphId"], "name": theme["name"]}))
    if existing:
        key = existing[0]["_key"]
        col.update({"_key": key, **theme})
        print(f"  [UPDATE] '{theme['name']}' theme (graphId={theme['graphId']})")
    else:
        result = col.insert(theme)
        print(f"  [INSERT] '{theme['name']}' theme → {result['_id']}")

    n_nodes = len(theme.get("nodeConfigMap", {}))
    n_edges = len(theme.get("edgeConfigMap", {}))
    print(f"  Coverage: {n_nodes} node collections, {n_edges} edge collections")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("IC Knowledge Graph — Visualizer Patch")
    print("=" * 60)

    db = get_db()
    print(f"Connected: {db.name}\n")

    print("── Fix 1: Patch Default theme (add missing RTL_* nodes + key edges) ──")
    patch_default_theme(db)

    print("\n── Fix 2: Add missing vertex collections to named graph ──")
    patch_named_graph(db)

    print("\n── Fix 3: Install/update hardware-design theme ──")
    install_hardware_design_theme(db)

    print("\n" + "=" * 60)
    print("Done. In the Graph Visualizer:")
    print("  • Refresh the page")
    print("  • RTL_Signal / RTL_Port / RTL_LogicChunk / RTL_Parameter now have icons")
    print("  • Switch to 'hardware-design' theme via Legend → theme dropdown")
    print("    for full per-repo color coding and cross-repo edge highlighting")
    print("=" * 60)


if __name__ == "__main__":
    main()
