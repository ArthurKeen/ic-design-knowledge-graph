"""
scripts/multi_repo/clone_manager.py — Manage local clones of target IC repos.

Clones repos on first run; pulls latest on subsequent runs.
Respects local_path overrides in the registry (e.g., the existing or1200 submodule).

Usage:
    from clone_manager import ensure_clone

    local_path = ensure_clone(repo_config)
"""

import os
import sys
import subprocess

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, SRC_DIR)

from config_temporal import REPOS_DIR, get_local_path


def ensure_clone(repo_config: dict, verbose: bool = True) -> str:
    """
    Ensure the repo is cloned locally. Pull latest if already present.

    Args:
        repo_config: Dict from repo_registry.yaml with keys:
                     name, github_url, branch, local_path (optional)
        verbose:     Print progress messages.

    Returns:
        Absolute path to the local clone.
    """
    local_path = get_local_path(repo_config)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if os.path.isdir(os.path.join(local_path, ".git")):
        if verbose:
            print(f"[clone_manager] Pulling {repo_config['name']} at {local_path} …")
        result = subprocess.run(
            ["git", "pull", "--quiet"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  [WARNING] git pull failed: {result.stderr[:200]}")
    else:
        if verbose:
            print(f"[clone_manager] Cloning {repo_config['github_url']} → {local_path} …")
        os.makedirs(local_path, exist_ok=True)
        result = subprocess.run(
            ["git", "clone",
             "--branch", repo_config.get("branch", "master"),
             repo_config["github_url"],
             local_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Clone failed for {repo_config['name']}: {result.stderr[:400]}"
            )

    if verbose:
        print(f"  ✓ {repo_config['name']} ready at {local_path}")

    return local_path


def clone_all(repos: list[dict], verbose: bool = True) -> dict[str, str]:
    """
    Ensure all repos in the list are cloned.
    Returns: {repo_name: local_path}
    """
    paths = {}
    for repo in repos:
        try:
            paths[repo["name"]] = ensure_clone(repo, verbose=verbose)
        except RuntimeError as e:
            print(f"[clone_manager] ERROR: {e}")
    return paths
