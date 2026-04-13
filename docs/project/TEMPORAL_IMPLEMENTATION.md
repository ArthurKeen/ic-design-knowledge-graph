# Temporal IC Knowledge Graph — Implementation Reference

**Branch:** `main` (merged from `feature/temporal-kg`)  
**Database:** `ic-knowledge-graph-temporal`  
**Last Updated:** 2026-03-10

This document is the authoritative implementation reference for the temporal knowledge graph extension. It combines the original implementation plan and technical specification into a single living document.

See also:
- [PRD.md](PRD.md) — Goals, user stories, and success criteria
- [SCHEMA.md](SCHEMA.md) — Full schema reference including §8 Temporal Extension

---

## 1. Architecture Overview

```
Git Repositories (4 repos, 3,805 total commits)
         │
         ▼
[etl_temporal_git.py]          ← replay commit-by-commit, diff RTL
         │
         ├─[etl_epoch_detector.py]  ← assign each commit to named epoch
         │
         ▼
temporal_nodes.jsonl / temporal_edges.jsonl
         │
         ▼
[load_temporal_data.py]        ← upsert to ArangoDB, create VCI+MDI indexes
         │
         ▼
ic-knowledge-graph-temporal
  ├── GitCommit (3,808)
  ├── RTL_Module (6,594, with valid_from/to_ts)
  ├── DesignEpoch (385)
  ├── DesignSituation (722)
  ├── MODIFIED edges (6,594, with VCI indexes)
  ├── BELONGS_TO_EPOCH edges (6,794)
  └── CROSS_REPO_SIMILAR_TO edges (61)
         │
         ├─[situation_detector.py]  ← auto-generate DesignSituation nodes
         └─[cross_repo_bridge.py]   ← CROSS_REPO_SIMILAR_TO edges
```

---

## 2. Phase Completion Status

| Phase | Description | Status |
|---|---|---|
| **Phase 1** | Temporal ETL for OR1200 | ✅ Complete |
| **Phase 2** | Local GraphRAG Pipeline | ✅ Built (`src/local_graphrag/`) |
| **Phase 3** | Multi-Repo Ingestor (4 repos) | ✅ Complete |
| **Phase 4** | Cross-Repo Bridges & Déjà Vu Engine | ✅ Structural bridges live |
| **Phase 5** | Agentic Swarm / Blackboard | 📋 Defined, not implemented |

---

## 3. Phase 1 — Temporal ETL

### Key Files

| File | Purpose |
|---|---|
| `src/config_temporal.py` | Temporal constants, repo registry, epoch thresholds |
| `src/etl_temporal_git.py` | Git replay: `replay_git_history()` |
| `src/etl_epoch_detector.py` | Epoch assignment: `detect_epochs()` |
| `scripts/temporal/load_temporal_data.py` | ArangoDB upsert + index creation |

### Epoch Detection Rules (priority order)

1. **`initial_commit`** — first commit in repo
2. **`milestone_<tag>`** — git release tag present on this commit
3. **`period_<YYYY_MM>`** — `EPOCH_WINDOW_DAYS` (default 180) elapsed since last epoch boundary
4. **`major_refactor_<sha7>`** — `MAJOR_REFACTOR_THRESHOLD` (default 15%) of RTL files changed
5. **inherit** — carry previous commit's epoch forward

### Edge Interval Propagation

Every edge written by the ETL mirrors `valid_from_ts` / `valid_to_ts` from its `_to` vertex:

```python
# make_modified_edge() — edge carries target module's valid interval
{
    "_key":           edge_key,
    "_from":          f"GitCommit/{commit_sha}",
    "_to":            f"RTL_Module/{module_key}",
    "valid_from_ts":  target_valid_from_ts,   # mirrored from _to vertex
    "valid_to_ts":    target_valid_to_ts,
    ...
}
```

This enables ArangoDB vertex-centric persistent indexes (VCI) to prune edge traversals before loading the neighboring vertex.

### Config Knobs (`config_temporal.py`)

| Variable | Default | Description |
|---|---|---|
| `MAJOR_REFACTOR_THRESHOLD` | `0.15` | Fraction of RTL files changed to trigger refactor epoch |
| `EPOCH_WINDOW_DAYS` | `180` | Days between auto-generated `period_YYYY_MM` epochs |
| `TEMPORAL_REPLAY_ENABLED` | `true` | Whether to replay full git history |
| `CROSS_REPO_MIN_SIMILARITY` | `0.70` | Minimum score for CROSS_REPO_SIMILAR_TO edges |

---

## 4. Phase 2 — Local GraphRAG Pipeline

Replaces the AMP-dependent `etl_graphrag.py` / `graphrag_client.py`.

### Directory Structure

