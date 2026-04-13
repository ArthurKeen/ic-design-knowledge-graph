# Hardening & Verification Guide

This document is the **customer-facing checklist** for validating that the IC Knowledge Graph project is correctly installed and functioning.

It is intentionally split into:
- **Core**: RTL + Git + semantic layer (no GraphRAG services required)
- **Optional GraphRAG**: document re-import pipeline (requires ArangoDB AMP GenAI services)

---

## Core install (recommended default)

From the repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-core.txt
```

## Full install (includes GraphRAG/document processing)

```bash
pip install -r requirements.txt
```

---

## Unit tests (fast, offline)

Run all unit tests (GraphRAG integration tests are skipped by default):

```bash
pytest tests/ --ignore=tests/test_graphrag_integration.py -v
```

Expected result: **PASS** with no network calls required.

To run integration tests explicitly (requires live services):

```bash
pytest -m integration --run-integration -v
```

---

## Core smoke test (fast validation of connectivity)

The smoke test verifies that:
- Python can import the project modules
- ArangoDB is reachable with the configured credentials
- The core collections exist

Run:

```bash
python scripts/smoke_test.py
```

If you want stricter checks:

```bash
# Fail if expected graph is missing
python scripts/smoke_test.py --require-graph

# Also require non-empty collections (post-ETL)
python scripts/smoke_test.py --require-nonempty

# Also check GraphRAG collections exist (does not run GraphRAG services)
python scripts/smoke_test.py --check-graphrag
```

---

## End-to-end core pipeline (build the KG)

The primary path builds the full multi-repo temporal knowledge graph:

```bash
./scripts/rebuild_database.sh
```

This runs RTL extraction for all four repos (OR1200, IBEX, MOR1KX, Marocchino), semantic bridging, cross-repo bridging, temporal graph creation, theme install, and demo query install.

After completion:
- Database: `ic-knowledge-graph-temporal`
- Graph: `IC_Temporal_Knowledge_Graph`
- Collections include `RTL_Module`, `RTL_Port`, `RTL_Signal`, `GitCommit`, `Author`, `RESOLVED_TO`, `CROSS_REPO_SIMILAR_TO`, etc.

<details>
<summary>Legacy alternative (single-repo OR1200 only)</summary>

```bash
python scripts/master_etl.py
python src/create_graph.py
```

</details>

---

## Optional: GraphRAG re-import pipeline

The GraphRAG re-import pipeline is **optional** and requires:
- ArangoDB AMP (cloud) with **GenAI services enabled**
- Proper `SERVER_URL` (AMP instance URL)
- Valid LLM API keys (for embeddings + extraction)

See `GRAPHRAG_STATUS.md` for:
- Current status
- Troubleshooting
- Exact commands and diagnostic tooling

