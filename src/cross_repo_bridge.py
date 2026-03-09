"""
src/cross_repo_bridge.py — Build CROSS_REPO_SIMILAR_TO and CROSS_REPO_EVOLVED_FROM edges.

Compares Golden Entities between repos using:
  1. Embedding cosine similarity (primary, if embeddings exist)
  2. Port-signature structural matching (for RTL_Module nodes)
  3. Rule-based lineage (for known architectural successor chains)

Usage:
    python src/cross_repo_bridge.py --source OR1200_ --target MOR1KX_
    python src/cross_repo_bridge.py --all  # process all registered repo pairs
"""

import os
import sys
import hashlib
import argparse
from itertools import combinations
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from arango import ArangoClient
from config import ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD
from config_temporal import (
    ARANGO_DATABASE,
    CROSS_REPO_MIN_SIMILARITY,
    EDGE_CROSS_REPO_SIMILAR, EDGE_CROSS_REPO_EVOLVED,
    LINEAGE_RULES, REPO_REGISTRY,
)


def get_db():
    client = ArangoClient(hosts=ARANGO_ENDPOINT)
    return client.db(ARANGO_DATABASE, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)


def _ensure_edge_col(db, name: str) -> None:
    existing = {c["name"] for c in db.collections()}
    if name not in existing:
        db.create_collection(name, edge=True)