```
src/local_graphrag/
├── __init__.py
├── chunker.py            # Version-aware chunker; adds temporal metadata per chunk
├── extractor.py          # Entity/relation extractor — OpenAI or Ollama backend
├── community_detector.py # Leiden community detection (python-igraph)
├── loader.py             # ArangoDB loader: PREFIX_Entities, PREFIX_Chunks, etc.
└── pipeline.py           # Orchestrator: chunker → extractor → community → loader
```

### Why Not AMP

| Issue | Detail |
|---|---|
| Service ID parsing bug | Fragile `split("-")[-1]` extraction |
| Startup timing | 15–30s blind wait; 404s during startup |
| Cost | $1–5 per PDF; prevents rapid iteration |
| Connectivity | Cannot run offline or in restricted environments |

### Why Not Daniel Morris lite-graphRAG (`docs/reference/lite-graphRAG.py`)

Reviewed (1834 lines). It is a **LightRAG storage backend plugin** — requires `from ..base import BaseGraphStorage`, has no chunker/extractor/LLM prompt engine/community detector, uses incompatible collection schema (`{ns}_nodes`, `{ns}_edges`, `{ns}_kv_store`), and has no IC entity type filtering or temporal metadata. **Decision: do not use.**

### Usage

```bash
python -m local_graphrag.pipeline \
  --doc-dir ./or1200/doc \
  --prefix OR1200_ \
  --backend ollama       # or: --backend openai
```

---

## 5. Phase 3 — Multi-Repo Ingestor

### Key Files

| File | Purpose |
|---|---|
| `scripts/multi_repo/repo_registry.yaml` | Config: repos with metadata |
| `scripts/multi_repo/ingest_repo.py` | Main driver: clone → ETL → load |
| `scripts/multi_repo/run_all_repos.sh` | Shell orchestrator for all repos |

### Ingested Repos (2026-03-10)

| Repo | Local Path | Commits | Epochs | Situations |
|---|---|---|---|---|
| `openrisc/or1200` | `or1200/` | 10 | 5 | 2 |
| `openrisc/mor1kx` | `data/repos/mor1kx/` | 819 | 100 | 179 |
| `openrisc/or1k_marocchino` | `data/repos/marocchino/` | 68 | 12 | 20 |
| `lowRISC/ibex` | `data/repos/ibex/` | 2,908 | 268 | 521 |

### Known Issues Fixed

| Bug | Fix | File |
|---|---|---|
| `.env` special chars (`$GTEaYL`) interpreted by shell | Replaced `source .env` with `while-read` loop | `run_all_repos.sh` |
| `.venv` missing `yaml`/`arango` packages | Added venv validation fallback to system python3 | `run_all_repos.sh` |
| AMP ERR 4: `CONTAINS()` + MDI index | Fetch all, filter in Python | `cross_repo_bridge.py` |

---

## 6. Phase 4 — Cross-Repo Bridges & Situation Detector

### Structural Bridge (`src/cross_repo_bridge.py`)

Compares RTL modules across repos using **label-suffix + file_hash matching**:

- `_label_suffix("or1200_cpu")` → `"cpu"` (strip repo prefix)
- Exact suffix match → score = 1.0
- Token Jaccard on full label → partial score
- Exact `file_hash` match → score = 1.0 (definitive copy/port)

