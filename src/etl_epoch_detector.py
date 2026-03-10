"""
etl_epoch_detector.py — Design epoch detection for the temporal IC knowledge graph.

Assigns each commit in a git repository to a named design epoch based on:
  1. First commit                        → "initial_commit"
  2. Git tags present on this commit     → "milestone_<tag>"
  3. >N days since last epoch boundary   → "period_<YYYY_MM>"
  4. High file-change ratio              → "major_refactor_<sha7>"
  5. Default                             → inherits previous commit's epoch

Usage:
    from etl_epoch_detector import detect_epochs

    commits = [{"sha": "abc123", "ts": 1020384000, "message": "..."}, ...]
    epochs = detect_epochs(repo_path="/path/to/repo", commits=commits)
    # Returns: {"abc123": "initial_commit", "def456": "milestone_v1.0", ...}
"""

import os
import re
import subprocess
import json
from datetime import datetime, timezone
from config_temporal import MAJOR_REFACTOR_THRESHOLD, EPOCH_WINDOW_DAYS, EPOCHS_FILE


def get_git_tags(repo_path: str) -> dict[str, list[str]]:
    """
    Returns a dict mapping commit SHA → [tag_name, ...].
    Some commits may have multiple tags.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "-l", "--format=%(objectname:short) %(refname:short)"],
            cwd=repo_path, capture_output=True, text=True, errors="replace"
        )
        tags: dict[str, list[str]] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                short_sha, tag = parts
                # Resolve short SHA to full SHA
                full_sha = _resolve_sha(repo_path, short_sha)
                if full_sha:
                    tags.setdefault(full_sha, []).append(tag)
        return tags
    except Exception as e:
        print(f"[epoch_detector] Warning: could not read git tags: {e}")
        return {}


def _resolve_sha(repo_path: str, ref: str) -> str | None:
    """Resolve any git ref (tag, short SHA) to full 40-char SHA."""
    try:
        # For tags, dereference to the commit object
        result = subprocess.run(
            ["git", "rev-parse", f"{ref}^0"],
            cwd=repo_path, capture_output=True, text=True
        )
        sha = result.stdout.strip()
        return sha if len(sha) == 40 else None
    except Exception:
        return None


def get_files_changed_count(repo_path: str, from_sha: str, to_sha: str) -> int:
    """
    Returns the number of RTL files (.v, .sv, .vhd, .vhdl) changed
    between two commits (exclusive from, inclusive to).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", from_sha, to_sha],
            cwd=repo_path, capture_output=True, text=True, errors="replace"
        )
        rtl_extensions = {".v", ".sv", ".vhd", ".vhdl", ".vh"}
        changed = [
            line.strip() for line in result.stdout.splitlines()
            if os.path.splitext(line.strip())[1].lower() in rtl_extensions
        ]
        return len(changed)
    except Exception:
        return 0