# ---------------------------------------------------------------------------
# Embedding similarity bridge
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(y * y for y in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def build_embedding_bridges(
    db,
    source_prefix: str,
    target_prefix: str,
    min_score: float = None,
) -> list[dict]:
    """
    Compare Golden Entities from two repos by embedding cosine similarity.
    Returns list of CROSS_REPO_SIMILAR_TO edge dicts.
    """
    min_score = min_score or CROSS_REPO_MIN_SIMILARITY
    src_col   = f"{source_prefix}Golden_Entities"
    tgt_col   = f"{target_prefix}Golden_Entities"

    # Fetch entities from both collections
    existing_cols = {c["name"] for c in db.collections()}
    if src_col not in existing_cols or tgt_col not in existing_cols:
        print(f"[bridge] Skipping embedding bridge: collection(s) not found "
              f"({src_col}, {tgt_col})")
        return []

    print(f"[bridge] Embedding bridge: {src_col} ↔ {tgt_col}  (min_score={min_score})")

    src_entities = list(db.aql.execute(
        f"FOR e IN `{src_col}` FILTER e.embedding != null RETURN e"
    ))
    tgt_entities = list(db.aql.execute(
        f"FOR e IN `{tgt_col}` FILTER e.embedding != null RETURN e"
    ))

    if not src_entities or not tgt_entities:
        print(f"[bridge] No embedded entities found — run embedding step first.")
        return []

    edges = []
    for src in src_entities:
        for tgt in tgt_entities:
            score = _cosine(src.get("embedding", []), tgt.get("embedding", []))
            if score >= min_score:
                edge_key = hashlib.md5(
                    f"{src['_id']}:{tgt['_id']}:similar".encode()
                ).hexdigest()[:16]
                edges.append({
                    "_key":              edge_key,
                    "_from":             src["_id"],
                    "_to":               tgt["_id"],
                    "similarity_score":  round(score, 4),
                    "similarity_type":   "embedding",
                    "source_repo":       source_prefix,
                    "target_repo":       target_prefix,
                    "created_by":        "cross_repo_bridge",
                })

    print(f"[bridge] {len(edges)} embedding bridges found (≥{min_score})")
    return edges


# ---------------------------------------------------------------------------
# Structural (port-signature) similarity bridge
# ---------------------------------------------------------------------------

def _port_signature_similarity(ports_a: list[str], ports_b: list[str]) -> float:
    """Jaccard similarity on lowercased port name sets with size penalty."""
    if not ports_a or not ports_b:
        return 0.0
    sa = {p.lower() for p in ports_a}
    sb = {p.lower() for p in ports_b}
    jaccard = len(sa & sb) / len(sa | sb)
    size_diff = abs(len(sa) - len(sb)) / max(len(sa), len(sb))
    return round(0.6 * jaccard + 0.4 * (1.0 - size_diff), 4)


def build_structural_bridges(
    db,
    source_prefix: str,
    target_prefix: str,
    min_score: float = None,
) -> list[dict]:
    """
    Compare RTL_Module nodes between repos by port-signature Jaccard similarity.
    Queries the existing RTL_Module collection filtered by repo prefix.
    """
    min_score = min_score or CROSS_REPO_MIN_SIMILARITY

    # Derive repo name from prefix (e.g. OR1200_ → or1200)
    src_repo = source_prefix.rstrip("_").lower()
    tgt_repo = target_prefix.rstrip("_").lower()

    print(f"[bridge] Structural bridge: {src_repo} ↔ {tgt_repo}  (min_score={min_score})")

    # Fetch RTL_Module nodes with their ports for each repo
    src_modules = list(db.aql.execute(
        "FOR m IN RTL_Module FILTER CONTAINS(m.repo, @r) "
        "LET ports = (FOR e IN HAS_PORT FILTER e._from == m._id "
        "             LET p = DOCUMENT(e._to) RETURN p.label) "
        "RETURN {id: m._id, label: m.label, ports: ports}",
        bind_vars={"r": src_repo}
    ))
    tgt_modules = list(db.aql.execute(
        "FOR m IN RTL_Module FILTER CONTAINS(m.repo, @r) "
        "LET ports = (FOR e IN HAS_PORT FILTER e._from == m._id "
        "             LET p = DOCUMENT(e._to) RETURN p.label) "
        "RETURN {id: m._id, label: m.label, ports: ports}",
        bind_vars={"r": tgt_repo}
    ))

    if not src_modules or not tgt_modules:
        print(f"[bridge] No RTL_Module nodes found with repo filter.")
        return []

    edges = []
    for src in src_modules:
        for tgt in tgt_modules:
            score = _port_signature_similarity(src["ports"], tgt["ports"])
            if score >= min_score:
                edge_key = hashlib.md5(
                    f"{src['id']}:{tgt['id']}:structural".encode()
                ).hexdigest()[:16]
                edges.append({
                    "_key":                    edge_key,
                    "_from":                   src["id"],
                    "_to":                     tgt["id"],
                    "similarity_score":        score,
                    "similarity_type":         "structural",
                    "port_signature_overlap":  score,
                    "source_repo":             source_prefix,
                    "target_repo":             target_prefix,
                    "created_by":              "cross_repo_bridge",
                })

    print(f"[bridge] {len(edges)} structural bridges found (≥{min_score})")
    return edges


# ---------------------------------------------------------------------------
# Lineage rules (rule-based CROSS_REPO_EVOLVED_FROM edges)
# ---------------------------------------------------------------------------

def build_lineage_bridges(db) -> list[dict]:
    """
    Create CROSS_REPO_EVOLVED_FROM edges based on the LINEAGE_RULES config.
    Uses suffix matching (e.g. or1200_cpu → mor1kx_cpu) or embedding similarity.
    """
    edges = []
    existing_cols = {c["name"] for c in db.collections()}

    for rule in LINEAGE_RULES:
        from_repo = rule["from_repo"]
        to_repo   = rule["to_repo"]
        match_by  = rule.get("match_by", "suffix_after_prefix")
        confidence = rule.get("confidence", 0.85)
        lineage   = rule.get("lineage", "related")

        # Derive collection prefixes from repo names
        from_prefix = from_repo.split("/")[-1].upper().replace("-", "") + "_"
        to_prefix   = to_repo.split("/")[-1].upper().replace("-", "") + "_"

        from_col = f"{from_prefix}Golden_Entities"
        to_col   = f"{to_prefix}Golden_Entities"

        if from_col not in existing_cols or to_col not in existing_cols:
            print(f"[bridge] Skipping lineage rule {from_repo}→{to_repo}: collections not found")
            continue

        print(f"[bridge] Lineage rule: {from_repo} evolved_from {to_repo}  ({match_by})")

        if match_by == "suffix_after_prefix":
            # Match entities whose names share the same suffix after their repo prefix
            from_entities = list(db.aql.execute(f"FOR e IN `{from_col}` RETURN e"))
            to_map = {}
            for e in db.aql.execute(f"FOR e IN `{to_col}` RETURN e"):
                to_map[e.get("name", "").lower()] = e

            for fe in from_entities:
                fe_name = fe.get("name", "").lower()
                if fe_name in to_map:
                    te = to_map[fe_name]
                    edge_key = hashlib.md5(
                        f"{fe['_id']}:{te['_id']}:evolved".encode()
                    ).hexdigest()[:16]
                    edges.append({
                        "_key":       edge_key,
                        "_from":      fe["_id"],    # from_repo entity
                        "_to":        te["_id"],    # to_repo (ancestor) entity
                        "lineage":    lineage,
                        "confidence": confidence,
                        "rule":       f"{from_repo} → {to_repo}",
                    })

    print(f"[bridge] {len(edges)} lineage bridges created")
    return edges


# ---------------------------------------------------------------------------
# Write to ArangoDB
# ---------------------------------------------------------------------------

def write_bridges(db, edges: list[dict], collection: str) -> int:
    """Bulk upsert bridge edges. Returns count written."""
    if not edges:
        return 0
    _ensure_edge_col(db, collection)
    col = db.collection(collection)
    written = 0
    batch_size = 500
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i + batch_size]
        try:
            result = col.import_bulk(batch, on_duplicate="replace")
            written += result.get("created", 0) + result.get("updated", 0)
        except Exception as e:
            print(f"[bridge] Batch write error: {e}")
    print(f"[bridge] Wrote {written} edges to {collection}")
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cross-repo semantic bridge builder")
    parser.add_argument("--source",       help="Source prefix (e.g. OR1200_)")
    parser.add_argument("--target",       help="Target prefix (e.g. MOR1KX_)")
    parser.add_argument("--all",          action="store_true",
                        help="Build bridges for all registered repo pairs")
    parser.add_argument("--min-score",    type=float, default=None)
    parser.add_argument("--skip-embedding",  action="store_true")
    parser.add_argument("--skip-structural", action="store_true")
    parser.add_argument("--skip-lineage",    action="store_true")
    args = parser.parse_args()

    db = get_db()

    if args.all:
        registered = REPO_REGISTRY
        pairs = list(combinations(registered, 2))
    elif args.source and args.target:
        # Build a fake pair from prefix strings
        pairs = [({"prefix": args.source, "name": args.source},
                  {"prefix": args.target, "name": args.target})]
    else:
        parser.print_help()
        return

    total_similar = 0
    total_evolved = 0

    for repo_a, repo_b in pairs:
        pa = repo_a["prefix"]
        pb = repo_b["prefix"]
        print(f"\n--- Bridge: {pa} ↔ {pb} ---")

        all_similar = []
        if not args.skip_embedding:
            all_similar += build_embedding_bridges(db, pa, pb, args.min_score)
        if not args.skip_structural:
            all_similar += build_structural_bridges(db, pa, pb, args.min_score)

        total_similar += write_bridges(db, all_similar, EDGE_CROSS_REPO_SIMILAR)

    if not args.skip_lineage:
        total_evolved += write_bridges(db, build_lineage_bridges(db), EDGE_CROSS_REPO_EVOLVED)

    print(f"\n[bridge] Total: {total_similar} CROSS_REPO_SIMILAR_TO, "
          f"{total_evolved} CROSS_REPO_EVOLVED_FROM edges written.")


if __name__ == "__main__":
    main()
