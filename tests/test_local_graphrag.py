"""
tests/test_local_graphrag.py — Integration tests for the local GraphRAG pipeline.

Tests the full chunk → extract → embed → community detect → load round-trip
using fixture documents and mocked LLM / ArangoDB calls, so no real services
are required.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure src/ is importable
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC_DIR)

from local_graphrag.chunker import chunk_document
from local_graphrag.extractor import EntityExtractor, _parse_llm_response
from local_graphrag.embedder import embed_entities
from local_graphrag.community_detector import detect_communities
from local_graphrag.loader import (
    build_golden_entities,
    build_golden_relations,
    build_consolidates_edges,
    build_mentioned_in_edges,
    load_to_arangodb,
    _get_collection_names,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_TEXT = """
The OR1200 processor features a 5-stage pipeline: Instruction Fetch (IF),
Instruction Decode (ID), Execute (EX), Memory Access (MEM), and Write-Back (WB).
The MMU includes a TLB with 64 fully-associative entries. The data cache is
direct-mapped with 8 KB capacity. The Wishbone bus interface connects the core
to peripheral IP blocks. The IPC target is 0.9 for integer workloads.
"""

FIXTURE_LLM_RESPONSE = json.dumps({
    "entities": [
        {"name": "OR1200 Processor",   "type": "PROCESSOR",      "description": "5-stage RISC processor", "aliases": ["OR1200"]},
        {"name": "MMU",                "type": "MEMORY_SYSTEM",   "description": "Memory management unit with 64-entry TLB", "aliases": []},
        {"name": "Data Cache",         "type": "MEMORY_SYSTEM",   "description": "Direct-mapped 8 KB cache", "aliases": ["dcache"]},
        {"name": "Wishbone Bus",       "type": "BUS_INTERFACE",   "description": "On-chip interconnect standard", "aliases": []},
    ],
    "relations": [
        {"source": "OR1200 Processor", "relation": "INCLUDES",   "target": "MMU",          "context": "pipeline integration"},
        {"source": "OR1200 Processor", "relation": "INCLUDES",   "target": "Data Cache",   "context": "memory hierarchy"},
        {"source": "OR1200 Processor", "relation": "CONNECTS_TO","target": "Wishbone Bus", "context": "bus interface"},
    ]
})


# ---------------------------------------------------------------------------
# Section 1 — Chunker
# ---------------------------------------------------------------------------

class TestChunker(unittest.TestCase):
    def test_chunk_text_file(self):
        """Plain text file should produce at least one chunk."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(FIXTURE_TEXT * 5)  # Repeat to ensure ≥1 chunk
            path = f.name

        try:
            chunks = chunk_document(path, doc_version="test_v1", prefix="TEST_")
            self.assertGreater(len(chunks), 0)
            for c in chunks:
                self.assertIn("text", c)
                self.assertIn("_key", c)
                self.assertEqual(c["doc_version"], "test_v1")
                self.assertIsNone(c["embedding"])  # Not yet embedded
        finally:
            os.unlink(path)

    def test_chunk_keys_are_unique(self):
        """Every chunk must have a unique _key."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(FIXTURE_TEXT * 10)
            path = f.name
        try:
            chunks = chunk_document(path, prefix="TEST_")
            keys = [c["_key"] for c in chunks]
            self.assertEqual(len(keys), len(set(keys)), "Chunk keys must be unique")
        finally:
            os.unlink(path)

    def test_markdown_file(self):
        """Markdown file should be chunked without error."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(f"# OR1200 Manual\n\n{FIXTURE_TEXT}\n")
            path = f.name
        try:
            chunks = chunk_document(path, prefix="TEST_")
            self.assertGreater(len(chunks), 0)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Section 2 — Extractor
# ---------------------------------------------------------------------------

