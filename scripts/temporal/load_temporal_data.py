"""
load_temporal_data.py — Load temporally-annotated RTL nodes and edges into ArangoDB.

Reads the JSONL files produced by etl_temporal_git.py and upserts them into
the ArangoDB ic-knowledge-graph database, creating temporal and epoch collections
as needed.

Usage:
    python scripts/temporal/load_temporal_data.py
    python scripts/temporal/load_temporal_data.py --nodes-file data/temporal/temporal_nodes.jsonl
    python scripts/temporal/load_temporal_data.py --dry-run
"""

import os
import sys
import json
import argparse
from collections import defaultdict

# Ensure src/ is on the path
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, SRC_DIR)

from arango import ArangoClient

from config import (
    ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD, ARANGO_DATABASE,
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_COMMIT,
    EDGE_MODIFIED,
)
from config_temporal import (
    TEMPORAL_NODES_FILE, TEMPORAL_EDGES_FILE,
    COL_DESIGN_EPOCH, COL_DESIGN_SITUATION,
    EDGE_BELONGS_TO_EPOCH, EDGE_EXEMPLIFIES,
    EDGE_CROSS_REPO_SIMILAR, EDGE_CROSS_REPO_EVOLVED,
)

# ---------------------------------------------------------------------------
# Collections to ensure exist
# ---------------------------------------------------------------------------

TEMPORAL_VERTEX_COLLECTIONS = [
    COL_MODULE, COL_COMMIT, COL_DESIGN_EPOCH, COL_DESIGN_SITUATION,
]

TEMPORAL_EDGE_COLLECTIONS = [
    EDGE_MODIFIED, EDGE_BELONGS_TO_EPOCH, EDGE_EXEMPLIFIES,
    EDGE_CROSS_REPO_SIMILAR, EDGE_CROSS_REPO_EVOLVED,
]

EDGE_TYPES = {
    EDGE_MODIFIED, EDGE_BELONGS_TO_EPOCH, EDGE_EXEMPLIFIES,
    EDGE_CROSS_REPO_SIMILAR, EDGE_CROSS_REPO_EVOLVED,
}

# ---------------------------------------------------------------------------
# Index specifications
# ---------------------------------------------------------------------------

# Vertex-centric persistent indexes (VCI) on edge collections.
# The pattern [_from, valid_from_ts] and [_to, valid_to_ts] lets ArangoDB
# prune edge traversals *before* loading the neighboring vertex,
# making temporal traversals O(log n) instead of full-collection scans.
VCI_EDGE_INDEXES = [
    # MODIFIED  (GitCommit → RTL_Module)
    {"col": EDGE_MODIFIED, "fields": ["_from", "valid_from_ts"],
     "name": "idx_modified_from_vci"},
    {"col": EDGE_MODIFIED, "fields": ["_to",   "valid_to_ts"],
     "name": "idx_modified_to_vci"},
    # BELONGS_TO_EPOCH  (RTL_Module → DesignEpoch)
    {"col": EDGE_BELONGS_TO_EPOCH, "fields": ["_from", "valid_from_ts"],
     "name": "idx_epoch_from_vci"},
    {"col": EDGE_BELONGS_TO_EPOCH, "fields": ["_to",   "valid_to_ts"],
     "name": "idx_epoch_to_vci"},
    # CROSS_REPO_SIMILAR_TO
    {"col": EDGE_CROSS_REPO_SIMILAR, "fields": ["_from", "valid_from_ts"],
     "name": "idx_similar_from_vci"},
    # CROSS_REPO_EVOLVED_FROM
    {"col": EDGE_CROSS_REPO_EVOLVED, "fields": ["_from", "valid_from_ts"],
     "name": "idx_evolved_from_vci"},
]

# MDI-prefixed indexes on vertex collections.
# These enable O(log n) interval range scans: FILTER valid_from_ts <= @t
# AND (valid_to_ts == null OR valid_to_ts > @t).
# 'prefixFields' keeps the index from being a full multi-dimensional scan
# by anchoring the leading field.
MDI_VERTEX_INDEXES = [
    {"col": COL_MODULE,          "fields": ["valid_from_ts", "valid_to_ts"],
     "name": "idx_rtl_module_mdi"},
    {"col": COL_COMMIT,          "fields": ["valid_from_ts", "valid_to_ts"],
     "name": "idx_gitcommit_mdi"},
    {"col": COL_DESIGN_SITUATION, "fields": ["valid_from_ts", "valid_to_ts"],
     "name": "idx_situation_mdi"},
]


def get_db():
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)


def ensure_collections(db, dry_run: bool = False) -> None:
    existing = {c["name"] for c in db.collections()}

    for col_name in TEMPORAL_VERTEX_COLLECTIONS:
        if col_name not in existing:
            if not dry_run:
                db.create_collection(col_name)
            print(f"  [create] vertex collection: {col_name}")

    for col_name in TEMPORAL_EDGE_COLLECTIONS:
        if col_name not in existing:
            if not dry_run:
                db.create_collection(col_name, edge=True)
            print(f"  [create] edge collection:   {col_name}")


