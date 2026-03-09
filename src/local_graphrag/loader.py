"""
src/local_graphrag/loader.py — ArangoDB loader for local GraphRAG output.

Loads entities, relations, communities, and chunks into repo-prefixed collections
in ArangoDB. Compatible with existing consolidator.py and bridger_bulk.py.

Usage:
    from local_graphrag.loader import load_to_arangodb

    load_to_arangodb(
        entities=entities,
        relations=relations,
        communities=communities,
        chunks=chunks,
        prefix="MOR1KX_",
        db=db,
    )
"""

import os
import sys
from collections import defaultdict

_pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def _get_collection_names(prefix: str) -> dict[str, str]:
    """Return a mapping of logical → ArangoDB collection names for a given prefix."""
    return {
        "entities":    f"{prefix}Entities",
        "golden":      f"{prefix}Golden_Entities",
        "relations":   f"{prefix}Relations",
        "golden_rel":  f"{prefix}Golden_Relations",
        "communities": f"{prefix}Communities",
        "chunks":      f"{prefix}Chunks",
        "documents":   f"{prefix}Documents",
    }


def _ensure_collection(db, name: str, edge: bool = False) -> None:
    existing = {c["name"] for c in db.collections()}
    if name not in existing:
        db.create_collection(name, edge=edge)
        print(f"  [loader] Created {'edge' if edge else 'vertex'} collection: {name}")


def _bulk_upsert(db, col_name: str, records: list[dict],
                 batch_size: int = 500, edge: bool = False) -> int:
    """Upsert records in batches. Returns total inserted/updated."""
    if not records:
        return 0
    _ensure_collection(db, col_name, edge=edge)
    col = db.collection(col_name)
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        try:
            result = col.import_bulk(batch, on_duplicate="replace")
            total += result.get("created", 0) + result.get("updated", 0)
        except Exception as e:
            print(f"  [loader] Batch error in {col_name}: {e}")
            for rec in batch:
                try:
                    col.insert(rec, overwrite=True)
                    total += 1
                except Exception:
                    pass
    return total


def load_to_arangodb(
    entities:    list[dict],
    relations:   list[dict],
    communities: list[dict],
    chunks:      list[dict],
    prefix:      str,
    db,
    documents:   list[dict] = None,
    batch_size:  int = 500,
) -> dict[str, int]:
    """
    Load all local GraphRAG output into ArangoDB.

    Collections written:
        {prefix}Entities        — raw extracted entities
        {prefix}Relations       — raw relations (edge collection)
        {prefix}Communities     — Leiden community clusters
        {prefix}Chunks          — document chunks
        {prefix}Documents       — document metadata (if provided)

    NOTE: {prefix}Golden_Entities and {prefix}Golden_Relations are created
    by the existing consolidator.py — we do NOT write them here.

    Returns: dict of {collection_name: count_written}
    """
    cols = _get_collection_names(prefix)
    counts: dict[str, int] = {}

    print(f"\n[loader] Loading to ArangoDB (prefix={prefix!r})")

    # Entities (vertex)
    n = _bulk_upsert(db, cols["entities"], entities, batch_size=batch_size)
    counts[cols["entities"]] = n
    print(f"  {cols['entities']:40s}  {n:6d}")

    # Relations (edge) — ensure _from/_to are properly namespaced
    rel_qualified = []
    for r in relations:
        rq = dict(r)
        if "/" not in rq.get("_from", ""):
            rq["_from"] = f"{cols['entities']}/{rq['_from'].split('/')[-1]}"
        if "/" not in rq.get("_to", ""):
            rq["_to"] = f"{cols['entities']}/{rq['_to'].split('/')[-1]}"
        rel_qualified.append(rq)

    n = _bulk_upsert(db, cols["relations"], rel_qualified, batch_size=batch_size, edge=True)
    counts[cols["relations"]] = n
    print(f"  {cols['relations']:40s}  {n:6d}")

    # Communities (vertex)
    n = _bulk_upsert(db, cols["communities"], communities, batch_size=batch_size)
    counts[cols["communities"]] = n
    print(f"  {cols['communities']:40s}  {n:6d}")

    # Chunks (vertex)
    n = _bulk_upsert(db, cols["chunks"], chunks, batch_size=batch_size)
    counts[cols["chunks"]] = n
    print(f"  {cols['chunks']:40s}  {n:6d}")

    # Documents (optional)
    if documents:
        n = _bulk_upsert(db, cols["documents"], documents, batch_size=batch_size)
        counts[cols["documents"]] = n
        print(f"  {cols['documents']:40s}  {n:6d}")

    total = sum(counts.values())
    print(f"\n[loader] Done — {total} total records loaded across {len(counts)} collections.")
    return counts
