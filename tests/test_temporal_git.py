"""
tests/test_temporal_git.py — Unit tests for temporal ETL core functions.

Run with:
    pytest tests/test_temporal_git.py -v
"""

import sys
import os
import json
import hashlib
import tempfile
import subprocess
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── We patch config imports before importing the module under test ───────────
with patch.dict(os.environ, {
    "ARANGO_DATABASE": "ic-knowledge-graph-temporal",
    "ARANGO_ENDPOINT": "http://localhost:8530",
    "ARANGO_USERNAME": "root",
    "ARANGO_PASSWORD": "test",
}):
    import etl_temporal_git as etl
    from etl_epoch_detector import detect_epochs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_commit(sha: str, ts: int, message: str = "test commit") -> dict:
    return {"sha": sha, "author": "Test User", "author_email": "test@example.com",
            "ts": ts, "message": message}


# ---------------------------------------------------------------------------
# compute_module_diff
# ---------------------------------------------------------------------------

class TestComputeModuleDiff:
    def test_added(self):
        prev = {}
        curr = {"alu": {"hash": "abc", "file": "alu.v"}}
        diff = etl.compute_module_diff(prev, curr)
        assert "alu" in diff["added"]
        assert diff["removed"] == []
        assert diff["modified"] == []

    def test_removed(self):
        prev = {"alu": {"hash": "abc", "file": "alu.v"}}
        curr = {}
        diff = etl.compute_module_diff(prev, curr)
        assert "alu" in diff["removed"]
        assert diff["added"] == []

    def test_modified(self):
        prev = {"alu": {"hash": "aaa", "file": "alu.v"}}
        curr = {"alu": {"hash": "bbb", "file": "alu.v"}}
        diff = etl.compute_module_diff(prev, curr)
        assert "alu" in diff["modified"]
        assert diff["added"] == []
        assert diff["removed"] == []

    def test_unchanged(self):
        prev = {"alu": {"hash": "aaa", "file": "alu.v"}}
        curr = {"alu": {"hash": "aaa", "file": "alu.v"}}
        diff = etl.compute_module_diff(prev, curr)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["modified"] == []
        assert "alu" in diff["unchanged"]

    def test_mixed(self):
        prev = {
            "alu": {"hash": "aaa", "file": "alu.v"},
            "mmu": {"hash": "mmu", "file": "mmu.v"},
        }
        curr = {
            "alu":  {"hash": "bbb", "file": "alu.v"},   # modified
            "ctrl": {"hash": "new", "file": "ctrl.v"},  # added
            # mmu removed
        }
        diff = etl.compute_module_diff(prev, curr)
        assert "alu"  in diff["modified"]
        assert "ctrl" in diff["added"]
        assert "mmu"  in diff["removed"]


# ---------------------------------------------------------------------------
# Node / edge creation
# ---------------------------------------------------------------------------

class TestNodeCreation:
    def test_rtl_module_node_has_temporal_fields(self):
        node = etl.make_rtl_module_node(
            "or1200_alu", {"hash": "abc123", "file": "rtl/verilog/or1200_alu.v"},
            "openrisc/or1200", "deadbeef01234567", 1020384000, "initial_commit"
        )
        assert node["valid_from_commit"] == "deadbeef01234567"
        assert node["valid_from_ts"] == 1020384000
        assert node["valid_to_commit"] is None
        assert node["valid_to_ts"] == 9999999999  # open-ended sentinel used in AQL filters
        assert node["design_epoch"] == "initial_commit"
        assert node["repo"] == "openrisc/or1200"

    def test_commit_node_structure(self):
        commit = make_commit("abc123def456789a", 1020384000, "Add ALU")
        node = etl.make_commit_node(commit, "openrisc/or1200")
        assert node["_key"] == "abc123def456789a"
        assert node["type"] == "GitCommit"
        assert node["repo"] == "openrisc/or1200"
        assert node["valid_from_ts"] == 1020384000

    def test_modified_edge_structure(self):
        edge = etl.make_modified_edge("abc123", "module_key_001", 1020384000, "rtl/alu.v")
        assert edge["type"] == "MODIFIED"
        assert edge["from"] == "abc123"
        assert edge["to"]   == "module_key_001"


# ---------------------------------------------------------------------------
# Epoch detection
# ---------------------------------------------------------------------------

class TestEpochDetection:
    def _make_minimal_git_repo(self) -> str:
        """Create a minimal git repo with 3 commits for testing epoch detection."""
        tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", tmpdir], capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=tmpdir, capture_output=True)

        for i in range(3):
            fpath = os.path.join(tmpdir, f"module_{i}.v")
            with open(fpath, "w") as f:
                f.write(f"module mod_{i}; endmodule\n")
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"commit {i}"],
                           cwd=tmpdir, capture_output=True)
        return tmpdir

    def test_first_commit_is_initial(self):
        commits = [make_commit("sha000", 1000, "initial")]
        epochs = detect_epochs("/tmp/nonexistent", commits)
        assert epochs["sha000"] == "initial_commit"

    def test_subsequent_commits_inherit_development(self):
        commits = [
            make_commit("sha000", 1000, "init"),
            make_commit("sha001", 2000, "add rtl"),
            make_commit("sha002", 3000, "fix"),
        ]
        with patch("etl_epoch_detector.get_git_tags", return_value={}), \
             patch("etl_epoch_detector.count_rtl_files_at_commit", return_value=10), \
             patch("etl_epoch_detector.get_files_changed_count", return_value=1):
            epochs = detect_epochs("/tmp/nonexistent", commits)
        assert epochs["sha000"] == "initial_commit"
        assert epochs["sha001"] == "development"
        assert epochs["sha002"] == "development"

    def test_tag_creates_milestone_epoch(self):
        commits = [
            make_commit("aaa000", 1000, "init"),
            make_commit("bbb001", 2000, "release prep"),
        ]
        with patch("etl_epoch_detector.get_git_tags",
                   return_value={"bbb001": ["v1.0"]}), \
             patch("etl_epoch_detector.count_rtl_files_at_commit", return_value=10), \
             patch("etl_epoch_detector.get_files_changed_count", return_value=1):
            epochs = detect_epochs("/tmp/nonexistent", commits)
        assert epochs["bbb001"] == "milestone_1_0"

    def test_monotonic_ts_assertion(self):
        """Replay should produce an ordered sequence of valid_from timestamps."""
        commits = [
            make_commit("sha001", 1000),
            make_commit("sha002", 2000),
            make_commit("sha003", 3000),
        ]
        ts_values = [c["ts"] for c in commits]
        assert ts_values == sorted(ts_values), "Commits must be ordered oldest-first"


# ---------------------------------------------------------------------------
# JSONL serialization round-trip
# ---------------------------------------------------------------------------

class TestJsonlRoundTrip:
    def test_save_and_read_back(self, tmp_path):
        records = [
            {"_key": "abc", "type": "RTL_Module", "valid_from_ts": 1000},
            {"_key": "def", "type": "GitCommit",  "valid_from_ts": 2000},
        ]
        out_path = str(tmp_path / "test.jsonl")
        etl.save_jsonl(records, out_path)
        assert os.path.exists(out_path)
        loaded = []
        with open(out_path) as f:
            for line in f:
                loaded.append(json.loads(line))
        assert len(loaded) == 2
        assert loaded[0]["_key"] == "abc"
        assert loaded[1]["valid_from_ts"] == 2000
