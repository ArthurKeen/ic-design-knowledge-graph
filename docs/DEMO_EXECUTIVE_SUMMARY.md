# Integrated Circuit Design Knowledge Graph Demo - Executive Summary

**Duration**: 30-45 minutes  
**Audience**: Technical Stakeholders & Engineering Teams  
**Objective**: Demonstrate ArangoDB Knowledge Graph for Integrated Circuit (IC) Design across four open-source RISC-V / OpenRISC processors (OR1200, IBEX, MOR1KX, Marocchino)

---

## What We're Showing

**Four RISC processors** (OR1200, IBEX, MOR1KX, Marocchino) transformed into a unified temporal knowledge graph that combines:
- **Hardware Structure** (RTL): ~6,400 modules across four repos
- **Version History** (Git): ~3,800 commits, 381 temporal epochs
- **Temporal Snapshots**: 721 design situations capturing point-in-time state
- **Semantic Bridges**: 193 RESOLVED_TO edges, 61 CROSS_REPO_SIMILAR_TO edges linking designs across repositories

---

## Key Value Propositions

### 1. Hierarchical Semantic Bridge
**Problem**: Designers ask "Where is the Exception Status Register implemented?"  
**Solution**: Graph traversal from specification → RTL signal in one query  
**Benefit**: Eliminates manual spec-to-code searches

### 2. Temporal Design Audit
**Problem**: "Which specs were impacted by the ALU redesign in commit #48?"  
**Solution**: Time-travel queries combining commits + modules + entities  
**Benefit**: Impact analysis and traceability across versions

### 3. Token Efficiency for AI Agents
**Problem**: Current setup retrieves 10 document chunks (~5K tokens) per query  
**Solution**: Graph-guided retrieval returns 3 precise entities (~500 tokens)  
**Benefit**: 10x reduction in LLM context size = 90% token savings

### 4. Type-Safe Entity Resolution
**Problem**: Vector similarity creates false positives (e.g., "clock" matches "instruction")  
**Solution**: Compatibility matrix + RTL Header Extraction + Acronym Dictionary  
**Benefit**: 100% precision in semantic bridges (validated on 15 hardware-specific samples)

---

## Demo Flow (6 Parts, 30 minutes)

> See [TEMPORAL_DEMO_SCRIPT.md](TEMPORAL_DEMO_SCRIPT.md) for the full step-by-step guide.

| Part | Topic | Key Action | Time |
|------|-------|------------|------|
| **A** | System Overview | Load sample from all collections | 5 min |
| **B** | Semantic Bridge | Show ALU → Specification links | 10 min |
| **C** | Hierarchy Exploration | Drill down CPU → sub-modules → logic | 8 min |
| **D** | Cross-Domain Search | Spec term "Exception Status Register" → Code | 7 min |
| **E** | Temporal Audit | Recent commits → affected modules → impacted specs | 6 min |
| **F** | Advanced Use Cases | Shortest path, wiring diagrams | 4 min |

---

## Anticipated Questions & Answers

**Q1: "How does this scale to our billion-edge graphs?"**  
A: SmartGraphs sharding keeps related IP blocks on same shard. Sizing analysis shows sub-200ms queries at 10B+ edges.

**Q2: "What about versioning with time intervals on edges?"**  
A: Add `valid_from`/`valid_to` attributes on edges, filter in AQL. Straightforward extension of current model.

**Q3: "How accurate is entity resolution?"**  
A: Hardware domain validation: Precision 0.50→1.00, Recall 0.11→0.44, F1 0.18→0.62 (validated against 9-question ground-truth set). Captured complex matches like `if_insn` and `alu_op`.

**Q4: "Can we integrate with our Neo4j setup?"**
A: Yes. Parallel operation or full migration via JSON export/import. ArangoDB unifies graph + document models.

**Q5: "What about vector embeddings? We use FAISS."**  
A: ArangoDB supports native vector search via ArangoSearch (L2/cosine distance). Eliminates external FAISS index.

**Q6: "Can agents query this directly?"**  
A: Yes. REST API, Python/JavaScript drivers. Example: LangGraph agent performs graph traversal before LLM call.

---

## Technical Highlights

### Visual Schema