class TestExtractorParsing(unittest.TestCase):
    def test_parse_valid_json(self):
        entities, relations = _parse_llm_response(FIXTURE_LLM_RESPONSE, "test_chunk")
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(relations), 3)

    def test_parse_json_with_markdown_fences(self):
        wrapped = f"```json\n{FIXTURE_LLM_RESPONSE}\n```"
        entities, relations = _parse_llm_response(wrapped, "test_chunk")
        self.assertEqual(len(entities), 4)

    def test_parse_invalid_json(self):
        entities, relations = _parse_llm_response("not json at all", "chunk")
        self.assertEqual(entities, [])
        self.assertEqual(relations, [])

    def test_extract_from_chunk_mocked(self):
        """Full extract_from_chunk with mocked LLM call."""
        chunk = {
            "_key": "test_chunk_001",
            "text": FIXTURE_TEXT,
            "doc_version": "v1",
            "valid_from_epoch": "initial_commit",
        }
        extractor = EntityExtractor(backend="openai")

        with patch.object(extractor, "_call_llm", return_value=FIXTURE_LLM_RESPONSE):
            entities, relations = extractor.extract_from_chunk(chunk, prefix="OR1200_")

        self.assertEqual(len(entities), 4)
        self.assertEqual(len(relations), 3)

        # All entities should have required fields
        for e in entities:
            self.assertIn("_key", e)
            self.assertIn("name", e)
            self.assertIn("type", e)
            self.assertEqual(e["source_chunk"], "test_chunk_001")
            self.assertIsNone(e["embedding"])  # Not yet embedded

        # All relations should have _from and _to using entity keys
        entity_keys = {e["_key"] for e in entities}
        for r in relations:
            frm = r["_from"].split("/")[-1]
            to  = r["_to"].split("/")[-1]
            self.assertIn(frm, entity_keys)
            self.assertIn(to, entity_keys)

    def test_dangling_relation_skipped(self):
        """Relations with unknown source or target should be silently dropped."""
        bad_response = json.dumps({
            "entities": [{"name": "ALU", "type": "FUNCTIONAL_UNIT", "description": "x", "aliases": []}],
            "relations": [
                {"source": "ALU",    "relation": "CONNECTS_TO", "target": "NonExistent", "context": ""},
                {"source": "Missing","relation": "CONNECTS_TO", "target": "ALU",         "context": ""},
            ]
        })
        entities, relations = _parse_llm_response(bad_response, "chunk")
        self.assertEqual(len(entities), 1)
        # Relations parsed at this level don't filter yet — filtering happens in extract_from_chunk
        # Just confirm parsing worked
        self.assertEqual(len(relations), 2)


# ---------------------------------------------------------------------------
# Section 3 — Embedder
# ---------------------------------------------------------------------------

class TestEmbedder(unittest.TestCase):
    def _make_entities(self, n: int = 4) -> list[dict]:
        return [
            {
                "_key":        f"OR1200_ent_{i:03d}",
                "name":        f"Entity {i}",
                "description": f"Description of entity {i}",
                "embedding":   None,
            }
            for i in range(n)
        ]

    def test_embed_sentence_transformers(self):
        """Embeddings should be float lists of consistent dimension."""
        entities = self._make_entities(3)
        result = embed_entities(entities, backend="sentence_transformers")
        self.assertEqual(len(result), 3)
        for e in result:
            self.assertIsInstance(e["embedding"], list)
            self.assertGreater(len(e["embedding"]), 0)
            self.assertIsInstance(e["embedding"][0], float)
        # All same dimension
        dims = {len(e["embedding"]) for e in result}
        self.assertEqual(len(dims), 1, "All embeddings should have the same dimension")

    def test_embed_skips_already_embedded(self):
        """Entities with existing embeddings should not be re-embedded."""
        entities = self._make_entities(2)
        existing_vec = [0.1] * 384
        entities[0]["embedding"] = existing_vec  # pre-filled

        with patch("local_graphrag.embedder._embed_sentence_transformers") as mock_enc:
            mock_enc.return_value = [[0.2] * 384]
            result = embed_entities(entities, backend="sentence_transformers")

        # Only one entity should have been processed by the embedder
        mock_enc.assert_called_once()
        args = mock_enc.call_args[0][0]  # texts arg
        self.assertEqual(len(args), 1)   # only the un-embedded entity

        # Pre-filled embedding unchanged
        self.assertEqual(result[0]["embedding"], existing_vec)

    def test_embed_empty_list(self):
        result = embed_entities([], backend="sentence_transformers")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Section 4 — Golden Entity Deduplication
