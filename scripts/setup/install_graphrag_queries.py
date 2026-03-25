#!/usr/bin/env python3
"""
GraphRAG Query & Canvas Action Installer
IC Knowledge Graph — ArangoDB Graph Visualizer setup

Installs four categories of saved queries and matching canvas actions:
  1. RTL module portrait  — module + ports/signals + RESOLVED_TO targets
  2. Golden entity view   — community peers + cross-repo neighbours
  3. RESOLVED_TO bridge   — see which RTL nodes map to a golden entity
  4. Cross-repo lineage   — CROSS_REPO_EVOLVED_FROM chain across designs

Usage:
    PYTHONPATH=src python3 scripts/setup/install_graphrag_queries.py
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db, get_system_db
from config_temporal import TEMPORAL_GRAPH_NAME

GRAPH_ID = TEMPORAL_GRAPH_NAME

# ---------------------------------------------------------------------------
# Saved queries (installed into _system._editor_saved_queries)
# ---------------------------------------------------------------------------

SAVED_QUERIES = [
    # ---- RTL Module Portrait -----------------------------------------------
    {
        "_key": "ickgq_rtl_module_portrait",
        "name": "RTL: Module portrait (ports + signals + RESOLVED_TO)",
        "description": (
            "Show a single RTL module with all its ports and signals, "
            "plus the golden entities each port/signal resolves to. "
            "Change @module to any RTL_Module/_key."
        ),
        "queryText": """\
// RTL module portrait: ports, signals, and their semantic anchors
LET mod = DOCUMENT(@module)

LET ports = (
    FOR p IN 1..1 OUTBOUND mod HAS_PORT
        LET golden = (
            FOR g IN 1..1 OUTBOUND p RESOLVED_TO
                RETURN {name: g.name, collection: SPLIT(g._id, "/")[0], score: g.score}
        )
        RETURN {
            name:      p.name,
            direction: p.direction,
            width:     p.width,
            resolved:  golden
        }
)

LET signals = (
    FOR s IN 1..1 OUTBOUND mod HAS_SIGNAL
        LET golden = (
            FOR g IN 1..1 OUTBOUND s RESOLVED_TO
                RETURN {name: g.name, collection: SPLIT(g._id, "/")[0], score: g.score}
        )
        RETURN {
            name:     s.name,
            width:    s.width,
            resolved: golden
        }
)

RETURN {
    module:   mod._key,
    name:     mod.name,
    repo:     mod.repo,
    ports:    ports,
    signals:  signals
}
""",
        "bindVariables": {"module": "RTL_Module/or1200_cpu"},
    },

    # ---- Golden entity community view --------------------------------------
    {
        "_key": "ickgq_golden_community",
        "name": "GraphRAG: Golden entity — community + cross-repo neighbours",
        "description": (
            "Given a golden entity, show its Leiden community peers, "
            "cross-repo similar entities, and RTL nodes that resolve to it. "
            "Change @golden to any *_Golden_Entities document ID."
        ),
        "queryText": """\
// Golden entity: community peers, cross-repo neighbours, RTL implementations
LET ent = DOCUMENT(@golden)

LET peers = (
    FOR peer IN CONCAT_SEPARATOR("", SPLIT(ent._id, "/")[0])
        FILTER peer.community == ent.community AND peer._id != ent._id
        LIMIT 10
        RETURN {name: peer.name, description: LEFT(peer.description, 120)}
)

LET cross_repo = (
    FOR edge IN CROSS_REPO_SIMILAR_TO
        FILTER edge._from == ent._id OR edge._to == ent._id
        LET other = edge._from == ent._id ? DOCUMENT(edge._to) : DOCUMENT(edge._from)
        RETURN {
            name:       other.name,
            collection: SPLIT(other._id, "/")[0],
            sim_score:  edge.similarity_score
        }
)

LET rtl_impls = (
    FOR edge IN RESOLVED_TO
        FILTER edge._to == ent._id
        LET rtl = DOCUMENT(edge._from)
        RETURN {
            name:   rtl.name,
            type:   SPLIT(rtl._id, "/")[0],
            repo:   rtl.repo,
            method: edge.match_method,
            score:  edge.score
        }
)

RETURN {
    entity:     ent.name,
    collection: SPLIT(ent._id, "/")[0],
    community:  ent.community,
    description: ent.description,
    peers:      peers,
    cross_repo: cross_repo,
    rtl_impls:  rtl_impls
}
""",
        "bindVariables": {"golden": "OR1200_Golden_Entities/TLB"},
    },

    # ---- RESOLVED_TO bridge audit ------------------------------------------
    {
        "_key": "ickgq_resolved_to_bridge",
        "name": "GraphRAG: RESOLVED_TO bridge — all RTL → golden mappings for a repo",
        "description": (
            "List every RTL node that resolves to a golden entity for a given repo, "
            "sorted by match method then score. "
            "Change @repo to 'or1200', 'mor1kx', 'marocchino', or 'ibex'."
        ),
        "queryText": """\
