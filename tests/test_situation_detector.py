"""
tests/test_situation_detector.py — Unit tests for the design situation detector.

Tests situation node construction, epoch-based heuristics, and the dedup/save
logic without requiring a real ArangoDB connection.
"""

import hashlib
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import situation_detector as sd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _commit(sha: str, ts: int, epoch: str = "development") -> dict:
    return {
        "_key":          sha,
        "sha":           sha,
        "valid_from_ts": ts,
        "design_epoch":  epoch,
        "repo":          "openrisc/or1200",
        "message":       f"Commit {sha}",
    }


def _mock_db_with_commits(commits: list[dict]) -> MagicMock:
    """DB mock that returns commits on aql.execute() and empty lists for modules."""
    db = MagicMock()

    def aql_side(query, bind_vars=None):
        q = query.strip().lower()
        if "gitcommit" in q:
            return iter(commits)
        # module queries should return empty (no subsystem additions by default)
        return iter([])

    db.aql.execute.side_effect = aql_side
    return db


# ---------------------------------------------------------------------------
# Section 1 — DesignSituation node schema
# ---------------------------------------------------------------------------

class TestMakeSituationNode(unittest.TestCase):
    def _make(self, cls: str = "release_prep", epoch: str = "milestone_v1") -> dict:
        return sd._make_situation_node(
            situation_class=cls,
            repo="openrisc/or1200",
            epoch=epoch,
            commit_range_start="aaa000",
            commit_range_end="bbb001",
            valid_from_ts=1000,
            valid_to_ts=2000,
            tags=["release", "v1.0"],
            outcome="milestone_release",
            notes="Test note",
        )

    def test_required_fields_present(self):
        node = self._make()
        for field in ("_key", "label", "type", "repo", "epoch", "situation_class",
                      "commit_range_start", "commit_range_end",
                      "valid_from_ts", "valid_to_ts", "tags", "outcome"):
            self.assertIn(field, node, f"Missing field: {field}")

    def test_key_is_deterministic(self):
        n1 = self._make()
        n2 = self._make()
        self.assertEqual(n1["_key"], n2["_key"])

    def test_key_changes_with_different_class(self):
        n1 = self._make("release_prep")
        n2 = self._make("major_refactor")
        self.assertNotEqual(n1["_key"], n2["_key"])

    def test_key_changes_with_different_epoch(self):
        n1 = self._make(epoch="milestone_v1")
        n2 = self._make(epoch="milestone_v2")
        self.assertNotEqual(n1["_key"], n2["_key"])

    def test_label_is_human_readable(self):
        node = self._make("release_prep")
        self.assertIn("Release Prep", node["label"])
        self.assertIn("openrisc/or1200", node["label"])

    def test_description_from_heuristics(self):
        node = self._make("major_refactor")
        self.assertIn("30%", node["description"])

    def test_unknown_class_has_empty_description(self):
        node = self._make("unknown_heuristic_xyz")
        self.assertEqual(node["description"], "")

    def test_tags_are_list(self):
        node = self._make()
        self.assertIsInstance(node["tags"], list)

    def test_embedding_starts_none(self):
        node = self._make()
        self.assertIsNone(node["embedding"])


# ---------------------------------------------------------------------------
# Section 2 — Heuristic: release prep
# ---------------------------------------------------------------------------

class TestDetectReleasePrepHeuristic(unittest.TestCase):
    def _commits(self) -> list[dict]:
        return [
            _commit("sha001", 1000, "milestone_v1_0"),
            _commit("sha002", 2000, "milestone_v1_0"),
            _commit("sha003", 3000, "milestone_v1_0"),
        ]

    def test_milestone_epoch_creates_situation(self):
        commits = self._commits()
        results = sd._detect_release_prep("openrisc/or1200", "milestone_v1_0", commits)
        self.assertEqual(len(results), 1)

    def test_non_milestone_epoch_returns_empty(self):
        commits = self._commits()
        results = sd._detect_release_prep("openrisc/or1200", "development", commits)
        self.assertEqual(results, [])

    def test_empty_commits_returns_empty(self):
        results = sd._detect_release_prep("openrisc/or1200", "milestone_v1_0", [])
        self.assertEqual(results, [])

    def test_outcome_is_milestone_release(self):
        commits = self._commits()
        result = sd._detect_release_prep("openrisc/or1200", "milestone_v1_0", commits)[0]
        self.assertEqual(result["outcome"], "milestone_release")

    def test_commit_range_spans_first_and_last(self):
        commits = self._commits()
        result = sd._detect_release_prep("openrisc/or1200", "milestone_v1_0", commits)[0]
        self.assertEqual(result["commit_range_start"], "sha001")
        self.assertEqual(result["commit_range_end"],   "sha003")


# ---------------------------------------------------------------------------
# Section 3 — Heuristic: major refactor
# ---------------------------------------------------------------------------

