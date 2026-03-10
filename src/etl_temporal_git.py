"""
etl_temporal_git.py — Temporal ETL: Commit-by-commit replay of an IC git repository.

This module walks a git repository from its first commit to HEAD,
extracting the RTL design state at each commit and computing diffs
to produce temporally annotated nodes and edges.

Output:
    data/temporal/temporal_nodes.jsonl — all RTL nodes with valid_from/valid_to metadata
    data/temporal/temporal_edges.jsonl — all MODIFIED edges + BELONGS_TO_EPOCH edges

Usage:
    python src/etl_temporal_git.py --repo ./or1200 --repo-name openrisc/or1200
    python src/etl_temporal_git.py --repo ./or1200 --limit 10  # first 10 commits only
"""

import os
import sys
import json
import hashlib
import subprocess
import argparse
import tempfile
from datetime import datetime
from collections import defaultdict

# Add src to path so config imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import COL_MODULE, COL_PORT, COL_SIGNAL, EDGE_MODIFIED, COL_COMMIT
from config_temporal import (
    TEMPORAL_NODES_FILE, TEMPORAL_EDGES_FILE, EPOCHS_FILE,
    INGESTION_LOG_FILE, COL_DESIGN_EPOCH, EDGE_BELONGS_TO_EPOCH,
)
from etl_epoch_detector import detect_epochs, save_epochs


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def get_commits_oldest_first(repo_path: str) -> list[dict]:
    """
    Return all commits in chronological order (oldest first).
    Each entry: {sha, author, author_email, ts, message}
    """
    sep = "|||"
    fmt = f"%H{sep}%an{sep}%ae{sep}%at{sep}%s"
    result = subprocess.run(
        ["git", "log", "--reverse", f"--pretty=format:{fmt}"],
        cwd=repo_path, capture_output=True, text=True, errors="replace"
    )
    commits = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(sep, 4)
        if len(parts) >= 4:
            commits.append({
                "sha":          parts[0],
                "author":       parts[1],
                "author_email": parts[2],
                "ts":           int(parts[3]),
                "message":      parts[4] if len(parts) > 4 else "",
            })
    return commits


def checkout_commit(repo_path: str, sha: str) -> bool:
    """Checkout a specific commit (detached HEAD). Returns True on success."""
    result = subprocess.run(
        ["git", "checkout", sha, "--quiet"],
        cwd=repo_path, capture_output=True, text=True
    )
    return result.returncode == 0


def restore_head(repo_path: str, branch: str = "master") -> None:
    """Restore the repo to the original branch."""
    subprocess.run(
        ["git", "checkout", branch, "--quiet"],
        cwd=repo_path, capture_output=True
    )
    # If branch doesn't exist try HEAD
    subprocess.run(
        ["git", "checkout", "-", "--quiet"],
        cwd=repo_path, capture_output=True
    )


# ---------------------------------------------------------------------------
# RTL Snapshot (thin wrapper around existing parse logic)
# ---------------------------------------------------------------------------

