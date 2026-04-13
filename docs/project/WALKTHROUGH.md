# Project Walkthrough: Integrated Circuit (IC) Design Knowledge Graph

This report documents the current state of the **Integrated Circuit (IC) Design Knowledge Graph** project, encompassing multi-repo temporal RTL data, commit-by-commit design history, and high-precision documentation bridges across four open-source RISC processors.

## 1. Multi-Repo Temporal RTL Ingestion

The ETL pipeline ingests Verilog source code from four processor repositories and transforms it into a fine-grained temporal graph representation, tracking design evolution commit-by-commit.

### Ingested Repositories

| Repo | Architecture | Commits | Epochs | Situations |
|---|---|---|---|---|
| `openrisc/or1200` | OpenRISC 1000 (primary) | 10 | 5 | 2 |
| `openrisc/mor1kx` | OpenRISC 1000 successor | 819 | 100 | 179 |
| `openrisc/or1k_marocchino` | OpenRISC OOO w/ 64-bit FPU | 68 | 12 | 20 |
| `lowRISC/ibex` | RISC-V 32 (OpenTitan core) | 2,908 | 268 | 521 |

### Aggregate Graph Statistics

- **RTL_Module**: ~6,400 temporal module versions across all repos
- **GitCommit**: ~3,800 commits
- **DesignEpoch**: 381 named design phases
- **DesignSituation**: 721 cross-referenceable structural patterns
- **RTL_Port**, **RTL_Signal**, **RTL_LogicChunk**: shared collections with per-repo data
- **RESOLVED_TO**: 193 semantic bridges (code ↔ specifications)
- **CROSS_REPO_SIMILAR_TO**: 61 structural similarity edges across repos
- **CROSS_REPO_EVOLVED_FROM**: 8 architectural lineage edges
- **SNAPSHOT_OF**: temporal snapshot edges linking module versions to commits

### Key Technical Achievements:
- **Multi-Repo Temporal Ingestion**: Processes four processor repositories commit-by-commit, assigning `valid_from`/`valid_to` epochs to every module version.
- **Design Epoch Detection**: Automatically classifies commits into named epochs (`initial_commit`, `milestone_tag`, `period_YYYY_MM`, `major_refactor`) via `etl_epoch_detector.py`.
- **Design Situation Index**: Auto-generates `DesignSituation` nodes (subsystem additions, major refactors, release preps) for cross-repo Déjà Vu detection.
- **Cross-Repo Structural Bridging**: Computes `CROSS_REPO_SIMILAR_TO` (structural similarity ≥ 0.7) and `CROSS_REPO_EVOLVED_FROM` (architectural lineage) edges across repositories.
- **Pin-to-Pin Connectivity**: Extracts structural wiring across module boundaries while filtering high-fanout nets (CLK, RST).
- **Granular Behavioral Modeling**: Decomposes `always` blocks and `assign` statements into logical units with cross-domain crossing (CDC) detection.
- **Context-Aware Entity Resolution**: Uses parent module summaries and header comments to disambiguate signals (e.g., linking `esr` to "Exception Status Register").

## 2. Advanced Semantic Architecture
We have implemented a hierarchical consolidation layer to address GraphRAG fragmentation.

### Canonical Golden Entity Layer
- **Golden Entities**: Per-repo canonical nodes representing unified concepts (Configuration, Architecture, Registers). Collections use per-repo prefixes: `OR1200_`, `IBEX_`, `MOR1KX_`, `MAROCCHINO_`.
- **Consolidation**: Unified raw document fragments using a high-performance strictly lexical AQL-based strategy.
- **Relationship Sweeping**: Remapped relations from original fragments to Golden Entities, preserving full **Provenance Breadcrumbs** for auditability.

### Type-Safe Resolution
- **Structural Constraints**: Implemented a type-compatibility matrix that prevents architectural "role" mismatches (e.g., preventing an RTL Signal from linking to a Documentation Instruction).
- **High-Precision Scoring**: Combines lexical similarity, parent context overlap, and role-based weighting to achieve a high-confidence semantic bridge.

### 3. Knowledge Graph Metrics (March 2026)

| Metric | Count | Notes |
| :--- | :--- | :--- |
| **Processors Ingested** | 4 | OR1200, IBEX, MOR1KX, Marocchino |
| **RTL Module Versions** | ~6,400 | Temporal versions across all repos |
| **Git Commits** | ~3,800 | Full commit history per repo |
| **Design Epochs** | 381 | Named phases (milestones, refactors, periods) |
| **Design Situations** | 721 | Auto-detected structural patterns |
| **Semantic Bridges** | 193 | RESOLVED_TO (code ↔ specifications) |
| **Cross-Repo Similarity** | 61 | CROSS_REPO_SIMILAR_TO edges |
| **Architectural Lineage** | 8 | CROSS_REPO_EVOLVED_FROM edges |
| **Unit Tests** | 213 | CI on Python 3.10 and 3.11 |

## 4. Verification & Exploration
Run this AQL query in ArangoDB to explore the top architectural links:
```aql
FOR edge IN RESOLVED_TO
  SORT edge.score DESC
  LIMIT 20
  LET source = DOCUMENT(edge._from)
  LET target = DOCUMENT(edge._to)
  RETURN {
    rtl_element: source.label,
    source_type: source.type,
    doc_concept: target.label,
    entity_type: target.entity_type,
    match_score: edge.score
  }
```

## 5. Visualizing the Graph
- **Database**: ArangoDB (`ic-knowledge-graph-temporal`)
- **Graph Name**: `IC_Temporal_Knowledge_Graph`
- **Naming Convention**: RTL nodes use dot-notation keys (e.g., `or1200_alu.clk`) for uniqueness across the hierarchy. Multi-repo collections use per-repo prefixes (`OR1200_`, `IBEX_`, `MOR1KX_`, `MAROCCHINO_`) for Golden Entities and Relations.
- **Analyzers**: The `harmonized_search_view` uses `text_en` and `identity` analyzers to support both fuzzy semantic search and exact technical identifier matching.
- **Deployment**: OneShard database on ArangoDB AMP cluster; 28 edge definitions in the named graph.

---
*Status: Production — Multi-Repo Temporal Knowledge Graph | Last Updated: 2026-03-31*