class TestDetectMajorRefactorHeuristic(unittest.TestCase):
    def test_major_refactor_epoch_creates_situation(self):
        commits = [_commit("sha001", 1000), _commit("sha002", 2000)]
        results = sd._detect_major_refactor("openrisc/or1200", "major_refactor_pipeline", commits)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["situation_class"], "major_refactor")

    def test_non_refactor_epoch_returns_empty(self):
        commits = [_commit("sha001", 1000)]
        results = sd._detect_major_refactor("openrisc/or1200", "development", commits)
        self.assertEqual(results, [])

    def test_empty_commits_returns_empty(self):
        results = sd._detect_major_refactor("openrisc/or1200", "major_refactor_x", [])
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# Section 4 — Heuristic: subsystem addition
# ---------------------------------------------------------------------------

class TestDetectSubsystemAddition(unittest.TestCase):
    def test_new_module_at_commit_creates_situation(self):
        """When new_modules_by_commit has an entry for a commit SHA, a situation is created."""
        commits = [_commit("sha001", 1000, "development")]

        new_modules_by_commit = {
            "sha001": [{"label": "or1200_mmu", "repo": "openrisc/or1200"}],
        }

        results = sd._detect_subsystem_addition(
            "openrisc/or1200", "development", commits, new_modules_by_commit
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["situation_class"], "subsystem_addition")
        self.assertIn("or1200_mmu", results[0]["tags"])

    def test_no_new_modules_returns_empty(self):
        commits = [_commit("sha001", 1000, "development")]
        new_modules_by_commit: dict = {}

        results = sd._detect_subsystem_addition(
            "openrisc/or1200", "development", commits, new_modules_by_commit
        )
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# Section 5 — Full detect_design_situations
# ---------------------------------------------------------------------------

class TestDetectDesignSituations(unittest.TestCase):
    def _make_commits(self) -> list[dict]:
        return [
            _commit("sha001", 1000, "initial_commit"),
            _commit("sha002", 2000, "development"),
            _commit("sha003", 3000, "milestone_v1_0"),
        ]

    def test_returns_list(self):
        db = _mock_db_with_commits(self._make_commits())
        result = sd.detect_design_situations("openrisc/or1200", db)
        self.assertIsInstance(result, list)

    def test_milestone_epoch_generates_release_prep_situation(self):
        commits = self._make_commits()
        db = _mock_db_with_commits(commits)
        situations = sd.detect_design_situations("openrisc/or1200", db)
        classes = {s["situation_class"] for s in situations}
        self.assertIn("release_prep", classes)

    def test_no_commits_returns_empty(self):
        db = _mock_db_with_commits([])
        result = sd.detect_design_situations("openrisc/or1200", db)
        self.assertEqual(result, [])

    def test_situations_have_unique_keys(self):
        commits = self._make_commits()
        db = _mock_db_with_commits(commits)
        situations = sd.detect_design_situations("openrisc/or1200", db)
        keys = [s["_key"] for s in situations]
        self.assertEqual(len(keys), len(set(keys)), "All situation keys must be unique")


# ---------------------------------------------------------------------------
# Section 6 — save_situations
# ---------------------------------------------------------------------------

class TestSaveSituations(unittest.TestCase):
    def _make_mock_db(self):
        db = MagicMock()
        db.collections.return_value = []
        col = MagicMock()
        col.insert.return_value = None
        db.collection.return_value = col
        db.create_collection.return_value = col
        return db, col

    def test_saves_all_situations(self):
        db, col = self._make_mock_db()
        situations = [
            {"_key": "sit001", "situation_class": "release_prep",   "repo": "openrisc/or1200"},
            {"_key": "sit002", "situation_class": "major_refactor", "repo": "openrisc/or1200"},
        ]
        count = sd.save_situations(db, situations)
        self.assertEqual(count, 2)
        self.assertEqual(col.insert.call_count, 2)

    def test_empty_list_returns_zero(self):
        db, col = self._make_mock_db()
        count = sd.save_situations(db, [])
        self.assertEqual(count, 0)
        col.insert.assert_not_called()

    def test_creates_collection_if_missing(self):
        db, col = self._make_mock_db()
        situations = [{"_key": "sit001", "situation_class": "release_prep"}]
        sd.save_situations(db, situations)
        db.create_collection.assert_called_once()

    def test_handles_insert_error_gracefully(self):
        """An insert error on one record should not prevent others from being saved."""
        db = MagicMock()
        db.collections.return_value = []
        col = MagicMock()

        call_count = [0]
        def flaky_insert(doc, overwrite=False):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("ArangoDB write error")

        col.insert.side_effect = flaky_insert
        db.collection.return_value = col
        db.create_collection.return_value = col

        situations = [
            {"_key": "sit001", "situation_class": "release_prep"},
            {"_key": "sit002", "situation_class": "major_refactor"},
        ]
        # Should not raise; first insert fails, second succeeds
        count = sd.save_situations(db, situations)
        self.assertEqual(count, 1)  # Only second succeeded


if __name__ == "__main__":
    unittest.main()