def count_rtl_files_at_commit(repo_path: str, sha: str) -> int:
    """Count total RTL files in tree at a given commit."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", sha],
            cwd=repo_path, capture_output=True, text=True, errors="replace"
        )
        rtl_extensions = {".v", ".sv", ".vhd", ".vhdl", ".vh"}
        return sum(
            1 for line in result.stdout.splitlines()
            if os.path.splitext(line.strip())[1].lower() in rtl_extensions
        )
    except Exception:
        return 1  # avoid division by zero


def _clean_tag_name(tag: str) -> str:
    """Normalize a git tag to a simple epoch label string."""
    # Remove 'v' prefix, replace dots and slashes with underscores
    label = re.sub(r"[/\.\-]", "_", tag.lstrip("v"))
    return f"milestone_{label}"


def detect_epochs(repo_path: str, commits: list[dict]) -> dict[str, str]:
    """
    Assign each commit to a named design epoch.

    Rules (in priority order):
      1. First commit                    → "initial_commit"
      2. Git tag on this commit           → "milestone_<tag>"
      3. >EPOCH_WINDOW_DAYS since last   → "period_<YYYY_MM>"
      4. RTL change ratio >= threshold   → "major_refactor_<sha7>"
      5. Default                         → inherit last epoch

    Args:
        repo_path:  Absolute path to the git repository.
        commits:    List of commit dicts, sorted oldest-first.
                    Each dict: {"sha": str, "ts": int, "author": str, "message": str}

    Returns:
        Dict mapping commit SHA → epoch label string.
    """
    if not commits:
        return {}

    tags = get_git_tags(repo_path)
    epochs: dict[str, str] = {}
    last_epoch = "development"
    last_epoch_ts: int = commits[0]["ts"]   # timestamp of the last epoch boundary

    for i, commit in enumerate(commits):
        sha = commit["sha"]
        ts  = commit.get("ts", 0)

        # Rule 1: first commit
        if i == 0:
            epoch = "initial_commit"
            last_epoch_ts = ts

        # Rule 2: git tag present on this commit
        elif sha in tags:
            epoch = _clean_tag_name(tags[sha][0])
            last_epoch_ts = ts

        # Rule 3: time-window — too long since last epoch boundary
        elif EPOCH_WINDOW_DAYS > 0 and (ts - last_epoch_ts) > (EPOCH_WINDOW_DAYS * 86400):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            epoch = f"period_{dt.strftime('%Y_%m')}"
            last_epoch_ts = ts

        # Rule 4: major refactor detection
        else:
            prev_sha = commits[i - 1]["sha"]
            rtl_total = count_rtl_files_at_commit(repo_path, sha)
            rtl_changed = get_files_changed_count(repo_path, prev_sha, sha)

            if rtl_total > 0 and (rtl_changed / rtl_total) >= MAJOR_REFACTOR_THRESHOLD:
                epoch = f"major_refactor_{sha[:7]}"
                last_epoch_ts = ts
            else:
                # Rule 5: inherit last epoch
                epoch = last_epoch

        epochs[sha] = epoch
        # initial_commit is a one-off label; subsequent commits default to "development"
        last_epoch = "development" if epoch == "initial_commit" else epoch

    return epochs


def save_epochs(epochs: dict[str, str], output_path: str = EPOCHS_FILE) -> None:
    """Persist epoch map to JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(epochs, f, indent=2)
    print(f"[epoch_detector] Saved {len(epochs)} epoch assignments → {output_path}")


def load_epochs(input_path: str = EPOCHS_FILE) -> dict[str, str]:
    """Load a previously saved epoch map."""
    if not os.path.exists(input_path):
        return {}
    with open(input_path, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Detect design epochs in a git repo")
    parser.add_argument("--repo", default=os.path.join(os.path.dirname(__file__), "..", "or1200"),
                        help="Path to git repo")
    parser.add_argument("--commits-json", default=None,
                        help="Path to commits JSON from etl_temporal_git (optional)")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    if args.commits_json and os.path.exists(args.commits_json):
        with open(args.commits_json) as f:
            commits = json.load(f)
    else:
        # Get commits directly
        result = subprocess.run(
            ["git", "log", "--reverse", "--pretty=format:%H|%an|%at|%s"],
            cwd=repo_path, capture_output=True, text=True, errors="replace"
        )
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 3:
                commits.append({
                    "sha": parts[0], "author": parts[1],
                    "ts": int(parts[2]), "message": parts[3] if len(parts) > 3 else ""
                })

    print(f"[epoch_detector] Processing {len(commits)} commits from {repo_path}")
    epochs = detect_epochs(repo_path, commits)
    save_epochs(epochs)

    # Print summary
    from collections import Counter
    epoch_counts = Counter(epochs.values())
    print("\nEpoch Distribution:")
    for epoch, count in sorted(epoch_counts.items(), key=lambda x: -x[1]):
        print(f"  {epoch:40s} {count:4d} commits")
