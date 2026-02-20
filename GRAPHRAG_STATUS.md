# GraphRAG Integration Status

## Summary

The GraphRAG document import pipeline is **implemented but not fully validated** end-to-end. The GraphRAG data (entities, relations, communities) was populated into the demo ArangoDB instance during initial development. The Python re-import pipeline was built and tested in isolation but encountered issues when run against the live ArangoDB AMP GenAI API under deadline pressure.

The core knowledge graph demo — RTL parsing, Git ingestion, semantic bridging — **works fully** and does not require running the GraphRAG import pipeline.

---

## What GraphRAG Does in This Project

The GraphRAG pipeline processes OR1200 PDF documentation through three stages:

1. **Document Conversion** (`src/document_converter.py`): PDFs are converted to Markdown using `pymupdf4llm` (fast) or `docling` (high accuracy).
2. **Entity Extraction** (`src/etl_graphrag.py`): Markdown chunks are submitted to the ArangoDB AMP GenAI Importer service, which uses an LLM to extract hardware-specific entities (18 custom types: `PROCESSOR_COMPONENT`, `REGISTER`, `INSTRUCTION`, etc.) and their relationships.
3. **Consolidation & Bridging** (`src/consolidator.py`, `src/bridger.py`): Raw entities are deduplicated into `OR1200_Golden_Entities` and linked to RTL code elements via `RESOLVED_TO` edges.

The collections created by this pipeline are:

| Collection | Type | Description |
|---|---|---|
| `OR1200_Documents` | Vertex | Source PDF metadata |
| `OR1200_Chunks` | Vertex | Text chunks (~1200 tokens each) |
| `OR1200_Entities` | Vertex | Raw LLM-extracted entities |
| `OR1200_Golden_Entities` | Vertex | Consolidated canonical entities |
| `OR1200_Relations` | Edge | Raw entity relationships |
| `OR1200_Golden_Relations` | Edge | Consolidated relationships |
| `OR1200_Communities` | Vertex | Entity clusters (Leiden algorithm) |

---

## Current State

- **Collections in demo database**: Populated (entities and relations are present).
- **Re-import pipeline** (`src/etl_graphrag.py`): Implemented, not validated end-to-end.
- **Consolidation** (`src/consolidator.py`): Works correctly; tested independently.
- **Semantic bridging** (`src/bridger.py`): Works correctly against existing `OR1200_Golden_Entities`.
- **Diagnostic tool** (`scripts/diagnose_graphrag.py`): Functional — use this first when troubleshooting.

---

## Known Issues and Likely Root Causes

### 1. Service ID Parsing (Most Likely Cause)

In `src/graphrag_client.py`, the `start_service()` method extracts the service ID from the API response using a fragile heuristic:

```python
# In graphrag_client.py, start_service()
service_id = full_service_id.split("-")[-1] if full_service_id else None
```

If the API returns a full ID like `arangodb-graphrag-importer-abc123`, this correctly extracts `abc123`. However, if the API returns a UUID-style ID like `abc1-2345-6789`, only `6789` is captured — breaking all subsequent API calls. **This has been fixed** (see the `start_service()` method — it now logs the raw response for debugging).

### 2. ArangoDB AMP GenAI API Requirements

The GraphRAG services require:
- An **ArangoDB AMP** (cloud) instance, not a self-hosted or Docker instance
- The **GenAI services** feature enabled on the account
- A valid `SERVER_URL` pointing to the AMP instance (same as `ARANGO_ENDPOINT`)
- A valid `OPENAI_API_KEY` for the LLM and embedding calls

The `env.template` / `.env` variable `SERVER_URL` must match the AMP endpoint exactly. Setting `ARANGO_MODE=REMOTE` alone is not sufficient.

### 3. Service Startup Timing

The Importer and Retriever services take time to initialize (~15–30 seconds). The pipeline includes a 15-second wait, but the actual startup time varies. If you see 404 errors immediately after service start, wait and retry — the `query_graphrag()` method already includes retry logic for this.

---

## How to Attempt a Fresh Import

### Prerequisites

1. ArangoDB AMP instance with GenAI services enabled
2. Valid API keys (`OPENAI_API_KEY`)
3. OR1200 PDF documents in `or1200/doc/` (populated via git submodule)

### Step 1: Configure `.env`

```bash
ARANGO_MODE=REMOTE
ARANGO_ENDPOINT=https://your-instance.arango.ai
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password
ARANGO_DATABASE=ic-knowledge-graph
SERVER_URL=https://your-instance.arango.ai
OPENAI_API_KEY=your_openai_api_key
GRAPHRAG_PROJECT_NAME=OR1200
```

### Step 2: Run the diagnostic tool first

```bash
# Start an importer service manually in the ArangoDB AMP UI first,
# then pass its service ID here to test document import:
python scripts/diagnose_graphrag.py <importer_service_id>
```

This script will:
- Verify configuration and connectivity
- Convert PDFs to Markdown
- Import one document at a time with detailed logging
- Monitor collections for 5 minutes and report what was written

### Step 3: Run the full pipeline (if diagnostics succeed)

```bash
# Check existing state
python src/etl_graphrag.py --check-collections --list-services

# Full import (clears existing collections and reimports)
python src/etl_graphrag.py --import --force-reimport

# Test queries against the retriever
python src/etl_graphrag.py --test --retriever-id <id>
```

### Step 4: Run consolidation and bridging

After import completes:

```bash
python src/consolidator.py
python src/bridger_bulk.py
```

---

## Files Involved

| File | Purpose |
|---|---|
| `src/etl_graphrag.py` | Main orchestrator — start services, import docs, test queries |
| `src/graphrag_client.py` | REST client for ArangoDB GenAI API (auth, service lifecycle, import, query) |
| `src/document_converter.py` | PDF → Markdown conversion (pymupdf or docling) |
| `src/consolidator.py` | Deduplicates raw entities into Golden Entities |
| `src/bridger.py` / `src/bridger_bulk.py` | Links Golden Entities to RTL elements |
| `src/config.py` | Configuration constants (entity types, collection names, API settings) |
| `scripts/diagnose_graphrag.py` | Diagnostic tool — use this first when troubleshooting |
| `docs/reference/graphrag-orchestration.md` | Full orchestration reference guide |
| `docs/reference/arangographrag-integration.md` | Integration architecture details |
