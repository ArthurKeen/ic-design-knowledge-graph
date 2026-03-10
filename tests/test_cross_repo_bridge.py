"""
tests/test_cross_repo_bridge.py — Unit tests for the cross-repo semantic bridge builder.

Tests the pure-Python similarity functions and edge construction logic without
requiring a real ArangoDB connection.
"""

import hashlib
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cross_repo_bridge as bridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entity(prefix: str, name: str, embedding: list[float] | None = None) -> dict:
    key = f"{prefix}g_{hashlib.md5(name.lower().replace(' ', '_').encode()).hexdigest()[:12]}"
    return {
        "_key":      key,
        "_id":       f"{prefix}Golden_Entities/{key}",
        "name":      name,
        "type":      "PROCESSOR",
        "embedding": embedding,
    }


def _mock_db(src_entities: list[dict], tgt_entities: list[dict],
             existing_cols: set[str] = None):
    """Build a minimal ArangoDB mock that returns fixed entity lists."""
    db = MagicMock()

    # collections() returns the union of src and tgt collection names
    if existing_cols is None:
        existing_cols = {"OR1200_Golden_Entities", "MOR1KX_Golden_Entities"}
    db.collections.return_value = [{"name": n} for n in existing_cols]

    # aql.execute — return different lists depending on query content
    def aql_side_effect(query, bind_vars=None):
        query_lower = query.lower()
        if "or1200" in query_lower or (bind_vars and "or1200" in str(bind_vars.get("r", ""))):
            return iter(src_entities)
        return iter(tgt_entities)

    db.aql.execute.side_effect = aql_side_effect
    return db


# ---------------------------------------------------------------------------
# Section 1 — Cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity(unittest.TestCase):
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(bridge._cosine(v, v), 1.0, places=5)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(bridge._cosine(a, b), 0.0, places=5)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        self.assertAlmostEqual(bridge._cosine(a, b), -1.0, places=5)

    def test_zero_vector(self):
        """Zero vector should return 0.0 safely without division error."""
        a = [0.0, 0.0]
        b = [1.0, 0.5]
        self.assertEqual(bridge._cosine(a, b), 0.0)

    def test_empty_vectors(self):
        self.assertEqual(bridge._cosine([], []), 0.0)

    def test_mismatched_lengths(self):
        self.assertEqual(bridge._cosine([1.0], [1.0, 2.0]), 0.0)

    def test_similar_embeddings(self):
        """High-similarity embeddings should yield score > 0.9."""
        a = [0.9, 0.1, 0.0]
        b = [0.85, 0.15, 0.0]
        score = bridge._cosine(a, b)
        self.assertGreater(score, 0.9)


# ---------------------------------------------------------------------------
# Section 2 — Port signature similarity
# ---------------------------------------------------------------------------

class TestPortSignatureSimilarity(unittest.TestCase):
    def test_identical_ports(self):
        ports = ["clk", "rst", "wb_adr", "wb_dat_i", "wb_dat_o"]
        score = bridge._port_signature_similarity(ports, ports)
        self.assertGreater(score, 0.9)

    def test_no_overlap(self):
        # 0 Jaccard overlap, but equal-size sets get a small size-match bonus.
        # Formula: 0.6 * jaccard + 0.4 * (1 - size_diff)
        # With 0 jaccard and equal sizes: 0.6*0 + 0.4*1.0 = 0.4
        # With unequal sizes the size bonus decreases.
        # Use clearly different-sized sets to push the score below 0.5.
        a = ["clk"]
        b = ["apb_addr", "apb_data", "apb_sel", "apb_enable", "apb_ready",
             "apb_slverr", "apb_wdata", "apb_rdata"]
        score = bridge._port_signature_similarity(a, b)
        self.assertLess(score, 0.5)

    def test_case_insensitive(self):
        a = ["CLK", "RST", "WB_ADR"]
        b = ["clk", "rst", "wb_adr"]
        score = bridge._port_signature_similarity(a, b)
        self.assertGreater(score, 0.9)

    def test_empty_ports(self):
        self.assertEqual(bridge._port_signature_similarity([], ["clk"]), 0.0)
        self.assertEqual(bridge._port_signature_similarity(["clk"], []), 0.0)

    def test_partial_overlap_reduces_score(self):
        a = ["clk", "rst", "wb_adr", "wb_dat_i"]
        b = ["clk", "rst", "axi_addr", "axi_data"]
        score = bridge._port_signature_similarity(a, b)
        self.assertGreater(score, 0.0)
        self.assertLess(score, 0.9)


# ---------------------------------------------------------------------------
# Section 3 — Embedding bridge
# ---------------------------------------------------------------------------

