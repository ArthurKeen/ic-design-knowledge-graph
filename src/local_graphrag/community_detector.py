"""
src/local_graphrag/community_detector.py — Local Leiden community detection.

Runs Leiden community detection on the entity-relation graph using python-igraph.
Output matches the existing OR1200_Communities schema so the existing pipeline works.

Fallback: if python-igraph is not installed, uses a simple greedy label propagation
implemented in pure Python.

Usage:
    from local_graphrag.community_detector import detect_communities

    communities = detect_communities(entities, relations, prefix="OR1200_")
"""

import hashlib
from collections import defaultdict


def _most_common_type(entities: list[dict], member_keys: list[str]) -> str:
    """Return the most common entity type in a community."""
    key_set = set(member_keys)
    types = [e.get("type", "UNKNOWN") for e in entities if e["_key"] in key_set]
    if not types:
        return "UNKNOWN"
    return max(set(types), key=types.count)


def _most_common_name(entities: list[dict], member_keys: list[str]) -> str:
    """Return the name of the first entity in the community as the label."""
    key_set = set(member_keys)
    for e in entities:
        if e["_key"] in key_set:
            return e.get("name", e["_key"])
    return member_keys[0] if member_keys else "Community"


# ---------------------------------------------------------------------------
# Leiden via python-igraph (preferred)
# ---------------------------------------------------------------------------

def _leiden_communities(entities: list[dict], relations: list[dict]) -> list[list[str]]:
    """
    Run the Leiden algorithm using python-igraph.
    Returns list of communities, each a list of entity _key strings.
    """
    import igraph as ig

    # Build id → index map
    keys = [e["_key"] for e in entities]
    idx = {k: i for i, k in enumerate(keys)}

    # Build edges from _from / _to IDs
    edges = []
    for r in relations:
        frm_raw = r.get("_from", "")
        to_raw  = r.get("_to", "")
        # Strip collection prefix: "OR1200_Entities/abc" → "abc"
        frm_key = frm_raw.split("/")[-1] if "/" in frm_raw else frm_raw
        to_key  = to_raw.split("/")[-1]  if "/" in to_raw  else to_raw
        if frm_key in idx and to_key in idx:
            edges.append((idx[frm_key], idx[to_key]))

    g = ig.Graph(n=len(keys), edges=edges, directed=False)
    # Leiden objective: modularity
    membership = g.community_leiden(
        objective_function="modularity",
        n_iterations=10,
    ).membership

    # Group keys by community id
    clusters: dict[int, list[str]] = defaultdict(list)
    for key, comm_id in zip(keys, membership):
        clusters[comm_id].append(key)

    return list(clusters.values())


# ---------------------------------------------------------------------------
# Fallback: label propagation (no external deps)
# ---------------------------------------------------------------------------

def _label_propagation(entities: list[dict], relations: list[dict]) -> list[list[str]]:
    """
    Simple synchronous label propagation as a fallback when igraph is absent.
    Not as accurate as Leiden but dependency-free.
    """
    keys = [e["_key"] for e in entities]
    labels = {k: k for k in keys}    # initially each node in its own community

    # Build adjacency
    adj: dict[str, set[str]] = defaultdict(set)
    for r in relations:
        frm = r.get("_from", "").split("/")[-1]
        to  = r.get("_to",  "").split("/")[-1]
        if frm and to:
            adj[frm].add(to)
            adj[to].add(frm)

    # Propagate for 20 iterations
    for _ in range(20):
        changed = False
        for key in keys:
            neighbors = adj.get(key, set())
            if not neighbors:
                continue
            neighbor_labels = [labels[n] for n in neighbors if n in labels]
            if not neighbor_labels:
                continue
            best = max(set(neighbor_labels), key=neighbor_labels.count)
            if labels[key] != best:
                labels[key] = best
                changed = True
        if not changed:
            break

    # Group by label
    clusters: dict[str, list[str]] = defaultdict(list)
    for key, lbl in labels.items():
        clusters[lbl].append(key)

    return list(clusters.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_communities(
    entities: list[dict],
    relations: list[dict],
    prefix: str = "",
) -> list[dict]:
    """
    Detect communities in the entity-relation graph.

    Tries python-igraph Leiden first; falls back to label propagation.

    Args:
        entities:  List of entity dicts (each with _key).
        relations: List of relation dicts (each with _from, _to).
        prefix:    Repo prefix for _key generation (e.g. "OR1200_").

    Returns:
        List of community dicts compatible with OR1200_Communities schema:
        {_key, community_id, member_entities, label, dominant_type, size}
    """
    if not entities:
        return []

    print(f"[community] Running community detection on {len(entities)} entities …")

    # Try Leiden first
    try:
        clusters = _leiden_communities(entities, relations)
        method = "leiden"
    except ImportError:
        print("[community] python-igraph not found, using label propagation fallback")
        clusters = _label_propagation(entities, relations)
        method = "label_propagation"

    communities = []
    for i, member_keys in enumerate(sorted(clusters, key=len, reverse=True)):
        comm_key = f"{prefix}comm_{hashlib.md5(str(sorted(member_keys)).encode()).hexdigest()[:12]}"
        communities.append({
            "_key":           comm_key,
            "community_id":   i,
            "member_entities": member_keys,
            "label":          _most_common_name(entities, member_keys),
            "dominant_type":  _most_common_type(entities, member_keys),
            "size":           len(member_keys),
            "detection_method": method,
        })

    print(f"[community] {len(communities)} communities detected (method: {method})")
    return communities