> **Why not port-signature matching?** `HAS_PORT` edges are not populated by the git-replay ETL (which doesn't parse Verilog port declarations). Port-based matching is a future enhancement requiring a Verilog port extractor.

### Situation Detector (`src/situation_detector.py`)

Three heuristics, all using **pre-fetched data** (O(1) AQL queries per repo):

| Heuristic | Trigger | Situation Class |
|---|---|---|
| New module introduced | `m.valid_from_commit == sha` (bulk pre-fetched) | `subsystem_addition` |
| Epoch starts with `milestone_*` | epoch label | `release_prep` |
| Epoch starts with `major_refactor_*` | epoch label | `major_refactor` |

> **Performance note:** The original implementation did one AQL query per commit (`O(n_commits)` DB round-trips). The fix pre-fetches all new module introductions for the repo in **one** AQL query, grouped in Python. For ibex (2,908 commits), this reduced runtime from 3+ hours to ~10 seconds.

### Cross-Repo Bridge Results

| Pair | CROSS_REPO_SIMILAR_TO edges |
|---|---|
| OR1200 ↔ MOR1KX | 6 |
| OR1200 ↔ MAROCCHINO | 4 |
| OR1200 ↔ IBEX | 4 |
| MOR1KX ↔ MAROCCHINO | 1 |
| MOR1KX ↔ IBEX | 2 |
| **Total** | **61** |

---

## 7. Canonical AQL Query Patterns

> [!IMPORTANT]
> Always include `WITH <CollectionName>` as the **first line** of any AQL traversal query in ArangoDB cluster mode. Omitting it causes `ERR 1521: collection not known to traversal`.

### State-as-of-timestamp

```aql
FOR m IN RTL_Module
  FILTER m.repo == "openrisc/or1200.git"
  FILTER m.valid_from_ts <= @target_ts
  FILTER m.valid_to_ts > @target_ts
  RETURN m
```

### Modules changed in an epoch

```aql
FOR m IN RTL_Module
  FILTER m.repo == @repo
  FILTER m.design_epoch == @epoch
  SORT m.valid_from_ts ASC
  RETURN {label: m.label, introduced: m.valid_from_ts, file: m.file}
```

### Who modified a module and when (temporal author trace)

```aql
WITH GitCommit, Author
FOR v, e IN 1..1 INBOUND @module_id MODIFIED
  LET commit = DOCUMENT(v._id)
  LET author = FIRST(
    FOR a IN 1..1 INBOUND commit AUTHORED RETURN a
  )
  SORT e.valid_from_ts ASC
  RETURN {commit: commit.metadata.message, author: author.name, ts: e.valid_from_ts}
```

### Cross-repo structural analogs

```aql
WITH RTL_Module
FOR v, e IN 1..1 OUTBOUND @module_id CROSS_REPO_SIMILAR_TO
  FILTER e.similarity_score >= 0.7
  RETURN {
    module:  v.label,
    repo:    v.repo,
    score:   e.similarity_score,
    type:    e.similarity_type
  }
```

### Find design situations in a repo

```aql
FOR s IN DesignSituation
  FILTER s.repo == @repo
  SORT s.valid_from_ts ASC
  RETURN {
    class:  s.situation_class,
    epoch:  s.epoch,
    tags:   s.tags,
    from:   s.valid_from_ts
  }
```

---

## 8. ArangoDB Index Reference

Created by `scripts/temporal/load_temporal_data.py` (idempotent, uses `[EXISTS]` check):

```
Vertex-Centric Persistent (VCI) indexes on edge collections:
  MODIFIED          → [_from, valid_from_ts]  (idx_modified_from_vci)
  MODIFIED          → [_to, valid_to_ts]       (idx_modified_to_vci)
  BELONGS_TO_EPOCH  → [_from, valid_from_ts]  (idx_epoch_from_vci)
  BELONGS_TO_EPOCH  → [_to, valid_to_ts]       (idx_epoch_to_vci)
  CROSS_REPO_*      → [_from, valid_from_ts]  (idx_similar_from_vci)
  CROSS_REPO_*      → [_from, valid_from_ts]  (idx_evolved_from_vci)

MDI-prefixed indexes on vertex collections:
  RTL_Module       → [valid_from_ts, valid_to_ts]  (idx_rtl_module_mdi)
  GitCommit        → [valid_from_ts, valid_to_ts]  (idx_gitcommit_mdi)
  DesignSituation  → [valid_from_ts, valid_to_ts]  (idx_situation_mdi)
```

---

## 9. Phase 5 — Agentic Swarm (Optional, Not Implemented)

A blackboard architecture where specialist agents cooperate over the temporal graph.

### Agent Roles

| Agent | Trigger | Output |
|---|---|---|
| `CommitWatcherAgent` | New commit in watched repo | Triggers ETL; writes `GitCommit` node |
| `PatternMatcherAgent` | New `DesignSituation` detected | `DesignAlert` node with matching situation |
| `DocDriftAgent` | RTL modified; spec embedding distance > threshold | `DesignAlert` (drift detected) |
| `CrossRepoBridgeAgent` | New repo ingested | New `CROSS_REPO_SIMILAR_TO` edges |
| `AlertPublisherAgent` | `DesignAlert` written | Stdout/webhook/notification |

### New Collections (Phase 5 Only)

| Collection | Type | Description |
|---|---|---|
| `DesignAlert` | Vertex | Alert from an agent |
| `AgentRun` | Vertex | Audit log of agent invocations |
| `WatchedRepo` | Vertex | Repos under active monitoring |

### Technology Recommendation

Start with `asyncio` task loop (zero new dependencies). Migrate to LangGraph multi-agent if multi-LLM coordination is needed.

---

## 10. Next Steps

1. **Run local GraphRAG on doc directories** (`src/local_graphrag/`) to populate `{PREFIX}Entities` / `{PREFIX}Communities` and enable `CROSS_REPO_EVOLVED_FROM` lineage edges
2. **Lower `CROSS_REPO_MIN_SIMILARITY`** from 0.70 to test broader bridge coverage, especially for ibex ↔ marocchino (currently 0 edges)
3. **Port extractor from Verilog** — parse module port declarations during ETL to enable port-signature structural bridges (replaces label-suffix heuristic)
4. ~~Merge `feature/temporal-kg` → `main`~~ (completed)
5. **Phase 5** — implement agentic swarm if continuous monitoring is required