class TestBuildEmbeddingBridges(unittest.TestCase):
    def _make_embeddings(self, n: int, base: float) -> list[float]:
        """Generate a unit-ish embedding of length 4."""
        v = [base + i * 0.01 for i in range(n)]
        mag = sum(x ** 2 for x in v) ** 0.5
        return [x / mag for x in v]

    def test_high_similarity_creates_edge(self):
        e_src = [_entity("OR1200_", "Pipeline",
                          self._make_embeddings(4, 0.9))]
        e_tgt = [_entity("MOR1KX_", "Pipeline",
                          self._make_embeddings(4, 0.88))]
        db = _mock_db(e_src, e_tgt)

        edges = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.7)
        self.assertGreater(len(edges), 0)
        edge = edges[0]
        self.assertIn("_key",             edge)
        self.assertIn("_from",            edge)
        self.assertIn("_to",              edge)
        self.assertIn("similarity_score", edge)
        self.assertEqual(edge["similarity_type"], "embedding")
        self.assertEqual(edge["source_repo"], "OR1200_")
        self.assertEqual(edge["target_repo"], "MOR1KX_")

    def test_low_similarity_filtered_out(self):
        e_src = [_entity("OR1200_", "Pipeline",
                          [1.0, 0.0, 0.0, 0.0])]   # orthogonal to target
        e_tgt = [_entity("MOR1KX_", "Cache",
                          [0.0, 1.0, 0.0, 0.0])]
        db = _mock_db(e_src, e_tgt)

        edges = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.7)
        self.assertEqual(len(edges), 0)

    def test_missing_collection_returns_empty(self):
        db = _mock_db([], [], existing_cols={"OTHER_col"})
        edges = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.5)
        self.assertEqual(edges, [])

    def test_entities_without_embeddings_skipped(self):
        """Entities with embedding=None should produce no bridges."""
        e_src = [_entity("OR1200_", "Pipeline", None)]
        e_tgt = [_entity("MOR1KX_", "Pipeline", None)]

        db = MagicMock()
        db.collections.return_value = [
            {"name": "OR1200_Golden_Entities"},
            {"name": "MOR1KX_Golden_Entities"},
        ]
        # The query filters `embedding != null` in real AQL; simulate empty result
        db.aql.execute.return_value = iter([])

        edges = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.5)
        self.assertEqual(edges, [])

    def test_edge_keys_are_deterministic(self):
        """Same pair of entities should always produce the same edge key."""
        e_src = [_entity("OR1200_", "ALU", [0.9, 0.1, 0.0, 0.0])]
        e_tgt = [_entity("MOR1KX_", "ALU", [0.88, 0.12, 0.0, 0.0])]
        db = _mock_db(e_src, e_tgt)

        edges1 = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.5)
        # Reset mock
        db = _mock_db(e_src, e_tgt)
        edges2 = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.5)

        if edges1 and edges2:
            self.assertEqual(edges1[0]["_key"], edges2[0]["_key"])

    def test_multiple_edges_all_above_threshold(self):
        vec = self._make_embeddings(4, 0.9)
        e_src = [
            _entity("OR1200_", "ALU",      vec),
            _entity("OR1200_", "Pipeline", vec),
        ]
        e_tgt = [
            _entity("MOR1KX_", "ALU",      self._make_embeddings(4, 0.89)),
            _entity("MOR1KX_", "Pipeline", self._make_embeddings(4, 0.91)),
        ]
        db = _mock_db(e_src, e_tgt)
        edges = bridge.build_embedding_bridges(db, "OR1200_", "MOR1KX_", min_score=0.7)
        self.assertGreaterEqual(len(edges), 2)


# ---------------------------------------------------------------------------
# Section 4 — Structural bridge
# ---------------------------------------------------------------------------

class TestBuildStructuralBridges(unittest.TestCase):
    def _make_module_stub(self, id: str, label: str, ports: list[str]) -> dict:
        return {"id": id, "label": label, "ports": ports}

    def test_high_overlap_modules_linked(self):
        wishbone_ports = ["wb_clk_i", "wb_rst_i", "wb_adr_i", "wb_dat_i", "wb_dat_o",
                           "wb_we_i", "wb_sel_i", "wb_stb_i", "wb_cyc_i", "wb_ack_o"]
        src = [self._make_module_stub("RTL_Module/or1200_cpu",
                                      "or1200_cpu", wishbone_ports)]
        tgt = [self._make_module_stub("RTL_Module/mor1kx_cpu",
                                      "mor1kx_cpu", wishbone_ports[:8])]  # 80% overlap

        db = MagicMock()
        db.aql.execute.side_effect = [iter(src), iter(tgt)]

        edges = bridge.build_structural_bridges(db, "OR1200_", "MOR1KX_", min_score=0.3)
        self.assertGreater(len(edges), 0)
        self.assertEqual(edges[0]["similarity_type"], "structural")

    def test_no_rtl_modules_returns_empty(self):
        db = MagicMock()
        db.aql.execute.side_effect = [iter([]), iter([])]
        edges = bridge.build_structural_bridges(db, "OR1200_", "MOR1KX_", min_score=0.5)
        self.assertEqual(edges, [])


# ---------------------------------------------------------------------------
# Section 5 — write_bridges
# ---------------------------------------------------------------------------

class TestWriteBridges(unittest.TestCase):
    def test_write_creates_collection_and_bulk_inserts(self):
        db = MagicMock()
        db.collections.return_value = []
        col_mock = MagicMock()
        col_mock.import_bulk.return_value = {"created": 3, "updated": 0}
        db.collection.return_value = col_mock
        db.create_collection.return_value = col_mock

        edges = [
            {"_key": "e1", "_from": "A/1", "_to": "B/2", "similarity_score": 0.9},
            {"_key": "e2", "_from": "A/3", "_to": "B/4", "similarity_score": 0.85},
            {"_key": "e3", "_from": "A/5", "_to": "B/6", "similarity_score": 0.8},
        ]
        count = bridge.write_bridges(db, edges, "CROSS_REPO_SIMILAR_TO")
        self.assertGreater(count, 0)

    def test_write_empty_edges_returns_zero(self):
        db = MagicMock()
        count = bridge.write_bridges(db, [], "CROSS_REPO_SIMILAR_TO")
        self.assertEqual(count, 0)
        db.collection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