def create_temporal_indexes(db, dry_run: bool = False) -> None:
    """
    Create vertex-centric persistent (VCI) indexes on edge collections
    and MDI-prefixed indexes on vertex collections.

    VCI pattern: [_from, valid_from_ts] and [_to, valid_to_ts]
    Allows ArangoDB traversal engine to filter edges by time interval
    BEFORE loading the neighboring vertex, eliminating cold-vertex reads
    for out-of-window versions.

    MDI pattern: [valid_from_ts, valid_to_ts] with prefixFields=[valid_from_ts]
    Supports O(log n) temporal range scans on vertex collections.
    """
    if dry_run:
        print("[indexes] DRY RUN — index creation skipped")
        return

    existing_cols = {c["name"] for c in db.collections()}

    print("\n[indexes] Creating vertex-centric persistent indexes (VCI) on edge collections …")
    for spec in VCI_EDGE_INDEXES:
        col_name = spec["col"]
        if col_name not in existing_cols:
            print(f"  [SKIP] {col_name} not found, skipping VCI index")
            continue
        col = db.collection(col_name)
        # Check if index already exists by name
        existing_idx_names = {idx.get("name") for idx in col.indexes()}
        if spec["name"] in existing_idx_names:
            print(f"  [EXISTS] {spec['name']}")
            continue
        try:
            col.add_index({
                "type":   "persistent",
                "fields": spec["fields"],
                "name":   spec["name"],
                "unique": False,
                "sparse": True,    # sparse=True skips docs where valid_from_ts is null
            })
            print(f"  [DONE] {spec['name']:45s}  on {col_name} fields={spec['fields']}")
        except Exception as e:
            print(f"  [ERROR] {spec['name']}: {e}")

    print("\n[indexes] Creating MDI-prefixed indexes on vertex collections …")
    for spec in MDI_VERTEX_INDEXES:
        col_name = spec["col"]
        if col_name not in existing_cols:
            print(f"  [SKIP] {col_name} not found, skipping MDI index")
            continue
        col = db.collection(col_name)
        existing_idx_names = {idx.get("name") for idx in col.indexes()}
        if spec["name"] in existing_idx_names:
            print(f"  [EXISTS] {spec['name']}")
            continue
        try:
            col.add_index({
                "type":            "mdi-prefixed",
                "fields":          spec["fields"],
                "name":            spec["name"],
                "fieldValueTypes": "double",
                "prefixFields":    [spec["fields"][0]],   # anchor on valid_from_ts
                "unique":          False,
                "sparse":          True,   # exclude docs where valid_from_ts|valid_to_ts is null
            })
            print(f"  [DONE] {spec['name']:45s}  on {col_name} fields={spec['fields']}")
        except Exception as e:
            print(f"  [ERROR] {spec['name']}: {e}")


def read_jsonl(path: str) -> list[dict]:
    records = []
    if not os.path.exists(path):
        print(f"[loader] File not found: {path}")
        return records
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"[loader] Warning: skipping malformed line: {e}")
    return records


