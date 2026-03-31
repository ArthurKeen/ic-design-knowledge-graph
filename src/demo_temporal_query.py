"""
src/demo_temporal_query.py — Demonstration of temporal knowledge graph queries.

Runs 5 canonical query types against the ic-knowledge-graph-temporal database:

  1. state-as-of-commit  — RTL state at a specific point in OR1200 history
  2. epoch-evolution     — What changed between two OR1200 epochs
  3. cross-repo-analog   — Find the structural analog of a module in another repo
  4. deja-vu-match       — Find historically similar design situations
  5. author-timeline     — Author activity across OR1200's commit history

Usage:
    python src/demo_temporal_query.py              # run all demos
    python src/demo_temporal_query.py --query 1    # state-as-of-commit
    python src/demo_temporal_query.py --query 3    # cross-repo-analog
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ARANGO_ENDPOINT
from config_temporal import ARANGO_DATABASE
from db_utils import get_temporal_db


def _ts_human(ts: int) -> str:
    if not ts:
        return "unknown"
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Query 1: State-as-of-commit
# ---------------------------------------------------------------------------

def query_state_as_of(db, target_ts: int = None, repo: str = "openrisc/or1200",
                      limit: int = 20) -> list[dict]:
    """Modules active at a given Unix timestamp."""
    print_header("Query 1: RTL State as-of Timestamp")

    if target_ts is None:
        # Default: use median commit time for demo
        commits = list(db.aql.execute(
            "FOR c IN GitCommit FILTER c.repo == @repo "
            "SORT c.valid_from_ts ASC RETURN c.valid_from_ts",
            bind_vars={"repo": repo}
        ))
        if commits:
            target_ts = commits[len(commits) // 2]
        else:
            print("  No commits found — run temporal ETL first.")
            return []

    print(f"  Repo: {repo}  @  {_ts_human(target_ts)}")

    results = list(db.aql.execute(
        """
        FOR m IN RTL_Module
          FILTER m.repo == @repo
          FILTER m.valid_from_ts <= @ts
          FILTER (m.valid_to_ts == null OR m.valid_to_ts > @ts)
          SORT m.label ASC
          LIMIT @limit
          RETURN { label: m.label, epoch: m.design_epoch, introduced: m.valid_from_ts }
        """,
        bind_vars={"repo": repo, "ts": target_ts, "limit": limit}
    ))

    print(f"\n  {len(results)} modules active at {_ts_human(target_ts)}:")
    for r in results:
        print(f"    {r['label']:40s}  epoch={r['epoch']}  "
              f"introduced={_ts_human(r.get('introduced',0))}")
    return results


# ---------------------------------------------------------------------------
# Query 2: Epoch evolution
# ---------------------------------------------------------------------------

def query_epoch_evolution(db, repo: str = "openrisc/or1200") -> list[dict]:
    """Show RTL elements introduced per epoch."""
    print_header("Query 2: Design Evolution by Epoch")
    print(f"  Repo: {repo}")

    results = list(db.aql.execute(
        """
        FOR m IN RTL_Module
          FILTER m.repo == @repo AND m.design_epoch != null
          COLLECT epoch = m.design_epoch INTO modules
          SORT epoch ASC
          RETURN { epoch: epoch, count: LENGTH(modules),
                   examples: (FOR x IN SLICE(modules, 0, 3) RETURN x.m.label) }
        """,
        bind_vars={"repo": repo}
    ))

    for r in results:
        print(f"  {r['epoch']:35s}  {r['count']:4d} modules  "
              f"e.g. {', '.join(r['examples'][:2])}")
    return results


# ---------------------------------------------------------------------------
# Query 3: Cross-repo structural analog
# ---------------------------------------------------------------------------

def query_cross_repo_analog(db, module_label: str = "or1200_alu",
                             target_repo_prefix: str = "MOR1KX_",
                             limit: int = 5) -> list[dict]:
    """Find the structural analog of a module in another repo."""
    print_header("Query 3: Cross-Repo Analog Finder")
    print(f"  Source: {module_label}  →  Target repo: {target_repo_prefix}")

    # Find the source module
    src = list(db.aql.execute(
        "FOR m IN RTL_Module FILTER m.label == @label LIMIT 1 RETURN m",
        bind_vars={"label": module_label}
    ))
    if not src:
        print(f"  Module '{module_label}' not found in RTL_Module collection.")
        return []

    src_id = src[0]["_id"]
    tgt_col = f"{target_repo_prefix}Golden_Entities"

    existing = {c["name"] for c in db.collections()}
    if "CROSS_REPO_SIMILAR_TO" not in existing:
        print("  No CROSS_REPO_SIMILAR_TO edges yet — run cross_repo_bridge.py first.")
        return []

    results = list(db.aql.execute(
        """
        FOR e IN CROSS_REPO_SIMILAR_TO
          FILTER e._from == @src_id
          LET target = DOCUMENT(e._to)
          FILTER target != null
          SORT e.similarity_score DESC
          LIMIT @limit
          RETURN { target: target.name, score: e.similarity_score, type: e.similarity_type }
        """,
        bind_vars={"src_id": src_id, "limit": limit}
    ))

    if not results:
        print(f"  No cross-repo analogs found for {module_label}.")
    else:
        print(f"\n  Top analogs of '{module_label}':")
        for r in results:
            print(f"    {r['target']:40s}  score={r['score']:.3f}  ({r['type']})")
    return results


# ---------------------------------------------------------------------------
# Query 4: Déjà vu situation match
# ---------------------------------------------------------------------------

def query_deja_vu(db, repo: str = "openrisc/or1200", exclude_same_repo: bool = True,
                  limit: int = 5) -> list[dict]:
    """Show all detected design situations, optionally cross-repo only."""
    print_header("Query 4: Déjà Vu — Design Situation Index")

    existing = {c["name"] for c in db.collections()}
    if "DesignSituation" not in existing:
        print("  No DesignSituation nodes yet — run situation_detector.py first.")
        return []

    filter_clause = "FILTER s.repo != @repo" if exclude_same_repo else ""
    results = list(db.aql.execute(
        f"""
        FOR s IN DesignSituation
          {filter_clause}
          SORT s.valid_from_ts ASC
          LIMIT @limit
          RETURN {{
            repo: s.repo,
            epoch: s.epoch,
            class: s.situation_class,
            outcome: s.outcome,
            tags: s.tags,
            ts: s.valid_from_ts
          }}
        """,
        bind_vars={"repo": repo, "limit": limit}
    ))

    print(f"\n  {len(results)} design situations{' (cross-repo)' if exclude_same_repo else ''}:")
    for r in results:
        tag_str = ", ".join(r.get("tags", [])[:4])
        print(f"    [{_ts_human(r.get('ts',0))}]  {r['repo']:25s}  "
              f"{r['class']:25s}  outcome={r['outcome']}  tags=[{tag_str}]")
    return results


# ---------------------------------------------------------------------------
# Query 5: Author timeline
# ---------------------------------------------------------------------------

def query_author_timeline(db, repo: str = "openrisc/or1200") -> list[dict]:
    """Author activity across the repo's commit history."""
    print_header("Query 5: Author Activity Timeline")
    print(f"  Repo: {repo}")

    results = list(db.aql.execute(
        """
        FOR c IN GitCommit
          FILTER c.repo == @repo AND c.metadata.author != null
          COLLECT author = c.metadata.author INTO commits
          LET commit_count = LENGTH(commits)
          LET first_ts = MIN(commits[*].c.valid_from_ts)
          LET last_ts  = MAX(commits[*].c.valid_from_ts)
          SORT commit_count DESC
          LIMIT 10
          RETURN { author, commits: commit_count,
                   first: first_ts, last: last_ts }
        """,
        bind_vars={"repo": repo}
    ))

    print(f"\n  Top authors in {repo}:")
    for r in results:
        span = f"{_ts_human(r['first'])} → {_ts_human(r['last'])}"
        print(f"    {r['author']:30s}  {r['commits']:4d} commits  {span}")
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

QUERIES = {
    "1": ("state-as-of-commit",  lambda db: query_state_as_of(db)),
    "2": ("epoch-evolution",     lambda db: query_epoch_evolution(db)),
    "3": ("cross-repo-analog",   lambda db: query_cross_repo_analog(db)),
    "4": ("deja-vu-match",       lambda db: query_deja_vu(db)),
    "5": ("author-timeline",     lambda db: query_author_timeline(db)),
}


def main():
    parser = argparse.ArgumentParser(description="Temporal knowledge graph demo queries")
    parser.add_argument("--query", choices=list(QUERIES.keys()),
                        help="Query number to run (default: all)")
    parser.add_argument("--module", default="or1200_alu",
                        help="Module label for cross-repo analog query")
    args = parser.parse_args()

    db = get_temporal_db()
    print(f"\n[demo] Database: {ARANGO_DATABASE} @ {ARANGO_ENDPOINT}")

    to_run = [args.query] if args.query else list(QUERIES.keys())
    for q_id in to_run:
        name, fn = QUERIES[q_id]
        try:
            fn(db)
        except Exception as e:
            print(f"[demo] Query {q_id} ({name}) failed: {e}")

    print("\n[demo] All queries complete.")


if __name__ == "__main__":
    main()