// All RESOLVED_TO edges for a repo — quality audit view
FOR edge IN RESOLVED_TO
    LET rtl    = DOCUMENT(edge._from)
    LET golden = DOCUMENT(edge._to)
    FILTER rtl.repo == @repo
    SORT edge.match_method ASC, edge.score DESC
    RETURN {
        rtl_name:     rtl.name,
        rtl_type:     SPLIT(rtl._id, "/")[0],
        golden_name:  golden.name,
        golden_coll:  SPLIT(golden._id, "/")[0],
        method:       edge.match_method,
        score:        edge.score
    }
""",
        "bindVariables": {"repo": "or1200"},
    },

    # ---- Cross-repo lineage ------------------------------------------------
    {
        "_key": "ickgq_cross_repo_lineage",
        "name": "GraphRAG: Cross-repo lineage — EVOLVED_FROM chain",
        "description": (
            "Trace the evolutionary lineage of a hardware concept across "
            "OR1200 → MOR1KX → MAROCCHINO using CROSS_REPO_EVOLVED_FROM edges."
        ),
        "queryText": """\
// Cross-repo evolutionary lineage starting from a golden entity
FOR v, e, p IN 1..5 ANY @start CROSS_REPO_EVOLVED_FROM
    OPTIONS {uniqueVertices: "global"}
    RETURN {
        name:       v.name,
        collection: SPLIT(v._id, "/")[0],
        depth:      LENGTH(p.edges),
        direction:  e._from == @start ? "evolved_to" : "evolved_from"
    }
""",
        "bindVariables": {"start": "OR1200_Golden_Entities/Instruction_Cache"},
    },

    # ---- RESOLVED_TO count summary -----------------------------------------
    {
        "_key": "ickgq_resolved_to_summary",
        "name": "GraphRAG: RESOLVED_TO summary — counts per repo + method",
        "description": "Dashboard query: shows total RESOLVED_TO edge counts per repo and match method.",
        "queryText": """\
// RESOLVED_TO summary — count by repo and match method
FOR edge IN RESOLVED_TO
    LET rtl = DOCUMENT(edge._from)
    COLLECT repo = rtl.repo, method = edge.match_method
    WITH COUNT INTO n
    SORT repo, method
    RETURN {repo, method, count: n}
""",
        "bindVariables": {},
    },

    # ---- Community map for a repo ------------------------------------------
    {
        "_key": "ickgq_community_map",
        "name": "GraphRAG: Community map — all Leiden communities for a repo",
        "description": (
            "Show the Leiden community structure for one repo's golden entities. "
            "Change @prefix to the repo collection name."
        ),
        "queryText": """\
// Community map: group golden entities by Leiden community ID
FOR doc IN @@coll
    FILTER doc.community != null
    COLLECT community_id = doc.community INTO members
    SORT community_id
    RETURN {
        community: community_id,
        size:      LENGTH(members),
        members:   members[*].doc.name
    }
""",
        "bindVariables": {"@coll": "OR1200_Golden_Entities"},
    },
]

# ---------------------------------------------------------------------------
# Canvas actions (installed into _system._canvasActions, linked via _viewpointActions)
# ---------------------------------------------------------------------------

CANVAS_ACTIONS = [
    {
        "_key": "ickga_show_ports_signals",
        "name": "Show Ports & Signals",
        "title": "Show Ports & Signals",
        "graphId": GRAPH_ID,
        "queryText": """\
FOR v IN 1..1 OUTBOUND @nodes[0] HAS_PORT, HAS_SIGNAL
    RETURN v
""",
        "bindVariables": {"nodes": []},
    },
    {
        "_key": "ickga_show_resolved_to",
        "name": "Show RESOLVED_TO targets",
        "title": "Show RESOLVED_TO targets",
        "graphId": GRAPH_ID,
        "queryText": """\
FOR v IN 1..1 OUTBOUND @nodes[0] RESOLVED_TO
    RETURN v
""",
        "bindVariables": {"nodes": []},
    },
    {
        "_key": "ickga_show_rtl_to_golden",
        "name": "Show RTL nodes that resolve here",
        "title": "Show RTL nodes that resolve here",
        "graphId": GRAPH_ID,
        "queryText": """\
FOR v IN 1..1 INBOUND @nodes[0] RESOLVED_TO
    RETURN v
""",
        "bindVariables": {"nodes": []},
    },
    {
        "_key": "ickga_show_cross_repo",
        "name": "Show Cross-Repo Neighbours",
        "title": "Show Cross-Repo Neighbours",
        "graphId": GRAPH_ID,
        "queryText": """\
FOR v IN 1..1 ANY @nodes[0] CROSS_REPO_SIMILAR_TO, CROSS_REPO_EVOLVED_FROM
    RETURN v