def split_nodes_and_edges(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate vertex and edge records based on the 'type' field."""
    nodes = [r for r in records if r.get("type") not in EDGE_TYPES]
    edges = [r for r in records if r.get("type") in EDGE_TYPES]
    return nodes, edges


def get_collection_for_record(record: dict) -> str:
    """Map a record's type to its ArangoDB collection name."""
    type_map = {
        COL_MODULE:         COL_MODULE,
        COL_COMMIT:         COL_COMMIT,
        COL_DESIGN_EPOCH:   COL_DESIGN_EPOCH,
        COL_DESIGN_SITUATION: COL_DESIGN_SITUATION,
    }
    rec_type = record.get("type", "")
    return type_map.get(rec_type, COL_MODULE)  # default to RTL_Module


def upsert_records(db, records: list[dict], collection_name: str,
                   dry_run: bool = False, batch_size: int = 500) -> int:
    """Upsert records into a collection. Returns count of inserted/updated."""
    if not records:
        return 0

    col = db.collection(collection_name)
    inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        if dry_run:
            inserted += len(batch)
            continue
        try:
            result = col.import_bulk(batch, on_duplicate="replace")
            inserted += result.get("created", 0) + result.get("updated", 0)
        except Exception as e:
            print(f"  [ERROR] batch upsert to {collection_name}: {e}")
            # Try one-by-one fallback
            for rec in batch:
                try:
                    col.insert(rec, overwrite=True)
                    inserted += 1
                except Exception as e2:
                    print(f"    [SKIP] {rec.get('_key','?')}: {e2}")

    return inserted


def upsert_edges(db, edges: list[dict], dry_run: bool = False, batch_size: int = 500) -> dict:
    """Route edges into their correct edge collections and upsert."""
    counts = defaultdict(int)

    # Group by type
    by_type = defaultdict(list)
    for edge in edges:
        edge_type = edge.get("type", EDGE_MODIFIED)
        by_type[edge_type].append(edge)

    for edge_type, group in by_type.items():
        # Ensure _from / _to are in ArangoDB format (collection/key)
        formatted = []
        for e in group:
            formatted_edge = dict(e)
            frm = e.get("from") or e.get("_from", "")
            to  = e.get("to")  or e.get("_to", "")

            # Resolve from/to to full ArangoDB IDs
            formatted_edge["_from"] = _resolve_edge_endpoint(frm, edge_type, is_from=True)
            formatted_edge["_to"]   = _resolve_edge_endpoint(to,  edge_type, is_from=False)
            # Remove old keys
            formatted_edge.pop("from", None)
            formatted_edge.pop("to", None)
            formatted.append(formatted_edge)

        if not dry_run:
            if edge_type not in {c["name"] for c in db.collections()}:
                db.create_collection(edge_type, edge=True)

            col = db.collection(edge_type)
            for i in range(0, len(formatted), batch_size):
                batch = formatted[i:i + batch_size]
                try:
                    result = col.import_bulk(batch, on_duplicate="replace")
                    counts[edge_type] += result.get("created", 0) + result.get("updated", 0)
                except Exception as e:
                    print(f"  [ERROR] edge batch to {edge_type}: {e}")
                    for rec in batch:
                        try:
                            col.insert(rec, overwrite=True)
                            counts[edge_type] += 1
                        except Exception:
                            pass
        else:
            counts[edge_type] += len(formatted)

    return dict(counts)


def _resolve_edge_endpoint(ref: str, edge_type: str, is_from: bool) -> str:
    """
    Ensure an edge endpoint is in 'Collection/key' format.
    Uses edge_type to determine source/target collection if only a bare key is given.
    """
    if "/" in ref:
        return ref  # already qualified

    # Determine collection based on edge type and endpoint direction
    col_map_from = {
        EDGE_MODIFIED:        COL_COMMIT,
        EDGE_BELONGS_TO_EPOCH: COL_MODULE,
        EDGE_EXEMPLIFIES:     COL_DESIGN_SITUATION,
        EDGE_CROSS_REPO_SIMILAR: "OR1200_Golden_Entities",
        EDGE_CROSS_REPO_EVOLVED: "OR1200_Golden_Entities",
    }
    col_map_to = {
        EDGE_MODIFIED:        COL_MODULE,
        EDGE_BELONGS_TO_EPOCH: COL_DESIGN_EPOCH,
        EDGE_EXEMPLIFIES:     COL_COMMIT,
        EDGE_CROSS_REPO_SIMILAR: "OR1200_Golden_Entities",
        EDGE_CROSS_REPO_EVOLVED: "OR1200_Golden_Entities",
    }
    col = (col_map_from if is_from else col_map_to).get(edge_type, COL_MODULE)
    return f"{col}/{ref}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Load temporal data into ArangoDB")
    parser.add_argument("--nodes-file", default=TEMPORAL_NODES_FILE)
    parser.add_argument("--edges-file", default=TEMPORAL_EDGES_FILE)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing to ArangoDB")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n[loader] Temporal data loader — {mode}")
    print(f"  nodes → {args.nodes_file}")
    print(f"  edges → {args.edges_file}")
    print(f"  DB    → {ARANGO_DATABASE} @ {ARANGO_ENDPOINT}\n")

    # Connect
    if not args.dry_run:
        db = get_db()
        ensure_collections(db, dry_run=False)
    else:
        db = None
        print("[loader] DRY RUN: skipping DB connection\n")

    # Load all records
    print("[loader] Reading JSONL files …")
    all_records = read_jsonl(args.nodes_file)
    edge_records = read_jsonl(args.edges_file)

    print(f"  {len(all_records)} node records")
    print(f"  {len(edge_records)} edge records")

    # Split nodes by collection
    by_collection = defaultdict(list)
    for rec in all_records:
        col = get_collection_for_record(rec)
        by_collection[col].append(rec)

    # Upsert nodes
    total_nodes = 0
    for col_name, records in by_collection.items():
        if not args.dry_run:
            n = upsert_records(db, records, col_name,
                               dry_run=False, batch_size=args.batch_size)
        else:
            n = len(records)
        print(f"  [upsert] {col_name:30s} {n:6d} records")
        total_nodes += n

    # Upsert edges
    edge_counts = upsert_edges(db, edge_records, dry_run=args.dry_run,
                               batch_size=args.batch_size)
    total_edges = sum(edge_counts.values())
    for edge_type, count in edge_counts.items():
        print(f"  [upsert] {edge_type:30s} {count:6d} edges")

    print(f"\n[loader] Done. {total_nodes} nodes, {total_edges} edges loaded.")

    # Create indexes after data is loaded (skipped on dry run)
    if not args.dry_run:
        print("\n[loader] Creating temporal indexes …")
        create_temporal_indexes(db, dry_run=False)
    else:
        print("\n[loader] DRY RUN: index creation skipped.")


if __name__ == "__main__":
    main()
