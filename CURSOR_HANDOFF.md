# IC Knowledge Graph — Cursor Handoff Notes
_Branch: `feature/temporal-kg` — Last updated: 2026-03-18 (Session 3)_

---

## What Was Just Completed (Session 3)

### P1 — E2E Docker Test Infrastructure ✅
Created `tests/conftest.py` (dynamic Docker ArangoDB provisioning, free-port selection, health
check that accepts HTTP 401) and `tests/test_e2e_local.py` (9 smoke tests covering RTL extraction
and semantic bridging against a throwaway local container). Tests skip gracefully if Docker/repo
clones are absent. Run with:
```bash
PYTHONPATH=src pytest tests/test_e2e_local.py -v -s
```

### P2 — GraphRAG Re-Ingestion with `doc_version` Temporal Tagging ✅
`scripts/multi_repo/ingest_repo.py` now accepts `--doc-version`. All 1,006 golden entities can
be stamped with a temporal version tag on next ingestion:
```bash
python3 scripts/multi_repo/ingest_repo.py --no-clone --no-temporal --no-rtl --doc-version 2026-03-18
```

### P3 — GraphRAG Retrieval Query Layer ✅
`src/graph_retriever.py` — 5-step retrieval pipeline:
1. Embed question → vector anchor search in Golden Entities (all 4 repos)
2. Expand via `RESOLVED_TO` traversal
3. Expand via `CROSS_REPO_SIMILAR_TO`
4. Pull community peers + `MentionedIn` chunks
5. Assemble context → LLM (OpenAI `gpt-4o-mini` → Anthropic `claude-3-5-haiku` → no-op fallback)

MPS (Apple Silicon) aware. CLI:
```bash
PYTHONPATH=src python3 src/graph_retriever.py "How does the OR1200 handle cache misses?" [--explain] [--no-llm]
```

### P4 — ArangoDB Visualizer Saved Queries ✅
`scripts/setup/install_graphrag_queries.py` — installs 6 saved AQL queries and 6 canvas actions
into `_editor_saved_queries` and `_canvasActions` for the `IC_Temporal_Knowledge_Graph` viewpoint.

### P5 — OR1200 + IBEX Alias Curation ✅
- `src/ibex_acronyms.json` — **NEW** — 57 RISC-V/IBEX-specific acronyms (`csr`, `pmp`, `hart`,
  `mtvec`, `mepc`, `tlul`, `multdiv`, `priv`, …)
- `src/rtl_semantic_aliases.json` — extended with `OR1200_` (8 golden entities, port-name aliases)
  and `IBEX_` (15 golden entities, RISC-V signal aliases) sections

### ER Library Contribution Plan ✅
`docs/ER_LIBRARY_CONTRIBUTION_PLAN.md` — detailed plan for porting proven ER techniques to
`arango-entity-resolution`. Revised 2026-03-18 to close three IC-specific hardwiring gaps:
- `RTL_RELEVANT_TYPES` → `target_filter` param on `resolve_entity_cross_collection`
- `SKIP_NAMES` → `source_skip_values` param
- Wishbone/clk `if` blocks in `_embedding_gate()` → `token_type_affinity` param (new A4b section)

### MCP Server Rule ✅
`.cursor/rules/mcp-servers.mdc` — pins the two correct MCP servers for this project
(always applied, prevents cross-project confusion).

---

## Final Frozen RESOLVED_TO Table

Built with precision-first policy: alias-aware exact match first, gated embeddings.
Default threshold `0.72`; MAROCCHINO run at `0.70`.

| Repo | Exact | Embedding | Total |
|---|---:|---:|---:|
| OR1200 | 101 | 8 | **109** |
| MOR1KX | 0 | 42 | **42** |
| MAROCCHINO | 12 | 0 | **12** |
| IBEX | 32 | 24 | **56** |
| **TOTAL** | **145** | **74** | **219** |

Cross-repo: 53 `CROSS_REPO_SIMILAR_TO`, 1 `CROSS_REPO_EVOLVED_FROM`.

---

## Next Task: Port ER Capabilities to `arango-entity-resolution`

The full plan is at `docs/ER_LIBRARY_CONTRIBUTION_PLAN.md`. Sequencing (C1 first):

```
C1: A1 — cross-collection resolve_entity_cross_collection()  ← START HERE
      includes target_filter, source_skip_values (closes RTL_RELEVANT_TYPES / SKIP_NAMES gaps)
C2: A2 — multi_stage pipeline strategy
C3: A3 + A4 + A4b — score-margin gate, token-overlap gate, token_type_affinity gate
      A4b closes the Wishbone/clk hardwiring gap
C4: A5 — explain_match gate failure reasons
C5: A6 — alias/synonym expansion
C6: A7 — token_jaccard similarity type
```

After C1+C2+C3: refactor `src/rtl_semantic_bridge.py` (B1 in plan — shrinks from ~620 → ~120 lines).
After C6: refactor `src/cross_repo_bridge.py` (B2 in plan).

### Setup for ER library development

The library is at `/Users/arthurkeen/code/arango-entity-resolution/`. It is currently
installed as a static package in this venv. For live development across both repos, install
as editable from this project:

```bash
pip install -e /Users/arthurkeen/code/arango-entity-resolution
```

### ER library structure

```
src/entity_resolution/
  strategies/          ← BlockingStrategy subclasses (exact, bm25, vector, hybrid…)
  similarity/          ← weighted_field_similarity, ann_adapter
  core/                ← IncrementalResolver
  etl/                 ← CanonicalResolver
  enrichments/         ← HierarchicalContextResolver
  mcp/server.py        ← find_duplicates() and resolve_entity() MCP tool entry points
  cli.py
```