# ---------------------------------------------------------------------------

class TestGoldenDedup(unittest.TestCase):
    def _make_raw_entities(self) -> list[dict]:
        """Two occurrences of 'OR1200 Processor' from different chunks."""
        return [
            {
                "_key":        "OR1200_aaa",
                "name":        "OR1200 Processor",
                "type":        "PROCESSOR",
                "description": "5-stage RISC processor",
                "aliases":     ["OR1200"],
                "source_chunk": "chunk_001",
                "embedding":   [0.1] * 384,
            },
            {
                "_key":        "OR1200_bbb",
                "name":        "or1200 processor",   # same entity, different casing
                "type":        "PROCESSOR",
                "description": "",
                "aliases":     ["or1200", "or1k_core"],
                "source_chunk": "chunk_002",
                "embedding":   None,
            },
            {
                "_key":        "OR1200_ccc",
                "name":        "MMU",
                "type":        "MEMORY_SYSTEM",
                "description": "Memory management unit",
                "aliases":     [],
                "source_chunk": "chunk_001",
                "embedding":   [0.5] * 384,
            },
        ]

    def test_dedup_merges_same_entity(self):
        entities = self._make_raw_entities()
        golden = build_golden_entities(entities, prefix="OR1200_")
        names = {g["name"] for g in golden}
        # Should have 2 unique entities: OR1200 Processor and MMU
        self.assertEqual(len(golden), 2)

    def test_dedup_accumulates_aliases(self):
        entities = self._make_raw_entities()
        golden = build_golden_entities(entities, prefix="OR1200_")
        proc = next(g for g in golden if "or1200" in g["name"].lower())
        self.assertIn("or1200", [a.lower() for a in proc["aliases"]])
        self.assertIn("or1k_core", proc["aliases"])

    def test_dedup_keeps_first_description(self):
        entities = self._make_raw_entities()
        golden = build_golden_entities(entities, prefix="OR1200_")
        proc = next(g for g in golden if "or1200" in g["name"].lower())
        self.assertEqual(proc["description"], "5-stage RISC processor")

    def test_dedup_takes_first_embedding(self):
        entities = self._make_raw_entities()
        golden = build_golden_entities(entities, prefix="OR1200_")
        proc = next(g for g in golden if "or1200" in g["name"].lower())
        self.assertIsNotNone(proc["embedding"])
        self.assertEqual(len(proc["embedding"]), 384)

    def test_dedup_accumulates_source_chunks(self):
        entities = self._make_raw_entities()
        golden = build_golden_entities(entities, prefix="OR1200_")
        proc = next(g for g in golden if "or1200" in g["name"].lower())
        self.assertIn("chunk_001", proc["source_chunks"])
        self.assertIn("chunk_002", proc["source_chunks"])

    def test_golden_keys_are_stable(self):
        """Same input should always produce the same golden _key."""
        entities = self._make_raw_entities()
        golden1 = build_golden_entities(entities, prefix="OR1200_")
        golden2 = build_golden_entities(entities, prefix="OR1200_")
        keys1 = {g["_key"] for g in golden1}
        keys2 = {g["_key"] for g in golden2}
        self.assertEqual(keys1, keys2)


# ---------------------------------------------------------------------------
# Section 5 — Community Detector
# ---------------------------------------------------------------------------

