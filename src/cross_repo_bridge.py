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
# Structural (label-name) similarity bridge
# ---------------------------------------------------------------------------

def _label_suffix(label: str) -> str:
    """
    Strip common repo-specific prefixes from module names to get the functional suffix.
    e.g. 'or1200_cpu' → 'cpu',  'mor1kx_cpu' → 'cpu',  'ibex_core' → 'core'
    Splits on first underscore only (or returns full label if no underscore).
    """
    parts = label.lower().split("_", 1)
    return parts[1] if len(parts) > 1 else parts[0]


def _label_similarity(label_a: str, label_b: str) -> float:
    """
    Name-based similarity between two RTL module labels.
    - Exact suffix match after stripping repo prefix → 1.0
    - Token Jaccard on underscore-split words → partial score
    """
    sa, sb = _label_suffix(label_a), _label_suffix(label_b)
    if sa == sb:
        return 1.0
    # Token Jaccard on full label
    ta = set(label_a.lower().split("_"))
    tb = set(label_b.lower().split("_"))
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    return round(jaccard, 4)


def build_structural_bridges(
    db,
    source_prefix: str,
    target_prefix: str,
    min_score: float = None,
) -> list[dict]:
    """
    Compare RTL_Module nodes between repos by label-name similarity.

    Uses label suffix matching and token Jaccard on module names.  This is
    the best structural signal available from the temporal ETL (HAS_PORT is
    not populated by the git-replay pipeline).  A future enhancement can
    re-add port-level comparison once a Verilog port extractor is added.
    """
    min_score = min_score or CROSS_REPO_MIN_SIMILARITY

    src_repo = source_prefix.rstrip("_").lower()
    tgt_repo = target_prefix.rstrip("_").lower()

    print(f"[bridge] Structural bridge (label-name): {src_repo} ↔ {tgt_repo}  (min_score={min_score})")

    # Fetch the most-recent snapshot of each module (open-ended validity)
    # Fetch open-ended modules for both repos.
    # Note: combining CONTAINS() with the MDI index filter triggers an ArangoDB
    # AMP cluster planner bug (ERR 4). Workaround: fetch all open-ended modules
    # then filter by repo in Python.
    all_open = list(db.aql.execute(
        "FOR m IN RTL_Module FILTER m.valid_to_ts > 9000000000 "
        "RETURN {id: m._id, label: m.label, file_hash: m.file_hash, repo: m.repo}"
    ))
    src_modules = [m for m in all_open if src_repo in (m.get("repo") or "").lower()]
    tgt_modules = [m for m in all_open if tgt_repo in (m.get("repo") or "").lower()]

    if not src_modules or not tgt_modules:
        print(f"[bridge] No RTL_Module nodes found with repo filter.")
        return []

    print(f"[bridge]   {len(src_modules)} {src_repo} modules × {len(tgt_modules)} {tgt_repo} modules")

    edges = []
    for src in src_modules:
        for tgt in tgt_modules:
            # Exact file hash match → definite copy/port
            if src["file_hash"] and src["file_hash"] == tgt["file_hash"]:
                score = 1.0
            else:
                score = _label_similarity(src["label"], tgt["label"])

            if score >= min_score:
                edge_key = hashlib.md5(
                    f"{src['id']}:{tgt['id']}:structural".encode()
                ).hexdigest()[:16]
                edges.append({
                    "_key":             edge_key,
                    "_from":            src["id"],
                    "_to":              tgt["id"],
                    "similarity_score": score,
                    "similarity_type":  "structural_label",
                    "source_repo":      source_prefix,
                    "target_repo":      target_prefix,
                    "created_by":       "cross_repo_bridge",
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