def _hash_file(path: str) -> str:
    """SHA-256 hash of file contents."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return "000000000000"


def parse_rtl_snapshot(repo_path: str, rtl_subdir: str = "rtl/verilog") -> dict:
    """
    Parse RTL files in repo_path/rtl_subdir.
    Returns: {filename (no ext): {path, hash, ports, signals}}

    This is a lightweight snapshot — full detail extraction uses the existing
    etl_rtl.py at load time.  Here we only track file identity and hash.
    """
    rtl_dir = os.path.join(repo_path, rtl_subdir)
    snapshot = {}

    if not os.path.isdir(rtl_dir):
        # Fall back to scanning entire repo for .v files
        rtl_dir = repo_path

    rtl_extensions = {".v", ".sv", ".vhd", ".vhdl"}
    for root, _, files in os.walk(rtl_dir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in rtl_extensions:
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, repo_path)
            module_name = os.path.splitext(fname)[0]
            snapshot[module_name] = {
                "file": rel_path,
                "hash": _hash_file(full_path),
                "fname": fname,
            }
    return snapshot


# ---------------------------------------------------------------------------
# Diff utilities
# ---------------------------------------------------------------------------

def compute_module_diff(prev: dict, curr: dict) -> dict:
    """
    Compute the diff between two RTL snapshots.
    Returns: {added: [names], removed: [names], modified: [names], unchanged: [names]}
    """
    prev_keys = set(prev.keys())
    curr_keys = set(curr.keys())

    added   = list(curr_keys - prev_keys)
    removed = list(prev_keys - curr_keys)
    shared  = prev_keys & curr_keys
    modified  = [k for k in shared if prev[k]["hash"] != curr[k]["hash"]]
    unchanged = [k for k in shared if prev[k]["hash"] == curr[k]["hash"]]

    return {
        "added":     added,
        "removed":   removed,
        "modified":  modified,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# Node / Edge creation helpers
# ---------------------------------------------------------------------------

def _make_node_key(repo_name: str, module_name: str, commit_sha: str) -> str:
    """Unique key for a versioned RTL module node."""
    raw = f"{repo_name}:{module_name}:{commit_sha}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def make_rtl_module_node(
    module_name: str,
    file_info: dict,
    repo_name: str,
    valid_from_commit: str,
    valid_from_ts: int,
    epoch: str,
) -> dict:
    return {
        "_key":               _make_node_key(repo_name, module_name, valid_from_commit),
        "label":              module_name,
        "type":               COL_MODULE,
        "repo":               repo_name,
        "file":               file_info.get("file", ""),
        "file_hash":          file_info.get("hash", ""),
        "valid_from_commit":  valid_from_commit,
        "valid_from_ts":      valid_from_ts,
        "valid_to_commit":    None,
        "valid_to_ts":        9999999999,   # sentinel: open-ended validity (ts > 9e9 in AQL)
        "design_epoch":       epoch,
        "metadata": {
            "file": file_info.get("file", ""),
        }
    }


def make_commit_node(commit: dict, repo_name: str, design_epoch: str = "development") -> dict:
    return {
        "_key":         commit["sha"],
        "label":        f"Commit {commit['sha'][:7]}",
        "type":         COL_COMMIT,
        "repo":         repo_name,
        "design_epoch": design_epoch,
        "valid_from_ts": commit["ts"],
        "valid_to_ts":   9999999999,   # sentinel: open-ended validity
        "metadata": {
            "author":       commit["author"],
            "author_email": commit["author_email"],
            "timestamp":    commit["ts"],
            "message":      commit["message"][:200],
        }
    }


def make_modified_edge(
    commit_sha: str,
    module_key: str,
    ts: int,
    file_path: str,
    target_valid_from_ts: int = None,
    target_valid_to_ts: int = None,
) -> dict:
    """
    MODIFIED edge from GitCommit → RTL_Module.

    Edge carries the target module's valid interval (mirrored from the vertex).
    This enables ArangoDB vertex-centric persistent indexes on
    [_from, valid_from_ts] and [_to, valid_to_ts] to prune traversals
    before loading the neighboring vertex.
    """
    raw = f"{commit_sha}:{module_key}:MODIFIED"
    edge_key = hashlib.md5(raw.encode()).hexdigest()[:16]
    return {
        "_key":           edge_key,
        "from":           commit_sha,
        "to":             module_key,
        "type":           EDGE_MODIFIED,
        # Interval mirrored from _to vertex for VCI pruning
        "valid_from_ts": target_valid_from_ts,
        "valid_to_ts":   target_valid_to_ts,
        "metadata": {
            "timestamp": ts,
            "file_path": file_path,
        }
    }


def make_epoch_node(repo_name: str, epoch: str, start_commit: str,
                    start_ts: int, git_tag: str = None) -> dict:
    key = hashlib.md5(f"{repo_name}:{epoch}".encode()).hexdigest()[:16]
    return {
        "_key":         key,
        "label":        f"{repo_name} — {epoch}",
        "type":         COL_DESIGN_EPOCH,
        "repo":         repo_name,
        "epoch_type":   _classify_epoch_type(epoch),
        "git_tag":      git_tag,
        "start_commit": start_commit,
        "end_commit":   None,       # filled in post-processing
        "start_ts":     start_ts,
        "end_ts":       None,
        "description":  f"Design epoch '{epoch}' in {repo_name}",
    }


def _classify_epoch_type(epoch_label: str) -> str:
    if epoch_label == "initial_commit":
        return "initial_commit"
    if epoch_label.startswith("milestone_"):
        return "milestone_tag"
    if epoch_label.startswith("major_refactor_"):
        return "major_refactor"
    if epoch_label == "development":
        return "development"
    return "other"


def make_belongs_to_epoch_edge(
    module_key: str,
    epoch_key: str,
    role: str,
    target_valid_from_ts: int = None,
    target_valid_to_ts: int = None,
) -> dict:
    """
    BELONGS_TO_EPOCH edge from RTL_Module → DesignEpoch.

    Edge carries the source module's valid interval so that VCI on
    [_from, valid_from_ts] allows efficient epoch membership queries.
    """
    raw = f"{module_key}:{epoch_key}:{role}"
    return {
        "_key":           hashlib.md5(raw.encode()).hexdigest()[:16],
        "from":           module_key,
        "to":             epoch_key,
        "type":           EDGE_BELONGS_TO_EPOCH,
        "role":           role,  # "introduced_in" | "modified_in" | "removed_in"
        # Interval mirrored from _from vertex for VCI pruning
        "valid_from_ts": target_valid_from_ts,
        "valid_to_ts":   target_valid_to_ts,
    }


# ---------------------------------------------------------------------------
# Main replay loop
# ---------------------------------------------------------------------------

def replay_git_history(
    repo_path: str,
    repo_name: str,
    rtl_subdir: str = "rtl/verilog",
    commit_limit: int = None,
    original_branch: str = "master",
) -> tuple[list[dict], list[dict]]:
    """
    Walk the git history of repo_path commit-by-commit (oldest first).
    Build temporally annotated RTL nodes and MODIFIED / BELONGS_TO_EPOCH edges.

    Returns:
        (all_nodes, all_edges) — lists of dicts ready for JSONL serialization.
    """
    print(f"\n[temporal_git] Starting temporal replay of '{repo_name}' at {repo_path}")

    # Step 1: get commits
    commits = get_commits_oldest_first(repo_path)
    if not commits:
        print("[temporal_git] No commits found. Aborting.")
        return [], []

    if commit_limit:
        commits = commits[:commit_limit]
        print(f"[temporal_git] Limiting to first {commit_limit} commits.")

    print(f"[temporal_git] {len(commits)} commits to process.")

    # Step 2: detect epochs
    print("[temporal_git] Detecting design epochs …")
    epoch_map = detect_epochs(repo_path, commits)
    save_epochs(epoch_map)

    # Step 3: build epoch nodes
    epoch_nodes_by_label: dict[str, dict] = {}
    for commit in commits:
        epoch_label = epoch_map.get(commit["sha"], "development")
        if epoch_label not in epoch_nodes_by_label:
            epoch_nodes_by_label[epoch_label] = make_epoch_node(
                repo_name, epoch_label,
                start_commit=commit["sha"],
                start_ts=commit["ts"],
            )

    # Finalize epoch end times
    epoch_labels_ordered = list(epoch_nodes_by_label.keys())
    for i, label in enumerate(epoch_labels_ordered):
        if i < len(epoch_labels_ordered) - 1:
            next_label = epoch_labels_ordered[i + 1]
            next_node = epoch_nodes_by_label[next_label]
            epoch_nodes_by_label[label]["end_commit"] = next_node["start_commit"]
            epoch_nodes_by_label[label]["end_ts"] = next_node["start_ts"]

    # Step 4: replay commits
    all_nodes: list[dict] = list(epoch_nodes_by_label.values())
    all_edges: list[dict] = []

    # Track live modules: {module_name: node_dict}
    live_modules: dict[str, dict] = {}
    # Map module_name → node _key (for edge creation)
    module_key_map: dict[str, str] = {}

    # dict of commit nodes keyed by sha
    commit_nodes: dict[str, dict] = {}

    try:
        prev_snapshot: dict = {}

        for i, commit in enumerate(commits):
            sha = commit["sha"]
            ts  = commit["ts"]
            epoch_label = epoch_map.get(sha, "development")
            epoch_key   = epoch_nodes_by_label[epoch_label]["_key"]

            print(f"  [{i+1:4d}/{len(commits)}] {sha[:7]} {epoch_label:30s} "
                  f"{datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')} "
                  f"— {commit['message'][:50]}")

            # Checkout commit
            if not checkout_commit(repo_path, sha):
                print(f"    [WARNING] Could not check out {sha[:7]}, skipping")
                continue

            # Build commit node (epoch must be set before RTL module nodes)
            epoch_label = epoch_assignments.get(sha, "development")
            c_node = make_commit_node(commit, repo_name, design_epoch=epoch_label)
            commit_nodes[sha] = c_node
            all_nodes.append(c_node)

            # Parse current RTL snapshot
            curr_snapshot = parse_rtl_snapshot(repo_path, rtl_subdir)

            # Compute diff
            diff = compute_module_diff(prev_snapshot, curr_snapshot)

            # Handle added modules
            for module_name in diff["added"]:
                node = make_rtl_module_node(
                    module_name, curr_snapshot[module_name],
                    repo_name, sha, ts, epoch_label
                )
                all_nodes.append(node)
                live_modules[module_name]  = node
                module_key_map[module_name] = node["_key"]

                all_edges.append(make_belongs_to_epoch_edge(
                    node["_key"], epoch_key, "introduced_in",
                    target_valid_from_ts=node["valid_from_ts"],
                    target_valid_to_ts=node["valid_to_ts"],
                ))
                # MODIFIED edge — interval from target node
                all_edges.append(make_modified_edge(
                    sha, node["_key"], ts,
                    curr_snapshot[module_name]["file"],
                    target_valid_from_ts=node["valid_from_ts"],
                    target_valid_to_ts=node["valid_to_ts"],
                ))

            # Handle modified modules — close old version, open new
            for module_name in diff["modified"]:
                old_node = live_modules.get(module_name)
                if old_node:
                    old_node["valid_to_commit"] = sha
                    old_node["valid_to_ts"]     = ts

                new_node = make_rtl_module_node(
                    module_name, curr_snapshot[module_name],
                    repo_name, sha, ts, epoch_label
                )
                all_nodes.append(new_node)
                live_modules[module_name]  = new_node
                module_key_map[module_name] = new_node["_key"]

                all_edges.append(make_belongs_to_epoch_edge(
                    new_node["_key"], epoch_key, "modified_in",
                    target_valid_from_ts=new_node["valid_from_ts"],
                    target_valid_to_ts=new_node["valid_to_ts"],
                ))
                all_edges.append(make_modified_edge(
                    sha, new_node["_key"], ts,
                    curr_snapshot[module_name]["file"],
                    target_valid_from_ts=new_node["valid_from_ts"],
                    target_valid_to_ts=new_node["valid_to_ts"],
                ))

            # Handle removed modules — close their validity
            for module_name in diff["removed"]:
                old_node = live_modules.pop(module_name, None)
                if old_node:
                    old_node["valid_to_commit"] = sha
                    old_node["valid_to_ts"]     = ts
                    old_key = old_node["_key"]
                    all_edges.append(make_belongs_to_epoch_edge(
                        old_key, epoch_key, "removed_in"
                    ))
                    module_key_map.pop(module_name, None)

            prev_snapshot = curr_snapshot

    finally:
        # Always restore original branch
        print(f"\n[temporal_git] Restoring to branch '{original_branch}' …")
        restore_head(repo_path, original_branch)

    print(f"\n[temporal_git] Replay complete.")
    print(f"  Nodes: {len(all_nodes)}")
    print(f"  Edges: {len(all_edges)}")
    return all_nodes, all_edges


# ---------------------------------------------------------------------------
# JSONL serialization
# ---------------------------------------------------------------------------

def save_jsonl(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"[temporal_git] Saved {len(records)} records → {path}")


def is_already_ingested(repo_name: str, commit_sha: str) -> bool:
    """Check ingestion log to see if this commit was already processed."""
    if not os.path.exists(INGESTION_LOG_FILE):
        return False
    with open(INGESTION_LOG_FILE, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("repo") == repo_name and entry.get("commit") == commit_sha:
                    return True
            except json.JSONDecodeError:
                continue
    return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Temporal ETL: replay git history commit-by-commit"
    )
    parser.add_argument(
        "--repo",
        default=os.path.join(os.path.dirname(__file__), "..", "or1200"),
        help="Path to git repository (default: ./or1200)"
    )
    parser.add_argument(
        "--repo-name",
        default="openrisc/or1200",
        help="Canonical name for this repo (e.g. openrisc/or1200)"
    )
    parser.add_argument(
        "--rtl-subdir",
        default="rtl/verilog",
        help="Subdirectory within repo containing RTL files"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N commits (for testing)"
    )
    parser.add_argument(
        "--branch",
        default="master",
        help="Original branch to restore after replay"
    )
    parser.add_argument(
        "--nodes-out",
        default=TEMPORAL_NODES_FILE,
        help="Output path for temporal nodes JSONL"
    )
    parser.add_argument(
        "--edges-out",
        default=TEMPORAL_EDGES_FILE,
        help="Output path for temporal edges JSONL"
    )

    args = parser.parse_args()
    repo_path = os.path.abspath(args.repo)

    nodes, edges = replay_git_history(
        repo_path=repo_path,
        repo_name=args.repo_name,
        rtl_subdir=args.rtl_subdir,
        commit_limit=args.limit,
        original_branch=args.branch,
    )

    save_jsonl(nodes, args.nodes_out)
    save_jsonl(edges, args.edges_out)