```mermaid
graph LR
    subgraph History ["History (Red)"]
        Commits[Git Commits]
    end

    subgraph Design ["Hardware (Blue)"]
        RTL[RTL Components]
    end

    subgraph Specs ["Documentation (Green)"]
        Entities[Golden Entities]
        Docs[Documents]
    end

    Commits -- "Track History" --> RTL
    RTL -- "Resolve To" --> Entities
    Entities -- "Extracted From" --> Docs

    %% Styling
    style Commits fill:#e53e3e,color:#fff
    style RTL fill:#3182ce,color:#fff
    style Entities fill:#e5ce3e,color:#000
    style Docs fill:#38a169,color:#fff
```

### Key Statistics
- **Query Performance**: Sub-200ms for multi-hop traversals
- **Scope**: 4 processors, ~6,400 modules, ~3,800 commits
- **Temporal Coverage**: 381 epochs, 721 design situations
- **Cross-Repo Bridges**: 193 RESOLVED_TO, 61 CROSS_REPO_SIMILAR_TO

### Technology Stack
- **Database**: ArangoDB (multi-model: graph + document + search)
- **Entity Resolution**: Custom ER library with type constraints
- **Search**: ArangoSearch (lexical + semantic analyzers)
- **Visualization**: Built-in Graph Visualizer with custom queries/actions

---

## Success Criteria

**Must Achieve**:
- [ ] Demonstrate spec-to-code bridge in <5 clicks
- [ ] Show temporal query combining 3 data sources
- [ ] Prove sub-second query response times
- [ ] Answer scaling questions confidently

**Nice to Have**:
- [ ] Live agent integration demo (if time)
- [ ] Show wiring connectivity analysis
- [ ] Discuss custom entity type extensions

---

## Post-Demo Actions

**If Positive Response**:
1. Share database credentials for hands-on exploration
2. Schedule technical deep-dive (2 hours)
3. Provide ETL pipeline source code
4. Discuss production scaling (cluster sizing)

**Follow-Up Materials**:
- Complete demo script (35 pages)
- Agent integration code samples
- Performance benchmarking results
- Migration guide (Neo4j → ArangoDB)

---

## Key Files Reference

| File | Purpose | Location |
|------|---------|----------|
| **TEMPORAL_DEMO_SCRIPT.md** | Current multi-repo temporal demo guide | `docs/` |
| **DEMO_SCRIPT.md** | Legacy single-repo demo (deprecated) | `docs/` |
| **DEMO_SETUP_QUERIES.json** | Pre-configured queries/actions/theme | `docs/` |
| **install_demo_setup.py** | Automated installer script | `scripts/setup/` |
| **install_theme.py** | Visualization theme installer | `scripts/setup/` |
| **DEMO_README.md** | Preparation checklist and troubleshooting | `docs/` |
| **SCHEMA.md** | Knowledge graph schema diagram | `docs/project/` |
| **WALKTHROUGH.md** | Data statistics and metrics | `docs/project/` |

---

## Pre-Demo Checklist (30 min before)

- [ ] Run `python scripts/setup/install_ic_theme.py` (installs 'hardware-design' theme)
- [ ] Run `python scripts/setup/install_demo_setup.py` (installs queries/actions)
- [ ] Open ArangoDB web interface → ic-knowledge-graph-temporal → IC_Temporal_Knowledge_Graph
- [ ] Apply "hardware-design" theme in Legend panel
- [ ] Test 3 queries: Graph Overview, ALU Entity Resolutions, Top Semantic Links
- [ ] Have TEMPORAL_DEMO_SCRIPT.md open for reference
- [ ] Clear canvas to start fresh

---

## Opening Line

> "We've transformed four open-source RISC processors—OR1200, IBEX, MOR1KX, and Marocchino—into a temporal knowledge graph that lets you time-travel through design evolution and discover cross-repo similarities. Let me show you how it works."

---

## Closing Line

> "This POC proves the architecture works. The next phase is to apply it to your proprietary IP—validating scalability, defining custom entity types, and integrating with your agent workflows. Let's schedule a technical deep-dive to map out the production architecture."

---

**Prepared by**: Project Team  
**Last Updated**: March 31, 2026  
**Version**: 2.0 (multi-repo temporal)

