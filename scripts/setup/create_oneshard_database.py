#!/usr/bin/env python3
"""
Create an ArangoDB database with OneShard layout (sharding=single).

Uses credentials from the project .env (same as other scripts: ARANGO_MODE,
ARANGO_ENDPOINT / LOCAL_ARANGO_*, ARANGO_USERNAME, ARANGO_PASSWORD).

Optional cluster HA (Enterprise):
  ARANGO_REPLICATION_FACTOR — default replication for collections in this DB
  ARANGO_WRITE_CONCERN       — must be <= replication factor

Examples:
  PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py
  PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py --name ic-knowledge-graph-temporal
  ARANGO_REPLICATION_FACTOR=2 PYTHONPATH=src python3 scripts/setup/create_oneshard_database.py --name mydb
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from db_utils import create_oneshard_database, get_system_db  # noqa: E402
from config import ARANGO_DATABASE  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Create a OneShard ArangoDB database.")
    p.add_argument(
        "--name",
        default=os.getenv("ARANGO_DATABASE") or ARANGO_DATABASE,
        help="Database name (default: ARANGO_DATABASE from .env / config)",
    )
    p.add_argument(
        "--fail-if-exists",
        action="store_true",
        help="Exit with code 1 if the database already exists (default: skip quietly).",
    )
    args = p.parse_args()
    name = args.name.strip()
    if not name:
        print("ERROR: empty database name", file=sys.stderr)
        sys.exit(2)

    sys_db = get_system_db()
    if sys_db.has_database(name):
        if args.fail_if_exists:
            print(f"ERROR: database already exists: {name}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Database already exists (skip): {name}")
        return

    create_oneshard_database(name)
    print(f"[OK] Created OneShard database: {name}")


if __name__ == "__main__":
    main()