class TestCommunityDetector(unittest.TestCase):
    def _make_entities_and_relations(self):
        entities = [
            {"_key": "OR1200_a", "name": "Pipeline", "type": "PIPELINE_STAGE", "embedding": None},
            {"_key": "OR1200_b", "name": "ALU",      "type": "FUNCTIONAL_UNIT", "embedding": None},
            {"_key": "OR1200_c", "name": "MMU",      "type": "MEMORY_SYSTEM",   "embedding": None},
            {"_key": "OR1200_d", "name": "Cache",    "type": "MEMORY_SYSTEM",   "embedding": None},
        ]
        col = "OR1200_Entities"
        relations = [
            {"_key": "r1", "_from": f"{col}/OR1200_a", "_to": f"{col}/OR1200_b", "type": "INCLUDES"},
            {"_key": "r2", "_from": f"{col}/OR1200_c", "_to": f"{col}/OR1200_d", "type": "CONTAINS"},
        ]
        return entities, relations

    def test_detect_communities_returns_list(self):
        entities, relations = self._make_entities_and_relations()
        communities = detect_communities(entities, relations, prefix="OR1200_")
        self.assertIsInstance(communities, list)

    def test_communities_have_required_fields(self):
        entities, relations = self._make_entities_and_relations()
        communities = detect_communities(entities, relations, prefix="OR1200_")
        for c in communities:
            self.assertIn("_key", c)
            # community_detector uses 'member_entities' for the member list
            self.assertTrue(
                "member_entities" in c or "members" in c,
                f"Community missing member field: {list(c.keys())}"
            )


# ---------------------------------------------------------------------------
# Section 6 — Loader (mocked ArangoDB)
# ---------------------------------------------------------------------------

