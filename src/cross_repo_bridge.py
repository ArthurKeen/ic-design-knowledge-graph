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
import argparse
from itertools import combinations
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_temporal import (
    ARANGO_DATABASE,
    CROSS_REPO_BRIDGE_BATCH_SIZE,
    CROSS_REPO_MIN_SIMILARITY,
    EDGE_CROSS_REPO_SIMILAR, EDGE_CROSS_REPO_EVOLVED,
    LINEAGE_RULES, REPO_REGISTRY,
    OPEN_VALIDITY_TS,
)
from db_utils import get_temporal_db, ensure_collection
from utils import cosine_similarity, get_edge_key


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
        "FOR e IN @@col FILTER e.embedding != null RETURN e",
        bind_vars={"@col": src_col}
    ))
    tgt_entities = list(db.aql.execute(
        "FOR e IN @@col FILTER e.embedding != null RETURN e",
        bind_vars={"@col": tgt_col}
    ))

    if not src_entities or not tgt_entities:
        print(f"[bridge] No embedded entities found — run embedding step first.")
        return []

    edges = []
    for src in src_entities:
        for tgt in tgt_entities:
            score = cosine_similarity(src.get("embedding", []), tgt.get("embedding", []))
            if score >= min_score:
                edge_key = get_edge_key(src["_id"], tgt["_id"], "similar", truncate=16)
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


def _port_signature_similarity(ports_a: list[str], ports_b: list[str]) -> float:
    """
    Jaccard similarity on normalised port-name sets, weighted with a size-match bonus.

    Score = 0.6 * jaccard + 0.4 * (1 - size_diff_ratio)

    This gives > 0.9 for identical sets and < 0.5 for completely disjoint sets
    of very different cardinality (e.g. 1 vs 8 ports).
    """
    if not ports_a or not ports_b:
        return 0.0
    a = {p.lower() for p in ports_a}
    b = {p.lower() for p in ports_b}
    jaccard = len(a & b) / len(a | b)
    size_diff = abs(len(a) - len(b)) / max(len(a), len(b))
    return round(0.6 * jaccard + 0.4 * (1.0 - size_diff), 4)


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
        "FOR m IN RTL_Module FILTER m.valid_to_ts >= @open_validity "
        "RETURN {id: m._id, label: m.label, file_hash: m.file_hash, repo: m.repo}",
        bind_vars={"open_validity": OPEN_VALIDITY_TS}
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
                edge_key = get_edge_key(src["id"], tgt["id"], "structural", truncate=16)
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
            from_entities = list(db.aql.execute("FOR e IN @@col RETURN e", bind_vars={"@col": from_col}))
            to_map = {}
            for e in db.aql.execute("FOR e IN @@col RETURN e", bind_vars={"@col": to_col}):
                to_map[e.get("name", "").lower()] = e

            for fe in from_entities:
                fe_name = fe.get("name", "").lower()
                if fe_name in to_map:
                    te = to_map[fe_name]
                    edge_key = get_edge_key(fe["_id"], te["_id"], "evolved", truncate=16)
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
    ensure_collection(db, collection, edge=True)
    col = db.collection(collection)
    written = 0
    for i in range(0, len(edges), CROSS_REPO_BRIDGE_BATCH_SIZE):
        batch = edges[i:i + CROSS_REPO_BRIDGE_BATCH_SIZE]
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

    db = get_temporal_db()

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
