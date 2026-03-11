"""
scripts/temporal/create_temporal_graph.py
Create (or recreate) the IC_Temporal_Knowledge_Graph named graph in ArangoDB.

Run from project root:
    PYTHONPATH=src python3 scripts/temporal/create_temporal_graph.py

Run anytime to rebuild the graph definition after schema changes.
Existing graph is deleted and recreated — edge/vertex data is untouched.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from arango import ArangoClient
from config_temporal import TEMPORAL_GRAPH_NAME, ARANGO_DATABASE

def create_graph(db):
    cols = {c["name"] for c in db.collections() if not c["name"].startswith("_")}

    golden_entity_cols = sorted(c for c in cols if c.endswith("_Golden_Entities"))
    entity_cols        = sorted(c for c in cols if c.endswith("_Entities"))
    community_cols     = sorted(c for c in cols if c.endswith("_Communities"))
    chunk_cols         = sorted(c for c in cols if c.endswith("_Chunks"))
    relation_cols      = sorted(c for c in cols if c.endswith("_Relations") and not c.endswith("_Golden_Relations"))
    golden_rel_cols    = sorted(c for c in cols if c.endswith("_Golden_Relations"))
    doc_cols           = sorted(c for c in cols if c.endswith("_Documents"))

    edge_definitions = [
        # ── Core temporal traversal ──────────────────────────────────────
        {
            "edge_collection": "MODIFIED",
            "from_vertex_collections": ["GitCommit"],
            "to_vertex_collections":   ["RTL_Module"],
        },
        {
            "edge_collection": "BELONGS_TO_EPOCH",
            "from_vertex_collections": ["RTL_Module"],
            "to_vertex_collections":   ["DesignEpoch"],
        },
        # ── Cross-repo bridges ───────────────────────────────────────────
        {
            "edge_collection": "CROSS_REPO_SIMILAR_TO",
            "from_vertex_collections": golden_entity_cols + ["RTL_Module"],
            "to_vertex_collections":   golden_entity_cols + ["RTL_Module"],
        },
        {
            "edge_collection": "CROSS_REPO_EVOLVED_FROM",
            "from_vertex_collections": golden_entity_cols + ["RTL_Module"],
            "to_vertex_collections":   golden_entity_cols + ["RTL_Module"],
        },
    ]

    # Per-repo GraphRAG Golden relation edges
    for rel_col in golden_rel_cols:
        ge_col = rel_col.replace("_Golden_Relations", "_Golden_Entities")
        if ge_col in cols:
            edge_definitions.append({
                "edge_collection": rel_col,
                "from_vertex_collections": [ge_col],
                "to_vertex_collections":   [ge_col],
            })

    # Per-repo raw relation edges
    for rel_col in relation_cols:
        prefix  = rel_col.replace("_Relations", "_")
        e_col   = prefix + "Entities"
        ch_col  = prefix + "Chunks"
        comm_col= prefix + "Communities"
        froms   = [c for c in [e_col, ch_col, comm_col] if c in cols]
        if froms:
            edge_definitions.append({
                "edge_collection": rel_col,
                "from_vertex_collections": froms,
                "to_vertex_collections":   froms,
            })

    # Orphan collections (vertex-only, no direct edge from this graph)
    all_vertex_cols = (
        ["GitCommit", "RTL_Module", "DesignEpoch", "DesignSituation", "Author"]
        + golden_entity_cols + entity_cols + community_cols + chunk_cols + doc_cols
    )
    linked = {
        v
        for ed in edge_definitions
        for v in ed["from_vertex_collections"] + ed["to_vertex_collections"]
    }
    orphans = [c for c in all_vertex_cols if c in cols and c not in linked]

    # Delete and recreate
    if db.has_graph(TEMPORAL_GRAPH_NAME):
        db.delete_graph(TEMPORAL_GRAPH_NAME)
        print(f"[graph] Deleted existing graph: {TEMPORAL_GRAPH_NAME}")

    graph = db.create_graph(
        TEMPORAL_GRAPH_NAME,
        edge_definitions=edge_definitions,
        orphan_collections=orphans,
    )
    print(f"[graph] Created: {TEMPORAL_GRAPH_NAME}")
    print(f"  Edge definitions ({len(edge_definitions)}):")
    for ed in edge_definitions:
        froms = ", ".join(ed["from_vertex_collections"])
        tos   = ", ".join(ed["to_vertex_collections"])
        print(f"    {ed['edge_collection']:35s}  [{froms}] → [{tos}]")
    if orphans:
        print(f"  Orphan vertex collections: {orphans}")
    return graph


if __name__ == "__main__":
    client = ArangoClient(hosts=os.environ["ARANGO_ENDPOINT"])
    db = client.db(
        ARANGO_DATABASE,
        username=os.environ["ARANGO_USERNAME"],
        password=os.environ["ARANGO_PASSWORD"],
    )
    print(f"[graph] Connected to: {ARANGO_DATABASE} @ {os.environ['ARANGO_ENDPOINT']}")
    create_graph(db)