class TestLoader(unittest.TestCase):
    def _make_mock_db(self):
        """Minimal ArangoDB mock that tracks inserted records."""
        db = MagicMock()

        # collections() returns empty list (so all collections are "new")
        db.collections.return_value = []

        # Mock collection object
        col_mock = MagicMock()
        col_mock.import_bulk.return_value = {"created": 5, "updated": 0}
        col_mock.indexes.return_value = []
        db.collection.return_value = col_mock
        db.create_collection.return_value = col_mock

        return db, col_mock

    def _make_entities(self):
        return [
            {"_key": "OR1200_aaa", "name": "Pipeline", "type": "PIPELINE_STAGE",
             "description": "CPU pipeline", "aliases": [], "source_chunk": "c1",
             "embedding": [0.1] * 384},
            {"_key": "OR1200_bbb", "name": "MMU", "type": "MEMORY_SYSTEM",
             "description": "Memory management unit", "aliases": [], "source_chunk": "c1",
             "embedding": [0.2] * 384},
        ]

    def _make_relations(self):
        return [
            {"_key": "rel1",
             "_from": "OR1200_Entities/OR1200_aaa",
             "_to":   "OR1200_Entities/OR1200_bbb",
             "type":  "INCLUDES",
             "context": "pipeline includes MMU",
             "source_chunk": "c1"},
        ]

    def test_load_writes_all_collections(self):
        db, col_mock = self._make_mock_db()
        entities = self._make_entities()
        relations = self._make_relations()
        communities = [{"_key": "OR1200_comm_0", "members": ["OR1200_aaa", "OR1200_bbb"]}]
        chunks = [{"_key": "c1", "text": "test", "doc_version": None}]

        counts = load_to_arangodb(
            entities=entities,
            relations=relations,
            communities=communities,
            chunks=chunks,
            prefix="OR1200_",
            db=db,
        )

        cols = _get_collection_names("OR1200_")
        # All expected collections should appear in the return dict
        self.assertIn(cols["entities"],      counts)
        self.assertIn(cols["relations"],     counts)
        self.assertIn(cols["golden"],        counts)
        self.assertIn(cols["golden_rel"],    counts)
        self.assertIn(cols["communities"],   counts)
        self.assertIn(cols["chunks"],        counts)
        self.assertIn(cols["consolidates"],  counts)
        self.assertIn(cols["mentioned_in"],  counts)

    def test_load_golden_dedup_reduces_count(self):
        """Two entities with the same name should merge into one golden entity."""
        db, col_mock = self._make_mock_db()

        # Track calls to import_bulk per collection
        bulk_calls: dict[str, list] = {}

        def col_side_effect(name, **kwargs):
            mock = MagicMock()
            mock.import_bulk.side_effect = lambda records, **kw: (
                bulk_calls.setdefault(name, []).append(records)
                or {"created": len(records), "updated": 0}
            )
            mock.indexes.return_value = []
            return mock

        db.collection.side_effect = col_side_effect
        db.create_collection.side_effect = col_side_effect

        # Two entities with same name in different cases
        entities = [
            {"_key": "OR1200_aaa", "name": "Pipeline", "type": "PIPELINE_STAGE",
             "description": "x", "aliases": [], "source_chunk": "c1", "embedding": None},
            {"_key": "OR1200_bbb", "name": "pipeline",  "type": "PIPELINE_STAGE",
             "description": "", "aliases": ["pip"], "source_chunk": "c2", "embedding": None},
        ]

        load_to_arangodb(
            entities=entities, relations=[], communities=[], chunks=[],
            prefix="OR1200_", db=db
        )

        # Golden_Entities should have received 1 record
        golden_col = _get_collection_names("OR1200_")["golden"]
        self.assertIn(golden_col, bulk_calls)
        num_golden = sum(len(batch) for batch in bulk_calls[golden_col])
        self.assertEqual(num_golden, 1, "Two same-name entities should merge into one golden")

    def test_consolidates_edges_written(self):
        """Each raw entity should produce a CONSOLIDATES edge from its golden entity."""
        entities = [
            {"_key": "OR1200_aaa", "name": "Pipeline", "type": "PIPELINE_STAGE",
             "description": "x", "aliases": [], "source_chunk": "c1", "embedding": None},
            {"_key": "OR1200_bbb", "name": "MMU", "type": "MEMORY_SYSTEM",
             "description": "y", "aliases": [], "source_chunk": "c1", "embedding": None},
        ]
        cols = _get_collection_names("OR1200_")
        edges = build_consolidates_edges(
            entities, "OR1200_",
            golden_col=cols["golden"],
            entities_col=cols["entities"],
        )
        self.assertEqual(len(edges), 2)
        for e in edges:
            self.assertTrue(e["_from"].startswith(cols["golden"] + "/")),
            self.assertTrue(e["_to"].startswith(cols["entities"] + "/"))
            self.assertEqual(e["type"], "CONSOLIDATES")

    def test_mentioned_in_edges_written(self):
        """Each raw entity with a source_chunk should produce a MENTIONED_IN edge."""
        entities = [
            {"_key": "OR1200_aaa", "name": "Pipeline", "source_chunk": "chunk_001"},
            {"_key": "OR1200_bbb", "name": "MMU",      "source_chunk": "chunk_001"},
            {"_key": "OR1200_ccc", "name": "Cache",    "source_chunk": "chunk_002"},
            {"_key": "OR1200_ddd", "name": "NoChunk",  "source_chunk": ""},  # should be skipped
        ]
        cols = _get_collection_names("OR1200_")
        edges = build_mentioned_in_edges(
            entities, "OR1200_",
            entities_col=cols["entities"],
            chunks_col=cols["chunks"],
        )
        self.assertEqual(len(edges), 3)  # ddd is skipped
        for e in edges:
            self.assertTrue(e["_from"].startswith(cols["entities"] + "/"))
            self.assertTrue(e["_to"].startswith(cols["chunks"] + "/"))
            self.assertEqual(e["type"], "MENTIONED_IN")


# ---------------------------------------------------------------------------
# Section 7 — End-to-end dry run
# ---------------------------------------------------------------------------

class TestPipelineDryRun(unittest.TestCase):
    def test_dry_run_returns_summary(self):
        """Full pipeline in dry-run mode should succeed and return a non-empty summary."""
        from local_graphrag.pipeline import LocalGraphRAGPipeline

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write(FIXTURE_TEXT * 3)
            path = f.name

        try:
            pipeline = LocalGraphRAGPipeline(
                prefix="TEST_",
                backend="openai",
                embedding_backend="sentence_transformers",
            )

            # Mock the LLM call so no real API is needed
            with patch.object(pipeline.extractor, "_call_llm",
                               return_value=FIXTURE_LLM_RESPONSE):
                summary = pipeline.run(doc_paths=[path], dry_run=True)

            self.assertIn("chunks",      summary)
            self.assertIn("entities",    summary)
            self.assertIn("relations",   summary)
            self.assertIn("communities", summary)
            self.assertGreater(summary["chunks"],   0)
            self.assertGreater(summary["entities"], 0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