""",
        "bindVariables": {"nodes": []},
    },
    {
        "_key": "ickga_show_community",
        "name": "Show Community Peers",
        "title": "Show Community Peers",
        "graphId": GRAPH_ID,
        "queryText": """\
LET src = DOCUMENT(@nodes[0])
FOR doc IN @@coll
    FILTER doc.community == src.community AND doc._id != src._id
    LIMIT 15
    RETURN doc
""",
        "bindVariables": {"nodes": [], "@coll": "OR1200_Golden_Entities"},
    },
    {
        "_key": "ickga_show_depends_on",
        "name": "Show Module Dependencies",
        "title": "Show Module Dependencies",
        "graphId": GRAPH_ID,
        "queryText": """\
FOR v IN 1..2 OUTBOUND @nodes[0] DEPENDS_ON
    RETURN v
""",
        "bindVariables": {"nodes": []},
    },
]


# ---------------------------------------------------------------------------
# Installer
# ---------------------------------------------------------------------------

def upsert_by_key(col, doc):
    """Insert or update a document using _key as the idempotency handle."""
    key = doc.get("_key")
    if key and col.has(key):
        col.update({"_key": key, **doc})
        return "updated"
    col.insert(doc, overwrite=True)
    return "inserted"


def ensure_collection(db, name, edge=False):
    if not db.has_collection(name):
        try:
            db.create_collection(name, edge=edge)
        except Exception:
            pass
    return db.collection(name)


def install_saved_queries(sys_db, target_db):
    print("\n[1/3] Installing saved queries …")
    ensure_collection(sys_db, "_editor_saved_queries")
    col = sys_db.collection("_editor_saved_queries")
    for q in SAVED_QUERIES:
        action = upsert_by_key(col, {**q, "databaseName": target_db.name})
        print(f"  {action}: {q['name']}")
    print(f"  Total: {len(SAVED_QUERIES)} queries")


def install_canvas_actions(sys_db, target_db):
    print("\n[2/3] Installing canvas actions …")
    ensure_collection(sys_db, "_canvasActions")
    col = sys_db.collection("_canvasActions")
    action_ids = {}
    for a in CANVAS_ACTIONS:
        result = col.insert({**a}, overwrite=True)
        action_ids[a["_key"]] = result["_id"] if "_id" in result else f"_canvasActions/{a['_key']}"
        print(f"  upserted: {a['name']}")
    print(f"  Total: {len(CANVAS_ACTIONS)} actions")
    return action_ids


def link_actions_to_viewpoints(target_db, action_ids):
    print("\n[3/3] Linking canvas actions to viewpoints …")
    vp_col  = ensure_collection(target_db, "_viewpoints")
    vpa_col = ensure_collection(target_db, "_viewpointActions", edge=True)

    viewpoints = list(vp_col.find({"graphId": GRAPH_ID}))
    if not viewpoints:
        print(f"  WARNING: no viewpoints found for '{GRAPH_ID}'.")
        print("  Open the graph in the ArangoDB UI once, then rerun this script.")
        return

    linked = 0
    for vp in viewpoints:
        vp_id = vp["_id"]
        for action_key, action_id in action_ids.items():
            existing = list(vpa_col.find({"_from": vp_id, "_to": action_id}))
            if not existing:
                vpa_col.insert({"_from": vp_id, "_to": action_id})
                linked += 1

    print(f"  Linked {linked} new viewpoint→action edges across {len(viewpoints)} viewpoint(s).")


def main():
    print("=" * 60)
    print("IC Knowledge Graph — GraphRAG Query & Canvas Action Installer")
    print("=" * 60)

    try:
        target_db = get_db()
        sys_db = get_system_db()
        print(f"Target DB : {target_db.name}")
        print(f"Graph     : {GRAPH_ID}")
    except Exception as exc:
        print(f"\nERROR connecting to ArangoDB: {exc}")
        print("Configure your .env file and set PYTHONPATH=src.")
        sys.exit(1)

    if not target_db.has_graph(GRAPH_ID):
        print(f"\nWARNING: Graph '{GRAPH_ID}' not found in {target_db.name}.")
        print("Run scripts/temporal/create_temporal_graph.py first.")
        print("Continuing — saved queries can still be installed without the graph.")

    install_saved_queries(sys_db, target_db)
    action_ids = install_canvas_actions(sys_db, target_db)
    link_actions_to_viewpoints(target_db, action_ids)

    print("\n" + "=" * 60)
    print("Done.")
    print("  Saved queries  : ArangoDB UI → Queries panel → dropdown")
    print("  Canvas actions : Visualizer → right-click node → Canvas Actions")
    print("  (Open the graph in the Visualizer once if actions don't appear.)")
    print("=" * 60)


if __name__ == "__main__":
    main()