### What to add for C1 (first PR to ER library)

New function in `src/entity_resolution/core/` (or a new `cross_collection.py`):

```python
def resolve_entity_cross_collection(
    source_collection:   str,
    target_collection:   str,
    source_text_field:   str | list,     # field name or fallback list
    target_text_fields:  list[str],
    confidence_threshold: float = 0.80,
    top_k:               int = 1,
    field_mapping:       dict = None,
    target_filter:       dict = None,    # {"field": "type", "values": [...]}
    source_skip_values:  set  = None,    # {"clk", "rst", "a", "b", ...}
) -> list[dict]
```

Reference implementation to strip IC-specific logic from:
`src/rtl_semantic_bridge.py` — particularly `load_golden_entities()`, `load_rtl_nodes()`,
`match_exact()`, `match_embedding()`, `_embedding_gate()`.

### IC-specific constructs to NOT port verbatim (generalise instead)

| IC construct | File | Generalised as |
|---|---|---|
| `RTL_RELEVANT_TYPES` set | `rtl_semantic_bridge.py:48` | `target_filter` param |
| `SKIP_NAMES` set | `rtl_semantic_bridge.py:62` | `source_skip_values` param |
| `if rtl_has_wishbone …` block | `rtl_semantic_bridge.py:352` | `token_type_affinity` param (A4b) |
| `if rtl_has_clk_rst …` block | `rtl_semantic_bridge.py:360` | `token_type_affinity` param (A4b) |
| `WORD_INDEX_STOPWORDS` | `rtl_semantic_bridge.py:71` | `word_index_stopwords` param (A4) |
| `_load_alias_overrides()` | `rtl_semantic_bridge.py:144` | `alias_sources` param (A6) |

---

## MCP Servers for This Project

Pinned in `.cursor/rules/mcp-servers.mdc` (alwaysApply: true):

| Purpose | Server |
|---|---|
| ArangoDB (AQL, graph, collections) | `user-arangodb-ic-knowledge-graph-mcp` |
| Entity resolution | `user-ic-knowledge-graph-arango-entity-resolution-mcp` |

---

## Files Changed (Session 3)

| File | What Changed |
|---|---|
| `tests/conftest.py` | **NEW** — Docker ArangoDB fixture: free port, health check (accepts 401), teardown |
| `tests/test_e2e_local.py` | **NEW** — 9 E2E smoke tests (RTL extraction + semantic bridge) |
| `src/graph_retriever.py` | **NEW** — GraphRAG retrieval pipeline (embed → traverse → LLM) |
| `scripts/setup/install_graphrag_queries.py` | **NEW** — installs 6 saved AQL queries + 6 canvas actions |
| `src/ibex_acronyms.json` | **NEW** — 57 RISC-V/IBEX acronyms |
| `src/rtl_semantic_aliases.json` | Extended with `OR1200_` and `IBEX_` sections |
| `docs/ER_LIBRARY_CONTRIBUTION_PLAN.md` | **NEW** — full ER library contribution plan (A1–A7, gap-fixed) |
| `.cursor/rules/mcp-servers.mdc` | **NEW** — MCP server pin rule |
| `scripts/multi_repo/ingest_repo.py` | `--doc-version` CLI arg; `ingest_all()` accepts `doc_version` param |
| `scripts/temporal/create_temporal_graph.py` | 28 edge definitions; RTL_* collections in orphan list |
| `src/cross_repo_bridge.py` | `_port_signature_similarity()` — Jaccard + size bonus |
| `src/local_graphrag/community_detector.py` | `python-igraph` installed; Leiden now active |
| `src/mor1kx_acronyms.json` | **NEW** — 34 MOR1KX-specific acronyms |

---

## Key Architecture Decisions (do not reverse)

1. **Shared RTL collections** (`RTL_Port`, `RTL_Signal`, etc.) — `repo` field discriminates.
2. **LPG schema on edges** — every edge has `fromNodeType + toNodeType + labels:[...]`.
3. **Golden entity `labels` list** — `["GoldenEntity", "REGISTER", "OR1200"]` — enables type-scan-free AQL filters.
4. **`RESOLVED_TO` is shared** — per-repo scoped by `repo` field on each edge.
5. **MAROCCHINO threshold stays at `0.70`** — `0.65` was investigated and explicitly rejected.
6. **`--min-score 0.65` is a known landmine** — do not apply globally. Expand coverage via alias file.
7. **ER library contributions must be domain-agnostic** — do not port `RTL_RELEVANT_TYPES`,
   `SKIP_NAMES`, Wishbone/clk checks verbatim. Use the generalised parameters in the plan.

---

## Running the Stack

```bash
source .venv/bin/activate
export PYTHONPATH=src

pytest tests/ -v                                           # all tests (no network required)
python3 src/rtl_semantic_bridge.py --all --truncate        # rebuild RESOLVED_TO
python3 src/cross_repo_bridge.py --all                     # rebuild cross-repo edges
python3 scripts/temporal/create_temporal_graph.py          # rebuild named graph + indexes
python3 src/graph_retriever.py "question" --explain        # test retrieval layer
```

---

## DB Connection
Values in `.env`:
```
ARANGO_ENDPOINT=https://5ieeavs2.rnd.pilot.arango.ai
ARANGO_DATABASE=ic-knowledge-graph-temporal
```

Named graph: `IC_Temporal_Knowledge_Graph` — 28 edge definitions.
