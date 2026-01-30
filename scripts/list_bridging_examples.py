#!/usr/bin/env python3
"""
List strong bridging examples for demonstration.

Queries RESOLVED_TO and prints RTL_Module-level and subcomponent (RTL_Port,
RTL_Signal) bridges to Golden Entities, with parent module context for
ports/signals.

Usage:
  python scripts/list_bridging_examples.py
  python scripts/list_bridging_examples.py --json   # machine-readable
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from config import COL_MODULE, COL_PORT, COL_SIGNAL, EDGE_RESOLVED, COL_ENTITIES
from db_utils import get_db


def run_query(db):
    """Return all RESOLVED_TO edges with source label and target entity_name."""
    q = f"""
    FOR e IN {EDGE_RESOLVED}
        LET from_doc = DOCUMENT(e._from)
        LET to_doc = DOCUMENT(e._to)
        FILTER from_doc != null AND to_doc != null
        LET from_coll = PARSE_IDENTIFIER(e._from).collection
        LET from_key = PARSE_IDENTIFIER(e._from).key
        LET label = from_doc.label != null ? from_doc.label : from_doc.name
        RETURN {{
            from_coll: from_coll,
            from_key: from_key,
            from_id: e._from,
            from_label: label,
            to_id: e._to,
            to_entity: to_doc.entity_name,
            score: e.score,
            method: e.method
        }}
    """
    return list(db.aql.execute(q))


def parent_module_from_key(coll, key):
    """For RTL_Port / RTL_Signal, key is module.port or module.signal; return module."""
    if coll in (COL_PORT, COL_SIGNAL) and "." in key:
        return key.split(".", 1)[0]
    return None


def main():
    ap = argparse.ArgumentParser(description="List bridging examples for demo")
    ap.add_argument("--json", action="store_true", help="Output JSON only")
    args = ap.parse_args()
    db = get_db()
    rows = run_query(db)
    by_coll = {}
    for r in rows:
        c = r["from_coll"]
        if c not in by_coll:
            by_coll[c] = []
        r["parent_module"] = parent_module_from_key(c, r["from_key"])
        by_coll[c].append(r)
    if args.json:
        print(json.dumps({"by_collection": by_coll, "total_edges": len(rows)}, indent=2))
        return
    # Human-readable summary and demo suggestions
    print("=" * 70)
    print("RESOLVED_TO bridging summary")
    print("=" * 70)
    print(f"Total edges: {len(rows)}\n")
    for coll in [COL_MODULE, COL_PORT, COL_SIGNAL]:
        entries = by_coll.get(coll, [])
        print(f"  {coll}: {len(entries)} edges")
    print()
    # Good examples for demo
    print("=" * 70)
    print("Good examples for demonstration")
    print("=" * 70)
    # Module-level (if any)
    mods = by_coll.get(COL_MODULE, [])
    if mods:
        print("\n--- RTL_Module → Golden Entity ---")
        for r in mods[:15]:
            print(f"  {r['from_label']}  →  {r['to_entity']}  (score: {r.get('score')})")
        if len(mods) > 15:
            print(f"  ... and {len(mods) - 15} more")
    else:
        print("\n--- RTL_Module → Golden Entity ---")
        print("  (none; bridging only creates module edges when name similarity is high enough)")
    # Ports: group by parent module, show a few strong examples per module
    ports = by_coll.get(COL_PORT, [])
    ports_by_parent = {}
    if ports:
        for r in ports:
            p = r.get("parent_module") or "?"
            if p not in ports_by_parent:
                ports_by_parent[p] = []
            ports_by_parent[p].append(r)
        print("\n--- RTL_Port (by parent module) → Golden Entity ---")
        for parent in sorted(ports_by_parent.keys())[:12]:
            for r in ports_by_parent[parent][:3]:
                part = r["from_key"].split(".", 1)[-1] if "." in r["from_key"] else r["from_key"]
                print(f"  {parent}.{part}  →  {r['to_entity']}")
            if len(ports_by_parent[parent]) > 3:
                print(f"      (+ {len(ports_by_parent[parent]) - 3} more for this module)")
    # Signals: same
    sigs = by_coll.get(COL_SIGNAL, [])
    sigs_by_parent = {}
    if sigs:
        for r in sigs:
            p = r.get("parent_module") or "?"
            if p not in sigs_by_parent:
                sigs_by_parent[p] = []
            sigs_by_parent[p].append(r)
        print("\n--- RTL_Signal (by parent module) → Golden Entity ---")
        for parent in sorted(sigs_by_parent.keys())[:12]:
            for r in sigs_by_parent[parent][:3]:
                part = r["from_key"].split(".", 1)[-1] if "." in r["from_key"] else r["from_key"]
                print(f"  {parent}.{part}  →  {r['to_entity']}")
            if len(sigs_by_parent[parent]) > 3:
                print(f"      (+ {len(sigs_by_parent[parent]) - 3} more for this module)")
    # Suggested demo nodes: modules with most bridged ports/signals
    print("\n--- Suggested demo entry points ---")
    from collections import defaultdict
    combined = defaultdict(int)
    for parent, plist in ports_by_parent.items():
        combined[parent] += len(plist)
    for parent, plist in sigs_by_parent.items():
        combined[parent] += len(plist)
    for parent, count in sorted(combined.items(), key=lambda x: -x[1])[:8]:
        print(f"  Module {parent}: {count} bridged ports/signals — good for subcomponent demo")
    print()


if __name__ == "__main__":
    main()
