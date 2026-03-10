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
import hashlib
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


def build_golden_entities(entities: list[dict], prefix: str) -> list[dict]:
    """
    Deduplicate raw extracted entities into Golden Entities.

    Two entities are considered the same if their normalized name (lowercased,
    stripped, spaces → underscores) hashes to the same MD5 prefix. When
    duplicates are found the first occurrence keeps its description; all
    occurrences contribute their aliases and source chunks.

    Returns a new list of golden entity dicts ready for {prefix}Golden_Entities.
    The ``_key`` of each golden entity is stable: ``{prefix}g_{md5(normalized_name)[:12]}``
    — matching what the existing consolidator.py would produce, so the two paths
    are interchangeable.
    """
    golden: dict[str, dict] = {}  # golden_key → merged entity

    for ent in entities:
        name = ent.get("name", "").strip()
        if not name:
            continue
        norm = name.lower().replace(" ", "_")
        golden_key = f"{prefix}g_{hashlib.md5(norm.encode()).hexdigest()[:12]}"

        if golden_key not in golden:
            golden[golden_key] = {
                "_key":           golden_key,
                "name":           name,
                "type":           ent.get("type", ""),
                "description":    ent.get("description", ""),
                "aliases":        list(ent.get("aliases", [])),
                "source_chunks":  [],
                "embedding":      ent.get("embedding"),  # take from first occurrence
                "valid_from_epoch": ent.get("valid_from_epoch"),
                "doc_version":    ent.get("doc_version"),
            }
        else:
            g = golden[golden_key]
            # Accumulate aliases
            g["aliases"] = list(set(g["aliases"]) | set(ent.get("aliases", [])))
            # Prefer a richer description
            if not g["description"] and ent.get("description"):
                g["description"] = ent["description"]
            # Take any embedding we find
            if g["embedding"] is None and ent.get("embedding") is not None:
                g["embedding"] = ent["embedding"]

        source_chunk = ent.get("source_chunk")
        if source_chunk and source_chunk not in golden[golden_key]["source_chunks"]:
            golden[golden_key]["source_chunks"].append(source_chunk)

    return list(golden.values())


def build_golden_relations(
    relations: list[dict],
    golden_entities: list[dict],
    prefix: str,
    entities_col: str,
    golden_col: str,
) -> list[dict]:
    """
    Build Golden Relations by re-mapping raw relation endpoints to their
    corresponding Golden Entity keys.

    A golden relation is created for each unique (golden_from, relation_type, golden_to)
    triple. Duplicate evidence is accumulated in ``evidence_count``.
    """
    # Build map: raw entity _key → golden entity _key
    # We derive golden key from entity name the same way build_golden_entities() does.
    raw_to_golden: dict[str, str] = {}
    for ent in golden_entities:
        # Reverse: the raw entity that produced this golden entity has a raw _key
        # that we can't directly recover, but we can rebuild the golden_key from
        # the name stored on the golden entity.
        name = ent.get("name", "").strip()
        norm = name.lower().replace(" ", "_")
        golden_key = f"{prefix}g_{hashlib.md5(norm.encode()).hexdigest()[:12]}"
        raw_to_golden[golden_key] = golden_key  # self-referencing in golden space

    # Also build from raw entities — we need to walk the raw list
    # (handled externally; here we translate endpoint collection/key refs)
    seen: dict[str, dict] = {}

    for rel in relations:
        raw_from = rel.get("_from", "").split("/")[-1]   # bare key
        raw_to   = rel.get("_to",   "").split("/")[-1]
        rel_type = rel.get("type", "RELATED_TO")

        # Keys from build_golden_entities use prefix+g+md5 — we can't remap directly
        # without the original name.  Use a simpler heuristic: strip the prefix
        # from the raw entity key to get the md5 portion, then try to build the
        # golden key by re-prefixing with "g_".
        # raw entity key format: {prefix}{md5[:12]}  → strip prefix → md5[:12]
        # golden key format:     {prefix}g_{md5[:12]}
        def _raw_to_golden_key(raw_key: str) -> str:
            bare = raw_key.removeprefix(prefix)   # e.g. "a1b2c3d4e5f6"
            return f"{prefix}g_{bare}"

        g_from = _raw_to_golden_key(raw_from)
        g_to   = _raw_to_golden_key(raw_to)

        triple_key = hashlib.md5(f"{g_from}:{rel_type}:{g_to}".encode()).hexdigest()[:16]

        if triple_key not in seen:
            seen[triple_key] = {
                "_key":           triple_key,
                "_from":          f"{golden_col}/{g_from.split('/')[-1]}",
                "_to":            f"{golden_col}/{g_to.split('/')[-1]}",
                "type":           rel_type,
                "context":        rel.get("context", ""),
                "evidence_count": 1,
                "source_chunks":  [rel["source_chunk"]] if rel.get("source_chunk") else [],
            }
        else:
            seen[triple_key]["evidence_count"] += 1
            sc = rel.get("source_chunk")
            if sc and sc not in seen[triple_key]["source_chunks"]:
                seen[triple_key]["source_chunks"].append(sc)

    return list(seen.values())


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
        {prefix}Entities        — raw extracted entities (with embeddings)
        {prefix}Relations       — raw relations (edge collection)
        {prefix}Golden_Entities — deduplicated canonical entities
        {prefix}Golden_Relations— deduplicated canonical relations (edge collection)
        {prefix}Communities     — Leiden community clusters
        {prefix}Chunks          — document chunks
        {prefix}Documents       — document metadata (if provided)

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

    # Golden entity deduplication
    print(f"  [loader] Deduplicating → {cols['golden']} …")
    golden_entities = build_golden_entities(entities, prefix)
    n = _bulk_upsert(db, cols["golden"], golden_entities, batch_size=batch_size)
    counts[cols["golden"]] = n
    print(f"  {cols['golden']:40s}  {n:6d}  (from {len(entities)} raw)")

    # Golden relations
    golden_relations = build_golden_relations(
        relations, golden_entities, prefix,
        entities_col=cols["entities"],
        golden_col=cols["golden"],
    )
    n = _bulk_upsert(db, cols["golden_rel"], golden_relations, batch_size=batch_size, edge=True)
    counts[cols["golden_rel"]] = n
    print(f"  {cols['golden_rel']:40s}  {n:6d}  (from {len(relations)} raw)")

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
