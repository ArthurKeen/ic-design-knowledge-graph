#!/usr/bin/env python3
"""
Install the "Integrated Circuit" theme and demo canvas actions into the
ArangoDB Graph Visualizer for IC_Temporal_Knowledge_Graph.

Prerequisites: open the graph once in the UI so _graphThemeStore,
_canvasActions, _viewpoints, and _viewpointActions exist.

Usage:
    PYTHONPATH=src python3 scripts/setup/install_ic_theme.py
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from db_utils import get_db  # noqa: E402
from config_temporal import TEMPORAL_GRAPH_NAME  # noqa: E402

GRAPH_NAME = TEMPORAL_GRAPH_NAME
THEME_NAME = "Integrated Circuit"
THEME_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "hardware_design_theme.json"
)

CANVAS_ACTIONS = [
    {
        "_key": "ic_rtl_module_hierarchy",
        "name": "[RTL_Module] Module hierarchy (ports + signals + params)",
        "title": "[RTL_Module] Module hierarchy (ports + signals + params)",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..1 OUTBOUND @startNode "
            "HAS_PORT, HAS_SIGNAL, HAS_PARAMETER, CONTAINS "
            "LIMIT 200 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_rtl_module_dependencies",
        "name": "[RTL_Module] Instantiation dependencies",
        "title": "[RTL_Module] Instantiation dependencies",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..2 ANY @startNode DEPENDS_ON "
            "OPTIONS { uniqueVertices: 'path' } "
            "LIMIT 100 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_rtl_module_wiring",
        "name": "[RTL_Module] Wiring (WIRED_TO from ports/signals)",
        "title": "[RTL_Module] Wiring (WIRED_TO from ports/signals)",
        "graphId": GRAPH_NAME,
        "query": (
            "LET children = (FOR c IN OUTBOUND @startNode HAS_PORT, HAS_SIGNAL RETURN c) "
            "FOR child IN children "
            "  FOR v, e, p IN 1..1 ANY child WIRED_TO "
            "  LIMIT 200 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_resolved_to_golden",
        "name": "[RTL_Module] Semantic bridge → Golden Entities",
        "title": "[RTL_Module] Semantic bridge → Golden Entities",
        "graphId": GRAPH_NAME,
        "query": (
            "LET children = (FOR c IN OUTBOUND @startNode HAS_PORT, HAS_SIGNAL RETURN c) "
            "FOR child IN children "
            "  FOR v, e, p IN 1..1 OUTBOUND child RESOLVED_TO "
            "  RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_golden_cross_repo",
        "name": "[Golden_Entities] Cross-repo bridges",
        "title": "[Golden_Entities] Cross-repo bridges",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..1 ANY @startNode "
            "CROSS_REPO_SIMILAR_TO, CROSS_REPO_EVOLVED_FROM "
            "RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_golden_full_graphrag",
        "name": "[Golden_Entities] Full GraphRAG path (→ entities → chunks)",
        "title": "[Golden_Entities] Full GraphRAG path (→ entities → chunks)",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..2 ANY @startNode "
            "GRAPH 'IC_Temporal_Knowledge_Graph' "
            "OPTIONS { uniqueVertices: 'path' } "
            "LIMIT 150 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_epoch_modules",
        "name": "[DesignEpoch] Modules at this epoch",
        "title": "[DesignEpoch] Modules at this epoch",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..1 INBOUND @startNode BELONGS_TO_EPOCH "
            "LIMIT 200 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_commit_modified",
        "name": "[GitCommit] Modules modified by this commit",
        "title": "[GitCommit] Modules modified by this commit",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..1 OUTBOUND @startNode MODIFIED "
            "RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_module_time_travel",
        "name": "[RTL_Module] Time travel (epochs + commits)",
        "title": "[RTL_Module] Time travel (epochs + commits)",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..1 ANY @startNode "
            "BELONGS_TO_EPOCH, MODIFIED "
            "RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_deep_traversal",
        "name": "[RTL_Module] Deep traversal (4 hops, all edges)",
        "title": "[RTL_Module] Deep traversal (4 hops, all edges)",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..4 ANY @startNode "
            "GRAPH 'IC_Temporal_Knowledge_Graph' "
            "OPTIONS { uniqueVertices: 'path' } "
            "LIMIT 300 RETURN p"
        ),
        "bindVariables": {},
    },
    {
        "_key": "ic_spec_to_successor",
        "name": "[Chunks] Spec concept → cross-repo successors",
        "title": "[Chunks] Spec concept → cross-repo successors",
        "graphId": GRAPH_NAME,
        "query": (
            "FOR v, e, p IN 1..3 ANY @startNode "
            "GRAPH 'IC_Temporal_Knowledge_Graph' "
            "OPTIONS { uniqueVertices: 'path' } "
            "LIMIT 100 RETURN p"
        ),
        "bindVariables": {},
    },
]


def install_theme(db):
    if not db.has_collection("_graphThemeStore"):
        print("[SKIP] _graphThemeStore not found — open the graph in the UI once first.")
        return False

    with open(THEME_FILE) as f:
        theme = json.load(f)

    theme["name"] = THEME_NAME
    theme["description"] = (
        "IC Knowledge Graph — multi-repo color coding, RTL structure, "
        "semantic bridges, temporal epochs, cross-repo edges"
    )
    now = datetime.utcnow().isoformat() + "Z"
    theme["createdAt"] = now
    theme["updatedAt"] = now

    col = db.collection("_graphThemeStore")
    existing = list(col.find({"graphId": GRAPH_NAME, "name": THEME_NAME}))
    if existing:
        col.update({"_key": existing[0]["_key"]}, theme)
        print(f"[UPDATED] Theme '{THEME_NAME}' ({existing[0]['_id']})")
    else:
        result = col.insert(theme)
        print(f"[CREATED] Theme '{THEME_NAME}' ({result['_id']})")
    print(f"  {len(theme['nodeConfigMap'])} node configs, {len(theme['edgeConfigMap'])} edge configs")
    return True


def install_actions(db):
    if not db.has_collection("_canvasActions"):
        print("[SKIP] _canvasActions not found — open the graph in the UI once first.")
        return 0

    col = db.collection("_canvasActions")
    count = 0
    for action in CANVAS_ACTIONS:
        action.setdefault("updatedAt", datetime.utcnow().isoformat() + "Z")
        if col.has(action["_key"]):
            col.update(action)
            print(f"  [UPD] {action['name']}")
        else:
            col.insert(action)
            print(f"  [NEW] {action['name']}")
        count += 1
    print(f"  {count} canvas actions installed.")
    return count


def link_actions(db):
    if not db.has_collection("_viewpoints"):
        print("[SKIP] _viewpoints not found — open the graph in the UI once first.")
        return 0

    vp_col = db.collection("_viewpoints")
    viewpoints = list(vp_col.all())
    vp = None
    for v in viewpoints:
        if v.get("graphId") == GRAPH_NAME:
            vp = v
            break
    if vp is None and viewpoints:
        vp = viewpoints[0]
    if vp is None:
        print("[SKIP] No viewpoints found. Open graph in UI first.")
        return 0

    if not db.has_collection("_viewpointActions"):
        db.create_collection("_viewpointActions", edge=True)

    edge_col = db.collection("_viewpointActions")
    linked = 0
    for action in CANVAS_ACTIONS:
        _from = vp["_id"]
        _to = f"_canvasActions/{action['_key']}"
        if not list(edge_col.find({"_from": _from, "_to": _to})):
            edge_col.insert({
                "_from": _from,
                "_to": _to,
                "createdAt": datetime.utcnow().isoformat() + "Z",
            })
            linked += 1
    print(f"  {linked} new viewpoint links created ({len(CANVAS_ACTIONS) - linked} already existed).")
    return linked


def main():
    db = get_db()
    print(f"Connected: {db.name}")
    print()

    print("── Theme ──")
    install_theme(db)
    print()

    print("── Canvas Actions ──")
    install_actions(db)
    print()

    print("── Viewpoint Links ──")
    link_actions(db)
    print()

    print("Done. In the Graph Visualizer:")
    print(f"  • Legend → theme dropdown → select '{THEME_NAME}'")
    print("  • Right-click any node → Canvas Actions to see the demo actions")


if __name__ == "__main__":
    main()
