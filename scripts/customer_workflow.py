#!/usr/bin/env python3
"""
Customer workflow helper for numbered exercise databases.

Primary use:
  - customers explore `ic-knowledge-graph` read-only in the UI
  - then create `ic-knowledge-graph-N` (UI primary, script optional)
  - import docs via GraphRAG UI into the numbered DB
  - run this script to perform ETL, consolidation/bridging, and Visualizer setup

This wrapper avoids requiring customers to edit environment files by injecting
ARANGO_DATABASE into subprocesses.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Dict, List, Optional


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _print(msg: str) -> None:
    print(msg, flush=True)


def _run(
    args: List[str],
    env_overrides: Dict[str, str],
    cwd: str = REPO_ROOT,
) -> None:
    env = os.environ.copy()
    env.update(env_overrides)
    _print(f"[RUN] {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, env=env)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _python(script_path: str, env_overrides: Dict[str, str], extra: Optional[List[str]] = None) -> None:
    cmd = [sys.executable, script_path]
    if extra:
        cmd.extend(extra)
    _run(cmd, env_overrides=env_overrides)


def _create_db_if_missing(db_name: str) -> None:
    # Avoid importing config/db_utils at module import time to keep errors clean.
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from db_utils import get_system_db

    sys_db = get_system_db()

    # python-arango versions differ; support common APIs.
    exists = False
    try:
        exists = sys_db.has_database(db_name)  # type: ignore[attr-defined]
    except Exception:
        try:
            exists = db_name in (sys_db.databases() or [])  # type: ignore[attr-defined]
        except Exception:
            # If we can't determine existence, attempt create and handle error.
            exists = False

    if exists:
        _print(f"[OK] Database exists: {db_name}")
        return

    _print(f"[INFO] Creating database via API: {db_name}")
    try:
        sys_db.create_database(db_name)  # type: ignore[attr-defined]
        _print(f"[OK] Created database: {db_name}")
    except Exception as e:
        _print(f"[WARN] Failed to create database via API: {e}")
        _print("[INFO] UI primary path: Databases → Create database → use the name above.")
        raise


def cmd_init_db(db: str) -> None:
    _print("UI primary path:")
    _print("  ArangoDB UI → Databases → Create database")
    _print(f"  Name: {db}")
    _print("")
    _create_db_if_missing(db)


def cmd_install_visualizer(db: str) -> None:
    env = {"ARANGO_DATABASE": db, "LOCAL_ARANGO_DATABASE": db}
    _python("scripts/setup/install_theme.py", env)
    _python("scripts/setup/install_demo_setup.py", env, extra=["--db", db])
    _python("scripts/setup/install_author_visualizer.py", env, extra=["--db", db])


def _graphrag_collections_exist(db_name: str, prefix: str) -> bool:
    os.environ["ARANGO_DATABASE"] = db_name
    os.environ["LOCAL_ARANGO_DATABASE"] = db_name
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from db_utils import get_db

    db = get_db()
    # get_db uses ARANGO_DATABASE at import time via config, so ensure caller injected env.
    required = [
        f"{prefix}Entities",
        f"{prefix}Relations",
    ]
    return all(db.has_collection(c) for c in required)


def cmd_setup(db: str, skip_graphrag: bool) -> None:
    env = {"ARANGO_DATABASE": db, "LOCAL_ARANGO_DATABASE": db}

    # Core pipeline
    _python("scripts/master_etl.py", env)
    _python("src/create_graph.py", env)

    # Visualizer assets (safe to install early; linking requires a viewpoint)
    cmd_install_visualizer(db)

    if skip_graphrag:
        _print("[INFO] Skipping GraphRAG consolidation/bridging (requested).")
    else:
        # Best-effort: only run if GraphRAG import likely happened
        sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
        from config import GRAPHRAG_PREFIX

        try:
            if _graphrag_collections_exist(db, GRAPHRAG_PREFIX):
                _python("src/consolidator.py", env)
                _python("src/bridger_bulk.py", env)
            else:
                _print("[WARN] GraphRAG collections not found yet. Import docs via GraphRAG UI, then rerun:")
                _print(f"       python scripts/customer_workflow.py setup --db {db}")
        except Exception as e:
            _print(f"[WARN] GraphRAG post-import steps failed: {e}")
            _print(f"[INFO] You can rerun after GraphRAG import: python scripts/customer_workflow.py setup --db {db}")

    # Verification
    _python("scripts/smoke_test.py", env, extra=["--require-graph"])


def cmd_verify(db: str) -> None:
    env = {"ARANGO_DATABASE": db, "LOCAL_ARANGO_DATABASE": db}
    _python("scripts/smoke_test.py", env, extra=["--require-graph"])


def main() -> int:
    p = argparse.ArgumentParser(description="Customer workflow helper for numbered databases")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="Create the numbered database (UI primary; API/script optional)")
    p_init.add_argument("--db", required=True, help="Target database name (e.g., ic-knowledge-graph-1)")

    p_setup = sub.add_parser("setup", help="Run ETL + visualizer setup (+ GraphRAG consolidation/bridging if available)")
    p_setup.add_argument("--db", required=True, help="Target database name (e.g., ic-knowledge-graph-1)")
    p_setup.add_argument("--skip-graphrag", action="store_true", help="Skip GraphRAG consolidation/bridging steps")

    p_vis = sub.add_parser("install-visualizer", help="Install theme, saved queries, and canvas actions for the target DB")
    p_vis.add_argument("--db", required=True, help="Target database name (e.g., ic-knowledge-graph-1)")

    p_ver = sub.add_parser("verify", help="Run smoke verification for the target DB")
    p_ver.add_argument("--db", required=True, help="Target database name (e.g., ic-knowledge-graph-1)")

    args = p.parse_args()

    if args.cmd == "init-db":
        cmd_init_db(args.db)
    elif args.cmd == "setup":
        cmd_setup(args.db, skip_graphrag=bool(args.skip_graphrag))
    elif args.cmd == "install-visualizer":
        cmd_install_visualizer(args.db)
    elif args.cmd == "verify":
        cmd_verify(args.db)
    else:
        raise SystemExit(2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

